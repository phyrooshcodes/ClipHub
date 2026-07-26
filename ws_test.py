import asyncio
import websockets
import json

async def fetch_logs():
    async with websockets.connect("ws://localhost:7842/ws/7b6c704e") as ws:
        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                print(data)
                if data.get("type") in ("done", "error"):
                    break
            except Exception as e:
                print("Error:", e)
                break

asyncio.run(fetch_logs())
