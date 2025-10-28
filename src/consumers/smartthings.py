# SmartThings Consumer

import requests

url = "https://api.smartthings.com"


# Change any SmartThings toggle
def smartThingsConsumer(token: string):
    async def inner(queue: asyncio.Queue):
        # setup
        request = requests.get(url + "/devices", headers={"Authorization": "Bearer " + token})
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
                    headers={"Authorization": "Bearer " + token},
                    data='{"commands":[{"component":"main","capability":"switch","command":"on"}]}',
                )
            else:
                print("Invalid device/command: " + device + " " + command, flush=True)
            queue.task_done()
            await asyncio.sleep(0.1)

    return inner


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
