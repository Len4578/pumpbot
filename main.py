import asyncio
import json
import requests
import websockets

TELEGRAM_TOKEN = "8831499845:AAE3ZAVFCiU1db1-19nY6YjeHIYhBStHEXY"
TELEGRAM_CHAT_ID = "7175890846"

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

async def main():
    send_telegram("Bot started!")
    print("Bot started!")
    PUMP_WS = "wss://frontend-api.pump.fun/realtime"
    while True:
        try:
            print("Connecting to pump.fun...")
            async with websockets.connect(
                PUMP_WS,
                ping_interval=20,
                ping_timeout=10,
                extra_headers={
                    "User-Agent": "Mozilla/5.0",
                    "Origin": "https://pump.fun"
                }
            ) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                send_telegram("Connected to pump.fun!")
                print("Connected!")
                async for msg in ws:
                    data = json.loads(msg)
                    if data.get("txType") == "create":
                        symbol = data.get("symbol", "???")
                        name = data.get("name", "Unknown")
                        print(f"New token: {symbol}")
                        send_telegram(f"New token: {symbol} ({name})")
        except Exception as e:
            print(f"Error: {e}")
            send_telegram(f"Reconnecting...")
            await asyncio.sleep(5)

asyncio.run(main())
