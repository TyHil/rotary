import asyncio
import atexit
import os
import sys
import threading
import time
from datetime import timedelta
from enum import Enum

import requests
import serial
import RPi.GPIO as GPIO
import gpiod
from gpiod.line import Bias, Direction, Edge, Value
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger

import alarms  # defines times
import config  # defines smartThingsToken

GPIO.setmode(GPIO.BOARD)
atexit.register(GPIO.cleanup)


# Rotary Producer

ROTARY_CHIP = "/dev/gpiochip0"
ROTARY_LINE = 18  # BCM number of physical pin 12

rotaryRequest = None


def closeRotary():
    global rotaryRequest
    if rotaryRequest is not None:
        rotaryRequest.release()
        rotaryRequest = None


atexit.register(closeRotary)


# Kernel notifies on each pulse.
def setupRotary(
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    dialHasFinishedRotatingAfter=0.3,
    settleTime=0.015,
):
    global rotaryRequest
    count = 0
    finishTimer = None
    settleTimer = None

    rotaryRequest = gpiod.request_lines(
        ROTARY_CHIP,
        consumer="rotary",
        config={
            ROTARY_LINE: gpiod.LineSettings(
                direction=Direction.INPUT,
                edge_detection=Edge.BOTH,
                bias=Bias.PULL_UP,
            )
        },
    )
    stableLevel = rotaryRequest.get_value(ROTARY_LINE) == Value.ACTIVE

    def flush():  # the dial stopped moving, report the digit
        nonlocal count, finishTimer
        number, count, finishTimer = count, 0, None
        print("Read " + str(number), flush=True)
        queue.put_nowait(number)

    def settle():  # the pin has been quiet for settleTime: trust its level
        nonlocal count, finishTimer, settleTimer, stableLevel
        settleTimer = None
        level = rotaryRequest.get_value(ROTARY_LINE) == Value.ACTIVE
        if level == stableLevel:
            return  # it bounced and came back, no real change
        stableLevel = level
        if level:  # a real pulse
            count += 1
            if finishTimer is not None:
                finishTimer.cancel()
            finishTimer = loop.call_later(dialHasFinishedRotatingAfter, flush)

    def onEdge():  # any edge, rising or falling: restart the settle timer
        nonlocal settleTimer
        rotaryRequest.read_edge_events()  # drain everything queued, including bounce
        if settleTimer is not None:
            settleTimer.cancel()
        settleTimer = loop.call_later(settleTime, settle)

    loop.add_reader(rotaryRequest.fileno(), onEdge)


# Terminal Input Producer


# Manual control and clean exit when testing
async def readInput(queue: asyncio.Queue):
    if "--headless" not in sys.argv[1:]:
        while True:
            line = await asyncio.to_thread(input, "> ")
            if line == "exit" or line == "q":
                for task in asyncio.all_tasks():
                    if task is not asyncio.current_task():
                        task.cancel()
                break
            try:
                number = int(line)
            except ValueError:
                continue
            await queue.put(number)


# Router

# number -> indexes into outQueues (see rotary() for the order)
# 0: SmartThings, 1: Arduino, 2: alarm toggle, 3: restart
ROUTES = {
    1: [0],
    2: [0],
    3: [0],
    4: [0],
    5: [1],
    6: [1],
    7: [0, 1],
    9: [2],
    10: [3],
}


async def routeNumbers(inQueue: asyncio.Queue, outQueues: list[asyncio.Queue]):
    while True:
        number = await inQueue.get()
        routes = ROUTES.get(number, [])
        if not routes:
            print("Can't route " + str(number), flush=True)
        for index in routes:
            outQueues[index].put_nowait(number)
        inQueue.task_done()


# SmartThings Consumer

url = "https://api.smartthings.com"

# SmartThings label -> (device group, command)
DEVICE_LABELS = {
    "LED Strip On": ("ledStrip", "on"),
    "LED Strip Off": ("ledStrip", "off"),
    "LED Strip Toggle": ("ledStrip", "toggle"),
    "Bedside Lamp On": ("bedsideLamp", "on"),
    "Bedside Lamp Off": ("bedsideLamp", "off"),
    "Bedside Lamp Toggle": ("bedsideLamp", "toggle"),
    "All On": ("all", "on"),
    "All Off": ("all", "off"),
}


def fetchDevices(session: requests.Session):
    response = session.get(url + "/devices", timeout=10)
    response.raise_for_status()
    devices = {}
    for device in response.json()["items"]:  # categorize devices
        entry = DEVICE_LABELS.get(device.get("label"))
        if entry is not None:
            group, command = entry
            devices.setdefault(group, {})[command] = device["deviceId"]
    return devices


def pressSwitch(session: requests.Session, deviceId: str):
    try:
        response = session.post(
            url + "/devices/" + deviceId + "/commands",
            json={"commands": [{"component": "main", "capability": "switch", "command": "on"}]},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print("SmartThings request failed: " + str(error), flush=True)


# Change any SmartThings toggle
async def smartThings(queue: asyncio.Queue):
    # setup
    session = requests.Session()
    session.headers["Authorization"] = "Bearer " + config.smartThingsToken

    delay = 2
    while True:  # retry with backoff
        try:
            devices = await asyncio.to_thread(fetchDevices, session)
            break
        except requests.RequestException as error:
            print(
                "SmartThings setup failed, retrying in " + str(delay) + "s: " + str(error),
                flush=True,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    while True:  # consumer
        device, command = await queue.get()
        try:
            if device in devices and command in devices[device]:
                await asyncio.to_thread(pressSwitch, session, devices[device][command])
            else:
                print("Invalid device/command: " + device + " " + command, flush=True)
        finally:
            queue.task_done()


# Mini router to make toggling separate
# number -> (device, command, whether it should cancel a running alarm)
SMARTTHINGS_ACTIONS = {
    1: ("all", "on", True),
    2: ("all", "off", True),
    3: ("bedsideLamp", "toggle", False),
    4: ("ledStrip", "toggle", True),
    7: ("bedsideLamp", "off", True),
}


async def smartThingsRouter(inQueue: asyncio.Queue, outQueue: asyncio.Queue):
    while True:
        number = await inQueue.get()
        action = SMARTTHINGS_ACTIONS.get(number)
        if action is None:
            print("No SmartThings action for " + str(number), flush=True)
        else:
            device, command, stopsAlarm = action
            if stopsAlarm:
                alarmStopEarly.set()
            await outQueue.put([device, command])
        inQueue.task_done()


# Arduino Serial Consumer

UART_PIN = 7
GPIO.setup(UART_PIN, GPIO.OUT)
GPIO.output(UART_PIN, 1)

arduinoLock = threading.RLock()


# Send any bytes, blocking
def sendToArduinoRaw(data, maxAttempts=5):
    with arduinoLock:
        for attempt in range(maxAttempts):
            GPIO.output(UART_PIN, 0)
            try:
                with serial.Serial("/dev/serial0", 9600, timeout=1) as ser:
                    ser.reset_input_buffer()
                    ser.write(bytes(data + [sum(data) % 256]))
                    time.sleep(2)
                    if ser.in_waiting == 0:
                        print("Failed to send to Arduino", flush=True)
                        return None
                    if ser.read() != b"\x00":
                        # print(type(response), response, response[0], response[1], response[2], response[3], response[4], flush=True)
                        return ser.read(5)
            finally:
                GPIO.output(UART_PIN, 1)
            time.sleep(2)
        print("Arduino still busy after " + str(maxAttempts) + " attempts", flush=True)
        return None


# Use paramaters to send
def sendToArduino(fade, brightness, mode, color=[]):
    return sendToArduinoRaw([fade, brightness, mode] + color)


async def sendToArduinoAsync(*args, **kwargs):
    return await asyncio.to_thread(sendToArduino, *args, **kwargs)


# number -> (fade, brightness, mode, color)
ARDUINO_ACTIONS = {
    5: (1, 119, 0, []),  # white
    6: (1, 119, 1, []),  # RGB
    7: (1, 153, 6, [255, 105, 180]),  # pink
}


# Consumer
async def arduino(queue: asyncio.Queue):
    while True:
        number = await queue.get()
        action = ARDUINO_ACTIONS.get(number)
        if action is None:
            print("No arduino action for " + str(number), flush=True)
        else:
            alarmStopEarly.set()
            await sendToArduinoAsync(*action)
        queue.task_done()


# Alarm Consumer and Control


class AlarmState(Enum):
    on = 0
    skip = 1
    off = 2

    def next(self):
        cls = self.__class__
        return cls((self.value + 1) % len(cls))


alarmState = AlarmState.on
alarmStopEarly = asyncio.Event()


# Display state on LED Strip, blocking
def alarmResponse():
    color = [255, 0, 0]  # red
    if alarmState == AlarmState.on:
        color = [0, 255, 0]  # green
    elif alarmState == AlarmState.skip:
        color = [255, 255, 0]  # yellow
    with arduinoLock:  # keep anything else from sneaking in between these sends
        old = sendToArduino(1, 119, 6, color)
        time.sleep(2)
        if old is not None:
            sendToArduinoRaw([1] + [x for x in old])
        else:
            sendToArduino(1, 119, 1)


async def alarmResponseAsync(*args, **kwargs):
    return await asyncio.to_thread(alarmResponse, *args, **kwargs)


# Change alarm state
async def alarmToggle(queue: asyncio.Queue):
    global alarmState
    while True:
        number = await queue.get()
        if number == 9:  # skip and on/off toggle
            alarmStopEarly.set()
            alarmState = alarmState.next()
            await alarmResponseAsync()
        else:
            print("No alarm action for " + str(number), flush=True)
        queue.task_done()


# Sleep, but wake immediately if the alarm gets cancelled
async def sleepUnlessStopped(seconds):
    try:
        await asyncio.wait_for(alarmStopEarly.wait(), timeout=seconds)
        return True
    except asyncio.TimeoutError:
        return False


async def alarm(smartThingsQueue: asyncio.Queue):
    global alarmState
    if alarmState == AlarmState.skip:
        alarmState = AlarmState.on
    elif alarmState == AlarmState.on:
        alarmStopEarly.clear()
        await smartThingsQueue.put(["ledStrip", "on"])
        await smartThingsQueue.join()
        if await sleepUnlessStopped(10):
            return
        await sendToArduinoAsync(0, 17, 0)
        for brightness in range(17 * 2, 17 * 7 + 1, 17):
            if await sleepUnlessStopped(60 * 5):
                return
            await sendToArduinoAsync(0, brightness, 0)
        if not alarmStopEarly.is_set():
            await smartThingsQueue.put(["bedsideLamp", "on"])


# Restart Consumer


async def restart(queue: asyncio.Queue):
    while True:
        number = await queue.get()
        if number == 10:
            # os.execl skips atexit handlers
            closeRotary()
            GPIO.cleanup()
            os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            print("No restart action for " + str(number), flush=True)
        queue.task_done()


# Asyncio Producer, Router, and Consumer Setup


async def rotary(smartThingsQueue: asyncio.Queue):
    numberQueue = asyncio.Queue()
    smartThingsRouterQueue, arduinoQueue, alarmToggleQueue, restartQueue = (
        asyncio.Queue(),
        asyncio.Queue(),
        asyncio.Queue(),
        asyncio.Queue(),
    )
    setupRotary(numberQueue, asyncio.get_running_loop())
    producers = [
        asyncio.create_task(readInput(numberQueue)),
    ]
    routers = [
        asyncio.create_task(
            routeNumbers(
                numberQueue, [smartThingsRouterQueue, arduinoQueue, alarmToggleQueue, restartQueue]
            )
        ),
        asyncio.create_task(smartThingsRouter(smartThingsRouterQueue, smartThingsQueue)),
    ]
    consumers = [
        asyncio.create_task(smartThings(smartThingsQueue)),
        asyncio.create_task(arduino(arduinoQueue)),
        asyncio.create_task(alarmToggle(alarmToggleQueue)),
        asyncio.create_task(restart(restartQueue)),
    ]
    await asyncio.gather(*producers, *routers, *consumers)


# Alarm Setup


# Fires `offset` before a wrapped trigger
class EarlierTrigger(BaseTrigger):
    def __init__(self, trigger: BaseTrigger, offset: timedelta):
        self.trigger = trigger
        self.offset = offset

    def get_next_fire_time(self, previous_fire_time, now):
        if previous_fire_time is not None:
            previous_fire_time += self.offset
        fireTime = self.trigger.get_next_fire_time(previous_fire_time, now + self.offset)
        return None if fireTime is None else fireTime - self.offset


async def alarmSchedule(smartThingsQueue: asyncio.Queue):
    startEarly = timedelta(minutes=30, seconds=10)
    scheduler = AsyncIOScheduler()
    for entry in alarms.times:
        scheduler.add_job(
            alarm,
            EarlierTrigger(
                CronTrigger(
                    day_of_week=entry["day"],
                    hour=entry["hour"],
                    minute=entry["minute"],
                    second=0,
                ),
                startEarly,
            ),
            args=[smartThingsQueue],
            misfire_grace_time=300,  # allow running up to 5 mins late
        )
    scheduler.start()
    try:
        await asyncio.Event().wait()  # sleep forever without waking up
    finally:
        scheduler.shutdown()


# Main


async def main():
    smartThingsQueue = asyncio.Queue()
    try:
        await asyncio.gather(rotary(smartThingsQueue), alarmSchedule(smartThingsQueue))
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
