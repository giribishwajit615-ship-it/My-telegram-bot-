# file: channel_video_bot.py
# Requirements: python >= 3.9, python-telegram-bot>=20, requests
# Install first: pip install python-telegram-bot requests

import uuid
import sqlite3
import requests
import logging
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# === CONFIG ===
BOT_TOKEN = "8222645012:AAEQMNK31oa5hDo_9OEStfNL7FMBdZMkUFM"
ADRINO_SHORTEN_API = "https://adrinolinks.in/api/shorten"
ADRINO_API_KEY = "5b33540e7eaa148b24b8cca0d9a5e1b9beb3e634"
BASE_BOT_USERNAME = "Cornsebot"  # without @
OWNER_CHAT_ID = 7681308594  # 👈 YOUR Telegram ID (admin)

# === DB ===
DB_PATH = "videos.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            token TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            filename TEXT,
            caption TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# === SHORTENER ===
def shorten_url(long_url: str) -> str:
    payload = {
        "api_key": ADRINO_API_KEY,
        "url": long_url
    }
    try:
        r = requests.post(ADRINO_SHORTEN_API, json=payload, timeout=8)
        r.raise_for_status()
        data = r.json()
        # adjust based on response format
        short = data.get("short") or data.get("short_url") or data.get("result")
        if not short:
            raise ValueError("Shortener response missing short url, response: " + str(data))
        return short
    except Exception as e:
        logging.exception("Shortener failed, returning long url as fallback")
        return long_url

# === HANDLERS ===
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Hi 👋 — Agar aapko video chahiye to link se start karein.")
        return

    token = args[0]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT file_id, filename, caption FROM videos WHERE token = ?", (token,))
    row = c.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("Maaf kijiye — yeh link expire ho gaya ya galat hai.")
        return

    file_id, filename, caption = row
    try:
        await context.bot.send_video(chat_id=update.effective_chat.id, video=file_id, caption=caption or "")
    except Exception as e:
        logging.exception("Failed to send video")
        await update.message.reply_text("Video bhejne mein dikkat aayi. Please try again later.")

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post
    if not post:
        return

    video = post.video
    doc = post.document
    file_id = None
    filename = None
    caption = post.caption or ""

    if video:
        file_id = video.file_id
        filename = video.file_name
    elif doc and (doc.mime_type and doc.mime_type.startswith("video")):
        file_id = doc.file_id
        filename = doc.file_name
    else:
        return  # not a video

    token = uuid.uuid4().hex
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO videos (token, file_id, filename, caption) VALUES (?, ?, ?, ?)",
              (token, file_id, filename, caption))
    conn.commit()
    conn.close()

    long_link = f"https://t.me/{BASE_BOT_USERNAME}?start={token}"
    short_link = shorten_url(long_link)

    # send the short link privately to admin (OWNER_CHAT_ID)
    try:
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=f"🎬 New video saved!\n\n🔗 Short link: {short_link}\n\nOriginal: {long_link}\n\nToken: {token}"
        )
    except Exception as e:
        logging.exception("Failed to send short link to admin")

# === MAIN ===
def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.ALL, channel_post_handler))

    print("✅ Bot started... Waiting for videos in channel.")
    app.run_polling()

if __name__ == "__main__":
    main()
