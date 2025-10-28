# Arduino Serial Consumer

import asyncio
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
async def arduinoConsumer(queue: asyncio.Queue):
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

