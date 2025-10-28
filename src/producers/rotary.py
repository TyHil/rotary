# Rotary Producer

import asyncio
import time
import RPi.GPIO as GPIO
import atexit

# Helper function for timing async waits
def millis():
    return time.time_ns() // 1_000_000

ROTARY_PIN = 12
GPIO.setmode(GPIO.BOARD)
GPIO.setup(ROTARY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
atexit.register(GPIO.cleanup)

async def rotaryProducer(queue: asyncio.Queue):
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

