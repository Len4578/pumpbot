import asyncio
import json
import requests
import websockets

TELEGRAM_TOKEN = 8831499845:AAE3ZAVFCiU1db1-19nY6YjeHIYhBStHEXY"REPLACE_WITH_TOKEN"
TELEGRAM_CHAT_ID = "7175890846"

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

async def main():
    send_telegram("Bot started on Render!")
    PUMP_WS = "wss://frontend-api.pump.fun/realtime"
    while True:
        try:
            async with websockets.connect(PUMP_WS, ping_interval=None) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                send_telegram("Connected to pump.fun!")
                async for msg in ws:
                    data = json.loads(msg)
                    if data.get("txType") == "create":
                        symbol = data.get("symbol", "???")
                        name = data.get("name", "Unknown")
                        send_telegram(f"New token: {symbol} ({name})")
        except Exception as e:
            await asyncio.sleep(5)

asyncio.run(main())
