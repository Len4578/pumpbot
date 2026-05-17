import os
import json
import requests
import asyncio
import threading
import base58
import logging
from flask import Flask, request
from datetime import datetime

# ─── CONFIG ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "AAFQQwk-
nATsMs1wrJg8lBFYjKHKGMRKpZg..."
TELEGRAM_CHAT_ID   = "7175890846"
WALLET_PRIVATE_KEY = " 3HxT5NfLoerqVXgjx659KNG1zEc4WhyWtpcjNNYNhNArLXooESfokBSUAbSPH3bVYZ5U4wPmedHaxjBBczGx9sVU
  # base58 string

TARGET_PROFIT_PCT  = 0.30   # 30% take profit
STOP_LOSS_PCT      = 0.15   # 15% stop loss
TRADE_CAPITAL_PCT  = 0.80   # use 80% of balance
RESERVE_PCT        = 0.20   # keep 20% in reserve
MIN_RISK_REWARD    = 2.0    # minimum risk/reward ratio (30/15 = 2.0)

PUMP_FUN_API       = "https://frontend-api.pump.fun/coins"
JUPITER_QUOTE_API  = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API   = "https://quote-api.jup.ag/v6/swap"
SOL_MINT           = "So11111111111111111111111111111111111111112"

# ─── SETUP ───────────────────────────────────────────────────────────────────
app    = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Active trades: { token_mint: { entry_price, amount, take_profit, stop_loss } }
active_trades = {}
balance_sol   = 0.0
bot_running   = False


# ─── TELEGRAM HELPERS ────────────────────────────────────────────────────────
def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})


# ─── WALLET ──────────────────────────────────────────────────────────────────
def get_wallet_pubkey():
    try:
        from solders.keypair import Keypair
        kp = Keypair.from_base58_string(WALLET_PRIVATE_KEY)
        return str(kp.pubkey())
    except Exception as e:
        logger.error(f"Wallet error: {e}")
        return None

def get_sol_balance():
    try:
        pubkey = get_wallet_pubkey()
        resp = requests.post("https://api.mainnet-beta.solana.com", json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getBalance",
            "params": [pubkey]
        })
        lamports = resp.json()["result"]["value"]
        return lamports / 1e9  # convert to SOL
    except Exception as e:
        logger.error(f"Balance error: {e}")
        return 0.0


# ─── PUMP.FUN ────────────────────────────────────────────────────────────────
def get_new_pump_tokens(limit=20):
    """Fetch newest tokens from pump.fun API"""
    try:
        resp = requests.get(PUMP_FUN_API, params={
            "limit": limit,
            "offset": 0,
            "sort": "created_timestamp",
            "order": "DESC",
            "includeNsfw": False
        }, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception as e:
        logger.error(f"Pump.fun API error: {e}")
        return []

def get_token_price(mint):
    """Get token price in SOL via Jupiter"""
    try:
        resp = requests.get(JUPITER_QUOTE_API, params={
            "inputMint": SOL_MINT,
            "outputMint": mint,
            "amount": 1000000000,  # 1 SOL in lamports
            "slippageBps": 500
        }, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            out_amount = int(data.get("outAmount", 0))
            if out_amount > 0:
                return 1 / (out_amount / 1e9)  # price per token in SOL
        return None
    except Exception as e:
        logger.error(f"Price fetch error: {e}")
        return None


# ─── RISK / REWARD ───────────────────────────────────────────────────────────
def calculate_risk_reward(entry_price):
    """
    Returns (take_profit_price, stop_loss_price, rr_ratio)
    Only trade if rr_ratio >= MIN_RISK_REWARD
    """
    take_profit = entry_price * (1 + TARGET_PROFIT_PCT)
    stop_loss   = entry_price * (1 - STOP_LOSS_PCT)
    reward      = take_profit - entry_price
    risk        = entry_price - stop_loss
    rr_ratio    = reward / risk if risk > 0 else 0
    return take_profit, stop_loss, rr_ratio

def calculate_trade_size(balance):
    """Use 80% of balance, keep 20% in reserve"""
    tradeable = balance * TRADE_CAPITAL_PCT
    # Split across potential trades (max 3 at once)
    max_trades = 3
    per_trade  = tradeable / max_trades
    return per_trade


# ─── TRADING ─────────────────────────────────────────────────────────────────
def execute_buy(mint, sol_amount):
    """Execute buy via Jupiter swap"""
    try:
        pubkey = get_wallet_pubkey()
        lamports = int(sol_amount * 1e9)

        # Get quote
        quote_resp = requests.get(JUPITER_QUOTE_API, params={
            "inputMint": SOL_MINT,
            "outputMint": mint,
            "amount": lamports,
            "slippageBps": 500
        }, timeout=10)

        if quote_resp.status_code != 200:
            return None

        quote = quote_resp.json()

        # Get swap transaction
        swap_resp = requests.post(JUPITER_SWAP_API, json={
            "quoteResponse": quote,
            "userPublicKey": pubkey,
            "wrapAndUnwrapSol": True
        }, timeout=10)

        if swap_resp.status_code != 200:
            return None

        swap_data = swap_resp.json()
        tx_b64    = swap_data.get("swapTransaction")

        if not tx_b64:
            return None

        # Sign and send transaction
        from solders.keypair import Keypair
        from solders.transaction import VersionedTransaction
        import base64

        kp      = Keypair.from_base58_string(WALLET_PRIVATE_KEY)
        tx_bytes = base64.b64decode(tx_b64)
        tx       = VersionedTransaction.from_bytes(tx_bytes)
        tx.sign([kp])

        signed_tx = base64.b64encode(bytes(tx)).decode()
        send_resp = requests.post("https://api.mainnet-beta.solana.com", json={
            "jsonrpc": "2.0", "id": 1,
            "method": "sendTransaction",
            "params": [signed_tx, {"encoding": "base64"}]
        }, timeout=15)

        result = send_resp.json()
        return result.get("result")  # transaction signature

    except Exception as e:
        logger.error(f"Buy error: {e}")
        return None

def execute_sell(mint, token_amount):
    """Execute sell via Jupiter swap"""
    try:
        pubkey   = get_wallet_pubkey()
        amount   = int(token_amount)

        quote_resp = requests.get(JUPITER_QUOTE_API, params={
            "inputMint": mint,
            "outputMint": SOL_MINT,
            "amount": amount,
            "slippageBps": 500
        }, timeout=10)

        if quote_resp.status_code != 200:
            return None

        quote = quote_resp.json()

        swap_resp = requests.post(JUPITER_SWAP_API, json={
            "quoteResponse": quote,
            "userPublicKey": pubkey,
            "wrapAndUnwrapSol": True
        }, timeout=10)

        if swap_resp.status_code != 200:
            return None

        swap_data = swap_resp.json()
        tx_b64    = swap_data.get("swapTransaction")

        if not tx_b64:
            return None

        from solders.keypair import Keypair
        from solders.transaction import VersionedTransaction
        import base64

        kp       = Keypair.from_base58_string(WALLET_PRIVATE_KEY)
        tx_bytes = base64.b64decode(tx_b64)
        tx       = VersionedTransaction.from_bytes(tx_bytes)
        tx.sign([kp])

        signed_tx = base64.b64encode(bytes(tx)).decode()
        send_resp = requests.post("https://api.mainnet-beta.solana.com", json={
            "jsonrpc": "2.0", "id": 1,
            "method": "sendTransaction",
            "params": [signed_tx, {"encoding": "base64"}]
        }, timeout=15)

        result = send_resp.json()
        return result.get("result")

    except Exception as e:
        logger.error(f"Sell error: {e}")
        return None


# ─── MONITOR LOOP ────────────────────────────────────────────────────────────
def monitor_trades():
    """Background thread: check active trades for TP/SL"""
    import time
    while bot_running:
        for mint, trade in list(active_trades.items()):
            try:
                current_price = get_token_price(mint)
                if not current_price:
                    continue

                entry  = trade["entry_price"]
                tp     = trade["take_profit"]
                sl     = trade["stop_loss"]
                amount = trade["token_amount"]
                pct    = ((current_price - entry) / entry) * 100

                if current_price >= tp:
                    sig = execute_sell(mint, amount)
                    profit_pct = ((current_price - entry) / entry) * 100
                    send_message(
                        f"✅ *TAKE PROFIT HIT!*\n"
                        f"Token: `{mint[:8]}...`\n"
                        f"Profit: +{profit_pct:.1f}%\n"
                        f"Tx: `{sig}`"
                    )
                    del active_trades[mint]

                elif current_price <= sl:
                    sig = execute_sell(mint, amount)
                    loss_pct = ((current_price - entry) / entry) * 100
                    send_message(
                        f"🛑 *STOP LOSS HIT*\n"
                        f"Token: `{mint[:8]}...`\n"
                        f"Loss: {loss_pct:.1f}%\n"
                        f"Tx: `{sig}`"
                    )
                    del active_trades[mint]

                else:
                    send_message(
                        f"📊 *Trade Update*\n"
                        f"Token: `{mint[:8]}...`\n"
                        f"PnL: {pct:+.1f}%\n"
                        f"TP: +{TARGET_PROFIT_PCT*100:.0f}% | SL: -{STOP_LOSS_PCT*100:.0f}%"
                    )

            except Exception as e:
                logger.error(f"Monitor error for {mint}: {e}")

        time.sleep(30)  # check every 30 seconds


def scan_and_trade():
    """Background thread: scan pump.fun and enter trades"""
    import time
    while bot_running:
        try:
            if len(active_trades) >= 3:
                time.sleep(60)
                continue

            balance = get_sol_balance()
            reserve = balance * RESERVE_PCT

            if balance - reserve < 0.05:  # need at least 0.05 SOL to trade
                send_message("⚠️ *Low balance* — not enough SOL to trade safely.")
                time.sleep(120)
                continue

            tokens = get_new_pump_tokens(limit=20)

            for token in tokens:
                mint = token.get("mint")
                if not mint or mint in active_trades:
                    continue

                # Skip tokens older than 10 minutes
                created = token.get("created_timestamp", 0)
                age_mins = (datetime.utcnow().timestamp() - created / 1000) / 60
                if age_mins > 10:
                    continue

                price = get_token_price(mint)
                if not price:
                    continue

                tp, sl, rr = calculate_risk_reward(price)

                # Only trade if risk/reward is good enough
                if rr < MIN_RISK_REWARD:
                    continue

                trade_sol  = calculate_trade_size(balance)
                token_name = token.get("name", "Unknown")
                symbol     = token.get("symbol", "???")

                send_message(
                    f"🔍 *New Trade Signal*\n"
                    f"Token: {token_name} (${symbol})\n"
                    f"Mint: `{mint[:8]}...`\n"
                    f"Entry: {price:.8f} SOL\n"
                    f"TP: {tp:.8f} SOL (+30%)\n"
                    f"SL: {sl:.8f} SOL (-15%)\n"
                    f"R/R Ratio: {rr:.2f}\n"
                    f"Trade Size: {trade_sol:.3f} SOL"
                )

                sig = execute_buy(mint, trade_sol)

                if sig:
                    token_amount = (trade_sol * 1e9) / price
                    active_trades[mint] = {
                        "entry_price":  price,
                        "take_profit":  tp,
                        "stop_loss":    sl,
                        "token_amount": token_amount,
                        "sol_invested": trade_sol,
                        "name":         token_name,
                        "symbol":       symbol
                    }
                    send_message(
                        f"✅ *BUY EXECUTED*\n"
                        f"Token: {token_name} (${symbol})\n"
                        f"Invested: {trade_sol:.3f} SOL\n"
                        f"Tx: `{sig}`"
                    )
                    break  # one trade per scan cycle

        except Exception as e:
            logger.error(f"Scan error: {e}")

        time.sleep(60)  # scan every 60 seconds


# ─── TELEGRAM COMMANDS ───────────────────────────────────────────────────────
@app.route('/webhook', methods=['POST'])
def webhook():
    global bot_running
    data = request.get_json()

    if not data or "message" not in data:
        return "OK"

    msg  = data["message"]
    text = msg.get("text", "").strip()
    chat = msg.get("chat", {}).get("id")

    if text == "/start":
        bot_running = True
        threading.Thread(target=scan_and_trade,  daemon=True).start()
        threading.Thread(target=monitor_trades,  daemon=True).start()
        send_message(
            "🚀 *Bot Started!*\n"
            "Scanning pump.fun for early tokens...\n"
            "• Target Profit: 30%\n"
            "• Stop Loss: 15%\n"
            "• Min R/R: 2.0\n"
            "• Capital per trade: 80% of balance\n"
            "• Reserve: 20% always kept safe"
        )

    elif text == "/stop":
        bot_running = False
        send_message("🛑 *Bot Stopped.* All monitoring paused.")

    elif text == "/balance":
        bal     = get_sol_balance()
        reserve = bal * RESERVE_PCT
        send_message(
            f"💰 *Wallet Balance*\n"
            f"Total: {bal:.4f} SOL\n"
            f"Reserved (20%): {reserve:.4f} SOL\n"
            f"Tradeable (80%): {bal * TRADE_CAPITAL_PCT:.4f} SOL"
        )

    elif text == "/trades":
        if not active_trades:
            send_message("📭 No active trades right now.")
        else:
            msg_text = "📊 *Active Trades:*\n"
            for mint, t in active_trades.items():
                price = get_token_price(mint) or 0
                pct   = ((price - t["entry_price"]) / t["entry_price"]) * 100 if t["entry_price"] else 0
                msg_text += (
                    f"\n• {t['name']} (${t['symbol']})\n"
                    f"  PnL: {pct:+.1f}%\n"
                    f"  TP: +30% | SL: -15%\n"
                )
            send_message(msg_text)

    elif text == "/help":
        send_message(
            "🤖 *Pump.fun Trading Bot*\n\n"
            "/start — Start scanning & trading\n"
            "/stop — Stop the bot\n"
            "/balance — Check wallet balance\n"
            "/trades — View active trades\n"
            "/help — Show this menu"
        )

    return "OK"


@app.route('/')
def index():
    return "Pump.fun Trading Bot is running!"


if __name__ == '__main__':
    app.run(debug=False)

import requests,threading
from datetime import datetime
BOT= 
AAFQQwk-
nATsMs1wrJg8lBFYjKHKGMRKpZg“)
CHAT=“7175890846”
KEY=“ 3HxT5NfLoerqVXgjx659KNG1zEc4WhyWtpcjNNYNhNArLXooESfokBSUAbSPH3bVYZ5U4wPmedHaxjBBczGx9sVU “
app=Flask(“bot”)
active_trades={}
bot_running=False
def send(text):
        url=f”https://api.telegram.org/bot{BOT}/sendMessage”
        requests.post(url,json={“chat_id”:CHAT,“text”:text})

@app.route(”/”)
def index():
         return “Bot running!”

@app.route(”/webhook”,methods=[“POST”])
def webhook():
          global bot_running
        data=request.get_json()
     if not data or “message” not in data:
                      return “OK”
              text=data[“message”].get(“text”,””).strip()
     if text==”/start”:
                 bot_running=True
           send(“Bot Started! Scanning pump.fun…”)
    elif text==”/stop”:
        bot_running=False
     send(“Bot Stopped.”)
  elif text==”/balance”:
    send(“Checking balance…”)
  return “OK”

if name==”main”:
      : app.run()
    “Commit changes”
