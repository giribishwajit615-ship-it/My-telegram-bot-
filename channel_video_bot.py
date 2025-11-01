# file: channel_video_bot.py
# Requirements: python >= 3.9, python-telegram-bot>=20, requests

import uuid
import sqlite3
import requests
import logging
import datetime
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# === CONFIG ===
BOT_TOKEN = "8222645012:AAEQMNK31oa5hDo_9OEStfNL7FMBdZMkUFM"
ADRINO_SHORTEN_API = "https://adrinolinks.in/api"
ADRINO_API_KEY = "5b33540e7eaa148b24b8cca0d9a5e1b9beb3e634"
BASE_BOT_USERNAME = "Cornsebot"  # without @
OWNER_CHAT_ID = 7681308594       # your Telegram numeric id
CHANNEL_ID = -1003051609606      # your channel id (bot must be admin here)

DB_PATH = "videos.db"
logging.basicConfig(level=logging.INFO)


# === INIT DB ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            token TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            filename TEXT,
            caption TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


# === SHORTENER ===
def shorten_url(long_url: str) -> str:
    payload = {"api_key": ADRINO_API_KEY, "url": long_url}
    try:
        r = requests.post(ADRINO_SHORTEN_API, json=payload, timeout=8)
        r.raise_for_status()
        data = r.json()
        short = data.get("short") or data.get("short_url") or data.get("result") or data.get("url")
        return short or long_url
    except Exception:
        logging.exception("Shortener failed, returning original URL")
        return long_url


# === HELPERS ===
def save_video_to_db(token: str, file_id: str, filename: str | None, caption: str | None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO videos (token, file_id, filename, caption, created_at) VALUES (?, ?, ?, ?, ?)",
        (token, file_id, filename or "", caption or "", datetime.datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


# === HANDLERS ===
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User opens the short link"""
    args = context.args
    user = update.effective_user
    user_id = user.id if user else None

    if not args:
        await update.message.reply_text("👋 Send me a valid video link.")
        return

    token = args[0]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT file_id, caption FROM videos WHERE token = ?", (token,))
    v = c.fetchone()
    conn.close()

    if not v:
        await update.message.reply_text("❌ Invalid or expired video link.")
        return

    sent = await context.bot.send_video(chat_id=user_id, video=v[0], caption=v[1] or "")
    await asyncio.sleep(3600)  # 1 hour
    try:
        await context.bot.delete_message(chat_id=user_id, message_id=sent.message_id)
    except Exception:
        pass


async def save_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner sends video -> bot uploads to channel -> gives short link"""
    sender = update.effective_user
    if not sender or sender.id != OWNER_CHAT_ID:
        return

    msg = update.effective_message
    caption = msg.caption or ""
    video = msg.video or msg.document

    if not video or (msg.document and not msg.document.mime_type.startswith("video")):
        await msg.reply_text("Send a video file (as video or document).")
        return

    # Upload to channel
    sent = await context.bot.send_video(
        chat_id=CHANNEL_ID,
        video=video.file_id,
        caption=caption
    )

    file_id = sent.video.file_id if sent.video else video.file_id
    filename = getattr(video, "file_name", None)

    token = uuid.uuid4().hex
    save_video_to_db(token, file_id, filename, caption)

    long_url = f"https://t.me/{BASE_BOT_USERNAME}?start={token}"
    short = shorten_url(long_url)

    await msg.reply_text(
        f"🎬 Uploaded to channel!\n\n"
        f"🔗 Link: {short}\n"
        f"🆔 Token: {token}"
    )


# === MAIN ===
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(
        MessageHandler(
            filters.User(user_id=OWNER_CHAT_ID) & (filters.VIDEO | filters.Document.VIDEO),
            save_handler,
        )
    )

    logging.info("Bot starting...")
    app.run_polling(allowed_updates=["message", "edited_message"])


if __name__ == "__main__":
    main()
