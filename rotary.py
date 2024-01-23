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



async def routeNumbers(inQueue: asyncio.Queue, outQueues: list[asyncio.Queue]):
    while True:
        number = await inQueue.get()
        if number == 1 or number == 2 or number == 3 or number == 4:
            await outQueues[0].put(number)
        elif number == 5 or number == 6:
            await outQueues[1].put(number)
        elif number == 7:
            await asyncio.gather(outQueues[0].put(number), outQueues[1].put(number))
        elif number == 2 or number == 9:
            await outQueues[2].put(number)
        elif number == 10:
            await outQueues[3].put(number)
        inQueue.task_done()
        await asyncio.sleep(0.1)



import aiohttp
import pysmartthings
import config # defines smartThingsToken

# for alarm
ledStripOn = None
bedsideLampOn = None

async def smartThings(queue: asyncio.Queue):
    global ledStripOn
    while True:
        try:
            printToSystemd('Smart Things connecting...')
            async with aiohttp.ClientSession() as session:
                ledStrip = {}
                bedsideLamp = {}
                allDevices = {}

                api = pysmartthings.SmartThings(session, config.smartThingsToken)
                for device in await api.devices(): #categorize devices
                    if device.label == 'LED Strip On':
                        ledStrip['on'] = device
                        ledStripOn = device
                    elif device.label == 'LED Strip Off':
                        ledStrip['off'] = device
                    elif device.label == 'LED Strip Toggle':
                        ledStrip['toggle'] = device
                    elif device.label == 'Bedside Lamp On':
                        bedsideLamp['on'] = device
                        bedsideLampOn = device
                    elif device.label == 'Bedside Lamp Off':
                        bedsideLamp['off'] = device
                    elif device.label == 'Bedside Lamp Toggle':
                        bedsideLamp['toggle'] = device
                    elif device.label == 'All On':
                        allDevices['on'] = device
                    elif device.label == 'All Off':
                        allDevices['off'] = device
                printToSystemd('Smart Things connected.')

                while True: #consumer
                    number = await queue.get()
                    if number == 1:
                        await allDevices['on'].command('main', 'switch', 'on')
                    elif number == 2:
                        await allDevices['off'].command('main', 'switch', 'on')
                    elif number == 3:
                        await bedsideLamp['toggle'].command('main', 'switch', 'on')
                    elif number == 4:
                        await ledStrip['toggle'].command('main', 'switch', 'on')
                    elif number == 7:
                        await bedsideLamp['off'].command('main', 'switch', 'on')
                    queue.task_done()
                    await asyncio.sleep(0.1)
        except aiohttp.client_exceptions.ClientConnectorError:
            printToSystemd('Smart Things disconnected.')
            await asyncio.sleep(1)
        except:
            break



import serial

UART_PIN = 7
GPIO.setup(UART_PIN, GPIO.OUT)
GPIO.output(UART_PIN, 1)

def sendToArduinoRaw(data, waitResponse=False): #brightness, mode, [r, g, b]
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

def sendToArduino(fade, brightness, mode, color=[], waitResponse=False): #brightness, mode, [r, g, b]):
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
        queue.task_done()
        await asyncio.sleep(0.1)

from datetime import date

async def alarm():
    day = date.today().weekday()
    if day == 0 or day == 1 or day == 2 or day == 3:
        global alarmOn, alarmSkip, alarmStop
        alarmStop = False
        #global ledStripOn, bedsideLampOn
        if alarmOn and not(alarmSkip) and ledStripOn is not None:
            await ledStripOn.command('main', 'switch', 'on')
            await asyncio.sleep(10)
            sendToArduino(0, 17, 5)
            for brightness in range(17*2, 17*7+1, 17):
                if alarmStop:
                    break
                await asyncio.sleep(60*5) # 2
                sendToArduino(0, brightness, 5)
            if not(alarmStop):
                await bedsideLampOn.command('main', 'switch', 'on')
        alarmSkip = False



import os

async def restart(queue: asyncio.Queue):
    while True:
        number = await queue.get()
        if number == 10:
            os.execl(sys.executable, sys.executable, *sys.argv)
        queue.task_done()
        await asyncio.sleep(0.1)



async def rotary():
    rotaryQueue, smartThingsQueue, arduinoQueue, alarmToggleQueue, restartQueue = asyncio.Queue(), asyncio.Queue(), asyncio.Queue(), asyncio.Queue(), asyncio.Queue()
    producer = asyncio.create_task(readRotary(rotaryQueue))
    router = asyncio.create_task(routeNumbers(rotaryQueue, [smartThingsQueue, arduinoQueue, alarmToggleQueue, restartQueue]))
    consumers = [asyncio.create_task(smartThings(smartThingsQueue)), asyncio.create_task(arduino(arduinoQueue)), asyncio.create_task(alarmToggle(alarmToggleQueue)), asyncio.create_task(restart(restartQueue))]
    await asyncio.gather(producer, router, *consumers)



from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def alarmSchedule():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(alarm, 'cron', year="*", month="*", day="*", hour="10", minute="29", second="50") # hour="10", minute="29", second="40")
    scheduler.start()
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()



async def main():
    await asyncio.gather(rotary(), alarmSchedule())

if __name__ == '__main__':
    asyncio.run(main())
