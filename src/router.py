# Router

import asyncio

async def router(inQueue: asyncio.Queue, outQueues: list[asyncio.Queue]):
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

