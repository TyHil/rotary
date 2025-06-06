import sys
import asyncio

import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BOARD)

import time


# Helper function for timing async waits
def millis():
    return time.time_ns() // 1_000_000


# Rotary Producer

ROTARY_PIN = 12
GPIO.setup(ROTARY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)


async def readRotary(queue: asyncio.Queue):
    lastState = False
    trueState = False
    count = 0
    needToPrint = 0
    dialHasFinishedRotatingAfterMs = 100
    lastStateChangeTime = 0

    while True:
        buttonState = GPIO.input(ROTARY_PIN)

        if (millis() - lastStateChangeTime) > dialHasFinishedRotatingAfterMs and needToPrint:
            print("Read " + str(count), flush=True)
            await queue.put(count)
            needToPrint = 0
            count = 0

        if buttonState != lastState:
            lastStateChangeTime = millis()
        if (millis() - lastStateChangeTime) > 10:
            if buttonState != trueState:
                trueState = buttonState
                if trueState == True:
                    count += 1
                    needToPrint = 1
        lastState = buttonState
        await asyncio.sleep(0.01)


import atexit

atexit.register(GPIO.cleanup)


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
                await queue.put(number)
            except ValueError:
                continue
            await asyncio.sleep(0.1)


# Router


async def routeNumbers(inQueue: asyncio.Queue, outQueues: list[asyncio.Queue]):
    while True:
        number = await inQueue.get()
        routes = []
        if number == 1 or number == 2 or number == 3 or number == 4 or number == 7:
            routes.append(0)
        if number == 5 or number == 6 or number == 7:
            routes.append(1)
        if number == 9:
            routes.append(2)
        if number == 10:
            routes.append(3)
        if len(routes) == 0:
            print("Can't route " + str(number), flush=True)
        await asyncio.gather(*map(lambda index: outQueues[index].put(number), routes))
        inQueue.task_done()
        await asyncio.sleep(0.1)


# SmartThings Consumer

import requests
import config  # defines smartThingsToken

url = "https://api.smartthings.com"


# Change any SmartThings toggle
async def smartThings(queue: asyncio.Queue):
    # setup
    request = requests.get(
        url + "/devices", headers={"Authorization": "Bearer " + config.smartThingsToken}
    )
    result = request.json()
    devices = {}
    devices["ledStrip"] = {}
    devices["bedsideLamp"] = {}
    devices["all"] = {}
    for device in result["items"]:  # categorize devices
        if device["label"] == "LED Strip On":
            devices["ledStrip"]["on"] = device["deviceId"]
        elif device["label"] == "LED Strip Off":
            devices["ledStrip"]["off"] = device["deviceId"]
        elif device["label"] == "LED Strip Toggle":
            devices["ledStrip"]["toggle"] = device["deviceId"]
        elif device["label"] == "Bedside Lamp On":
            devices["bedsideLamp"]["on"] = device["deviceId"]
        elif device["label"] == "Bedside Lamp Off":
            devices["bedsideLamp"]["off"] = device["deviceId"]
        elif device["label"] == "Bedside Lamp Toggle":
            devices["bedsideLamp"]["toggle"] = device["deviceId"]
        elif device["label"] == "All On":
            devices["all"]["on"] = device["deviceId"]
        elif device["label"] == "All Off":
            devices["all"]["off"] = device["deviceId"]

    while True:  # consumer
        device, command = await queue.get()
        if device in devices and command in devices[device]:
            requests.post(
                url + "/devices/" + devices[device][command] + "/commands",
                headers={"Authorization": "Bearer " + config.smartThingsToken},
                data='{"commands":[{"component":"main","capability":"switch","command":"on"}]}',
            )
        else:
            print("Invalid device/command: " + device + " " + command, flush=True)
        queue.task_done()
        await asyncio.sleep(0.1)


# Mini router to make toggling separate
async def smartThingsRouter(inQueue: asyncio.Queue, outQueue: asyncio.Queue):
    while True:
        number = await inQueue.get()
        if number == 1:
            alarmStopEarly.set()
            await outQueue.put(["all", "on"])
        elif number == 2:
            alarmStopEarly.set()
            await outQueue.put(["all", "off"])
        elif number == 3:
            await outQueue.put(["bedsideLamp", "toggle"])
        elif number == 4:
            alarmStopEarly.set()
            await outQueue.put(["ledStrip", "toggle"])
        elif number == 7:
            alarmStopEarly.set()
            await outQueue.put(["bedsideLamp", "off"])
        else:
            print("No SmartThings action for " + str(number), flush=True)
        inQueue.task_done()
        await asyncio.sleep(0.1)


# Arduino Serial Consumer

import serial

UART_PIN = 7
GPIO.setup(UART_PIN, GPIO.OUT)
GPIO.output(UART_PIN, 1)


# Send any bytes
def sendToArduinoRaw(data):
    GPIO.output(UART_PIN, 0)
    ser = serial.Serial("/dev/serial0", 9600, timeout=1)
    ser.reset_input_buffer()
    ser.write(bytes(data + [sum(data) % 256]))
    time.sleep(2)
    response = None
    if ser.in_waiting > 0:
        check = ser.read()
        if check == b"\x00":
            ser.close()
            GPIO.output(UART_PIN, 1)
            temp = millis()
            while millis() - temp < 2000:
                pass
            return sendToArduinoRaw(data)
        else:
            response = ser.read(5)
            # print(type(response), response, response[0], response[1], response[2], response[3], response[4], flush=True)
    else:
        print("Failed to send to Arduino", flush=True)
    ser.close()
    GPIO.output(UART_PIN, 1)
    return response


# Use paramaters to send
def sendToArduino(fade, brightness, mode, color=[]):
    return sendToArduinoRaw([fade, brightness, mode] + color)


# Consumer
async def arduino(queue: asyncio.Queue):
    while True:
        number = await queue.get()
        if number == 5:  # white
            alarmStopEarly.set()
            sendToArduino(1, 51, 0)
        elif number == 6:  # RGB
            alarmStopEarly.set()
            sendToArduino(1, 51, 1)
        elif number == 7:  # pink
            alarmStopEarly.set()
            sendToArduino(1, 85, 6, [255, 105, 180])
        else:
            print("No arduino action for " + str(number), flush=True)
        queue.task_done()
        await asyncio.sleep(0.1)


# Alarm Consumer and Control

from enum import Enum


class AlarmState(Enum):
    on = 0
    skip = 1
    off = 2

    def next(self):
        cls = self.__class__
        return cls((self.value + 1) % len(cls))


alarmState = AlarmState.on
alarmStopEarly = asyncio.Event()


# Display state on LED Strip
def alarmResponse():
    color = [255, 0, 0]  # red
    if alarmState == AlarmState.on:
        color = [0, 255, 0]  # green
    elif alarmState == AlarmState.skip:
        color = [255, 255, 0]  # yellow
    old = sendToArduino(1, 51, 6, color)
    time.sleep(2)
    if old is not None:
        sendToArduinoRaw([1] + [x for x in old])
    else:
        sendToArduino(1, 51, 1)


# Change alarm state
async def alarmToggle(queue: asyncio.Queue):
    global alarmState
    while True:
        number = await queue.get()
        if number == 9:  # skip and on/off toggle
            alarmStopEarly.set()
            alarmState = alarmState.next()
            alarmResponse()
        else:
            print("No alarm action for " + str(number), flush=True)
        queue.task_done()
        await asyncio.sleep(0.1)


from datetime import date


async def alarm(smartThingsQueue: asyncio.Queue):
    global alarmState
    if alarmState != AlarmState.off:
        alarmStopEarly.clear()
        if alarmState == AlarmState.on:
            await smartThingsQueue.put(["ledStrip", "on"])
            await smartThingsQueue.join()
            await asyncio.sleep(10)
            sendToArduino(0, 5, 0)
            for brightness in range(17 * 2, 17 * 7 + 1, 17):
                if alarmStopEarly.is_set():
                    break
                await asyncio.sleep(60 * 5)
                sendToArduino(0, brightness, 0)
            if not alarmStopEarly.is_set():
                await smartThingsQueue.put(["bedsideLamp", "on"])
        elif alarmState == AlarmState.skip:
            alarmState = AlarmState.on


# Restart Consumer

import os


async def restart(queue: asyncio.Queue):
    while True:
        number = await queue.get()
        if number == 10:
            os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            print("No restart action for " + str(number), flush=True)
        queue.task_done()
        await asyncio.sleep(0.1)


# Asyncio Producer, Router, and Consumer Setup


async def rotary(smartThingsQueue: asyncio.Queue):
    numberQueue = asyncio.Queue()
    smartThingsRouterQueue, arduinoQueue, alarmToggleQueue, restartQueue = (
        asyncio.Queue(),
        asyncio.Queue(),
        asyncio.Queue(),
        asyncio.Queue(),
    )
    producers = [
        asyncio.create_task(readRotary(numberQueue)),
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

import alarms  # defines times
from apscheduler.schedulers.asyncio import AsyncIOScheduler


async def alarmSchedule(smartThingsQueue: asyncio.Queue()):
    removeMins = 31
    scheduler = AsyncIOScheduler()
    for time in alarms.times:
        scheduler.add_job(
            alarm,
            "cron",
            [smartThingsQueue],
            year="*",
            month="*",
            day="*",
            day_of_week=time["day"],
            hour=((time["hour"] - 1) % 24) if (time["minute"] < removeMins) else time["hour"],
            minute=(time["minute"] - removeMins) % 60,
            second="50",
        )
    scheduler.start()
    try:
        while True:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
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
