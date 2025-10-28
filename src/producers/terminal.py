# Terminal Input Producer

import asyncio
import sys


# Manual control and clean exit when testing
async def terminalProducer(queue: asyncio.Queue):
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

