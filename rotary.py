import asyncio

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BOARD)



import sys

def printToSystemd(*objects):
    print(*objects)
    sys.stdout.flush()



import time

def millis():
    return time.time_ns() // 1_000_000



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
            printToSystemd(count)
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



async def routeNumbers(inQueue: asyncio.Queue, outQueues: list[asyncio.Queue]):
    def put(index, number):
        return outQueues[index].put(number)
    while True:
        number = await inQueue.get()
        routes = []
        if number == 1 or number == 2 or number == 3 or number == 4 or number == 7:
            routes.append(0)
        if number == 5 or number == 6 or number == 7:
            routes.append(1)
        if number == 2 or number == 9:
            routes.append(2)
        if number == 10:
            routes.append(3)
        if len(routes) == 0:
            printToSystemd("Can't route " + str(number))
        await asyncio.gather(*map(lambda index: outQueues[index].put(number), routes))
        inQueue.task_done()
        await asyncio.sleep(0.1)



import aiohttp
import pysmartthings
import config # defines smartThingsToken

async def smartThings(queue: asyncio.Queue):
    while True:
        try:
            printToSystemd('Smart Things connecting...')
            async with aiohttp.ClientSession() as session:
                devices = {}
                devices['ledStrip'] = {}
                devices['bedsideLamp'] = {}
                devices['all'] = {}

                api = pysmartthings.SmartThings(session, config.smartThingsToken)
                for device in await api.devices(): #categorize devices
                    if device.label == 'LED Strip On':
                        devices['ledStrip']['on'] = device
                    elif device.label == 'LED Strip Off':
                        devices['ledStrip']['off'] = device
                    elif device.label == 'LED Strip Toggle':
                        devices['ledStrip']['toggle'] = device
                    elif device.label == 'Bedside Lamp On':
                        devices['bedsideLamp']['on'] = device
                    elif device.label == 'Bedside Lamp Off':
                        devices['bedsideLamp']['off'] = device
                    elif device.label == 'Bedside Lamp Toggle':
                        devices['bedsideLamp']['toggle'] = device
                    elif device.label == 'All On':
                        devices['all']['on'] = device
                    elif device.label == 'All Off':
                        devices['all']['off'] = device
                printToSystemd('Smart Things connected.')

                while True: #consumer
                    device, command = await queue.get()
                    if device in devices and command in devices[device]:
                        await devices[device][command].command('main', 'switch', 'on')
                    else:
                        printToSystemd('Invalid device/command: ' + device + ' ' + command)
                    queue.task_done()
                    await asyncio.sleep(0.1)
        except aiohttp.client_exceptions.ClientConnectorError:
            printToSystemd('Smart Things disconnected.')
            await asyncio.sleep(1)
        except:
            break

async def smartThingsRouter(inQueue: asyncio.Queue, outQueue: asyncio.Queue):
    while True:
        number = await inQueue.get()
        if number == 1:
            await outQueue.put(['all', 'on'])
        elif number == 2:
            await outQueue.put(['all', 'off'])
        elif number == 3:
            await outQueue.put(['bedsideLamp', 'toggle'])
        elif number == 4:
            await outQueue.put(['ledStrip', 'toggle'])
        elif number == 7:
            await outQueue.put(['bedsideLamp', 'off'])
        printToSystemd('No smart things action for ' + str(number))
        inQueue.task_done()
        await asyncio.sleep(0.1)



import serial

UART_PIN = 7
GPIO.setup(UART_PIN, GPIO.OUT)
GPIO.output(UART_PIN, 1)

def sendToArduinoRaw(data, waitResponse=False):
    GPIO.output(UART_PIN, 0)
    ser = serial.Serial('/dev/ttyS0', 9600, timeout=1)
    ser.reset_input_buffer()
    ser.write(bytes(data))
    temp = millis()
    response = None
    if waitResponse:
        while millis() - temp < 2000:
            if ser.in_waiting > 0:
                response = ser.read(5)
                #printToSystemd(type(response), response, response[0], response[1], response[2], response[3], response[4])
    ser.close()
    GPIO.output(UART_PIN, 1)
    return response

def sendToArduino(fade, brightness, mode, color=[], waitResponse=False):
    return sendToArduinoRaw([fade, brightness, mode] + color, waitResponse)

async def arduino(queue: asyncio.Queue):
    while True:
        number = await queue.get()
        if number == 5: # white
            sendToArduino(1, 51, 5)
        elif number == 6: # RGB
            sendToArduino(1, 51, 11)
        elif number == 7: # pink
            sendToArduino(1, 85, 16, [255, 105, 180])
        else:
            printToSystemd('No arduino action for ' + str(number))
        queue.task_done()
        await asyncio.sleep(0.1)




alarmOn = True
alarmSkip = False
alarmStop = False

def alarmResponseDisplay(old):
    time.sleep(2)
    if old is not None:
        sendToArduinoRaw([1] + [x for x in old])
    else:
        sendToArduino(1, 51, 11)

def alarmResponse():
    if not(alarmOn): # red
        alarmResponseDisplay(sendToArduino(1, 51, 16, [255, 0, 0], True))
    else:
        if alarmSkip: # yellow
            alarmResponseDisplay(sendToArduino(1, 51, 16, [255, 255, 0], True))
        else: # green
            alarmResponseDisplay(sendToArduino(1, 51, 16, [0, 255, 0], True))

async def alarmToggle(queue: asyncio.Queue):
    global alarmOn, alarmSkip, alarmStop
    while True:
        number = await queue.get()
        if number == 2:
            alarmStop = True
        if number == 9: # skip and on/off toggle
            if not(alarmOn):
                alarmOn = True
                alarmSkip = False
            elif not(alarmSkip):
                alarmSkip = True
            elif alarmSkip:
                alarmOn = False
            alarmResponse()
        else:
            printToSystemd('No alarm action for ' + str(number))
        queue.task_done()
        await asyncio.sleep(0.1)

from datetime import date

async def alarm(smartThingsQueue: asyncio.Queue):
    day = date.today().weekday()
    if day == 0 or day == 1 or day == 2 or day == 3:
        global alarmOn, alarmSkip, alarmStop
        alarmStop = False
        if alarmOn and not(alarmSkip):
            await smartThingsQueue.put(['ledStrip', 'on'])
            await smartThingsQueue.join()
            await asyncio.sleep(10)
            sendToArduino(0, 17, 5)
            for brightness in range(17*2, 17*7+1, 17):
                if alarmStop:
                    break
                await asyncio.sleep(60*5) # 60*5
                sendToArduino(0, brightness, 5)
            if not(alarmStop):
                await smartThingsQueue.put(['bedsideLamp', 'on'])
        alarmSkip = False



import os

async def restart(queue: asyncio.Queue):
    while True:
        number = await queue.get()
        if number == 10:
            os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            printToSystemd('No restart action for ' + str(number))
        queue.task_done()
        await asyncio.sleep(0.1)



async def rotary(smartThingsQueue: asyncio.Queue):
    rotaryQueue = asyncio.Queue()
    smartThingsRouterQueue, arduinoQueue, alarmToggleQueue, restartQueue = asyncio.Queue(), asyncio.Queue(), asyncio.Queue(), asyncio.Queue()
    producer = asyncio.create_task(readRotary(rotaryQueue))
    routers = [asyncio.create_task(routeNumbers(rotaryQueue, [smartThingsRouterQueue, arduinoQueue, alarmToggleQueue, restartQueue])), asyncio.create_task(smartThingsRouter(smartThingsRouterQueue, smartThingsQueue))]
    consumers = [asyncio.create_task(smartThings(smartThingsQueue)), asyncio.create_task(arduino(arduinoQueue)), asyncio.create_task(alarmToggle(alarmToggleQueue)), asyncio.create_task(restart(restartQueue))]
    await asyncio.gather(producer, *routers, *consumers)



from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def alarmSchedule(smartThingsQueue: asyncio.Queue()):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(alarm, 'cron', [smartThingsQueue], year="*", month="*", day="*", hour="10", minute="29", second="50") # hour="10", minute="29", second="40")
    scheduler.start()
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()



async def main():
    smartThingsQueue = asyncio.Queue()
    await asyncio.gather(rotary(smartThingsQueue), alarmSchedule(smartThingsQueue))

if __name__ == '__main__':
    asyncio.run(main())

