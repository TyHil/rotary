import aiohttp
import asyncio
import pysmartthings

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BOARD)
import time

import serial

smartThingsToken = 'API_KEY'

ROTARY_PIN = 12
GPIO.setup(ROTARY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

UART_PIN = 7
GPIO.setup(UART_PIN, GPIO.OUT)
GPIO.output(UART_PIN, 1)



async def main():
    rotaryQueue, smartThingsQueue, arduinoQueue = asyncio.Queue(), asyncio.Queue(), asyncio.Queue()
    producer = asyncio.create_task(readRotary(rotaryQueue))
    router = asyncio.create_task(routeNumbers(rotaryQueue, smartThingsQueue, arduinoQueue))
    consumers = [asyncio.create_task(smartThings(smartThingsQueue)), asyncio.create_task(arduino(arduinoQueue))]
    await asyncio.gather(producer, router, *consumers)



def millis():
    return time.time_ns() // 1_000_000

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
            print(count)
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



async def routeNumbers(mainQueue: asyncio.Queue, firstQueue: asyncio.Queue, secondQueue: asyncio.Queue):
    while True:
        number = await mainQueue.get()
        if number >= 1 and number <= 4:
            await firstQueue.put(number)
        elif number >= 5 and number <= 6:
            await secondQueue.put(number)
        elif number == 7:
            await asyncio.gather(firstQueue.put(number), secondQueue.put(number))
        mainQueue.task_done()
        await asyncio.sleep(0.1)



async def smartThings(queue: asyncio.Queue):
    while True:
        try:
            print('Smart Things connecting...')
            async with aiohttp.ClientSession() as session:
                ledStrip = {}
                bedsideLamp = {}
                allDevices = {}

                api = pysmartthings.SmartThings(session, smartThingsToken)
                for device in await api.devices(): #categorize devices
                    if device.label == 'LED Strip On':
                        ledStrip['on'] = device
                    elif device.label == 'LED Strip Off':
                        ledStrip['off'] = device
                    elif device.label == 'LED Strip Toggle':
                        ledStrip['toggle'] = device
                    elif device.label == 'Bedside Lamp On':
                        bedsideLamp['on'] = device
                    elif device.label == 'Bedside Lamp Off':
                        bedsideLamp['off'] = device
                    elif device.label == 'Bedside Lamp Toggle':
                        bedsideLamp['toggle'] = device
                    elif device.label == 'All On':
                        allDevices['on'] = device
                    elif device.label == 'All Off':
                        allDevices['off'] = device
                print('Smart Things connected.')

                while True: #consumer
                    number = await queue.get()
                    if number == 1:
                        await allDevices['on'].command('main', 'switch', 'on')
                    elif number == 2:
                        await allDevices['off'].command('main', 'switch', 'on')
                    elif number == 3:
                        await ledStrip['toggle'].command('main', 'switch', 'on')
                    elif number == 4:
                        await bedsideLamp['toggle'].command('main', 'switch', 'on')
                    elif number == 7:
                        await bedsideLamp['off'].command('main', 'switch', 'on')
                    queue.task_done()
                    await asyncio.sleep(0.1)
        except aiohttp.client_exceptions.ClientConnectorError:
            print('Smart Things disconnected.')
            await asyncio.sleep(1)
        except:
            break

def sendToArduino(data): #brightness, mode, [r, g, b]
    print(data)
    GPIO.output(UART_PIN, 0)
    ser = serial.Serial('/dev/ttyS0', 9600, timeout=1)
    ser.reset_input_buffer()
    ser.write(bytes(data))
    '''temp = millis()
    while millis() - temp < 2000:
        if ser.in_waiting > 0:
            line = ser.readline()#.decode('utf-8').rstrip()
            print(type(line), line)#[0], line[1], line[2], line[3], line[4])'''
    ser.close()
    GPIO.output(UART_PIN, 1)

async def arduino(queue: asyncio.Queue):
    while True:
        number = await queue.get()
        if number == 5:
            sendToArduino([51, 5])
        elif number == 6:
            sendToArduino([51, 11])
        elif number == 7:
            sendToArduino([85, 16, 255, 105, 180])
        queue.task_done()
        await asyncio.sleep(0.1)


if __name__ == '__main__':
    asyncio.run(main())
