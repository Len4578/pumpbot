import asyncio
import json
import requests
import websockets

TELEGRAM_TOKEN = "8107971895:AAEyZCHy5n0t1VVYkNp04mcZfm0YEhjPaf0"
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
    send_telegram("✅ Bot started!")
    print("Bot started!")
    PUMP_WS = "wss://pumpportal.fun/api/data"
    while True:
        try:
            print("Connecting to pump.fun...")
            async with websockets.connect(PUMP_WS) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                send_telegram("🔌 Connected! Watching for new tokens...")
                print("Connected!")
                async for msg in ws:
                    data = json.loads(msg)
                    symbol = data.get("symbol", "???")
                    name = data.get("name", "Unknown")
                    mint = data.get("mint", "")
                    print(f"New token: {symbol}")
                    send_telegram(f"🆕 {symbol} ({name})\nMint: {mint[:20]}...")
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(5)

asyncio.run(main())
