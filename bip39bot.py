from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8107971895:AAHQA5TUHllcZMgbW8rKx9K-2C4Za16iX3w"

BIP39_LIST = "abandon ability able about above absent absorb abstract absurd abuse access accident account accuse achieve acid acoustic acquire across act action actor actress actual adapt add addict address adjust admit adult advance advice aerobic afford afraid again age agent agree ahead aim air airport aisle alarm album alcohol alert alien all alley allow almost alone alpha already also alter always amateur amazing among amount amused analyst anchor ancient anger angle angry animal ankle announce annual another answer antenna antique anxiety any apart apology appear apple approve april arch arctic area arena argue arm armed armor army around arrange arrest arrive arrow art artefact artist artwork ask aspect assault asset assist assume asthma athlete atom attack attend attitude attract auction audit august aunt author auto autumn average avocado avoid awake aware away awesome awful awkward axis".split()

WORD_TO_INDEX = {word: i+1 for i, word in enumerate(BIP39_LIST)}
BIP39_WORDS = set(BIP39_LIST)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me BIP39 words to check!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = update.message.text.strip().lower().split()
    response = []
    for word in words:
        if word in WORD_TO_INDEX:
            response.append(f"✅ {word} → #{WORD_TO_INDEX[word]}")
        else:
            response.append(f"❌ {word} → Not valid BIP39")
    await update.message.reply_text("\n".join(response))

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
