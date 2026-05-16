import asyncio
import json
import requests
import websockets

TELEGRAM_TOKEN =8831499845:AAG2je5Zgh9Mv8OkPbW9nFK0jri-9m81rE8 "YOUR_NEW_TOKEN_HERE"
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
    send_telegram("✅ Bot started!")
    PUMP_WS = "wss://frontend-api.pump.fun/realtime"
    while True:
        try:
            async with websockets.connect(PUMP_WS, ping_interval=None) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                send_telegram("🔌 Connected to pump.fun!")
                async for msg in ws:
                    data = json.loads(msg)
                    if data.get("txType") == "create":
                        symbol = data.get("symbol", "???")
                        name = data.get("name", "Unknown")
                        send_telegram(f"🆕 {symbol} ({name})")
        except Exception as e:
            await asyncio.sleep(5)

asyncio.run(main())
