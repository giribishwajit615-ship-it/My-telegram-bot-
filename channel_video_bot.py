"""
Telegram Universal Storage & Share Bot
Public users can view shared files.
Only ADMIN_ID can upload new media.
"""

import os
import sqlite3
import logging
import datetime
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# ---------------- CONFIG ----------------
TOKEN = "8222645012:AAEQMNK31oa5hDo_9OEStfNL7FMBdZMkUFM"
BOT_USERNAME = "Cornsebot"
CHANNEL_ID = -1003292247930
ADMIN_ID = 7681308594
DATABASE_FILE = "bot_storage.db"
# -----------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------- SQLite Helper ---------------
def init_db(path: str = DATABASE_FILE):
    conn = sqlite3.connect(path, check_same_thread=False)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            file_id TEXT,
            text_content TEXT,
            uploader_id INTEGER NOT NULL,
            caption TEXT,
            title TEXT,
            views INTEGER DEFAULT 0,
            created_at TEXT
        )
        """
    )
    conn.commit()
    return conn


DB_CONN = init_db()

# ---------- DB Interaction ----------
def save_media(media_type: str, file_id: Optional[str], text_content: Optional[str],
               uploader_id: int, caption: Optional[str], title: Optional[str]) -> int:
    cur = DB_CONN.cursor()
    cur.execute(
        "INSERT INTO media (type, file_id, text_content, uploader_id, caption, title, views, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
        (media_type, file_id, text_content, uploader_id, caption, title, datetime.datetime.utcnow().isoformat()),
    )
    DB_CONN.commit()
    return cur.lastrowid


def get_media_by_id(media_id: int):
    cur = DB_CONN.cursor()
    cur.execute("SELECT * FROM media WHERE id=?", (media_id,))
    return cur.fetchone()


def increment_views(media_id: int):
    cur = DB_CONN.cursor()
    cur.execute("UPDATE media SET views = views + 1 WHERE id=?", (media_id,))
    DB_CONN.commit()


# ------------- Access Control -------------
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ------------- Handlers ----------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # Agar start ke sath argument hai -> jaise ?start=share_5
    if args and args[0].startswith("share_"):
        try:
            media_id = int(args[0].split("_")[1])
            record = get_media_by_id(media_id)
            if not record:
                await update.message.reply_text("❌ File not found.")
                return

            increment_views(media_id)

            media_type, file_id, text_content, _, caption, title, *_ = record[1:]
            if media_type == "text":
                await update.message.reply_text(text_content or "📄 Empty text.")
            elif media_type == "photo":
                await update.message.reply_photo(file_id, caption=caption or "")
            elif media_type == "video":
                await update.message.reply_video(file_id, caption=caption or "")
            elif media_type == "document":
                await update.message.reply_document(file_id, caption=caption or "")
            elif media_type == "audio":
                await update.message.reply_audio(file_id, caption=caption or "")
            else:
                await update.message.reply_text("❌ Unsupported media type.")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error loading file: {e}")
        return

    # Normal start message (for all users)
    await update.message.reply_text(
        f"👋 Hello {user.first_name or 'User'}!\n"
        "Send me a valid share link to access a file.\n\n"
        "If you're the admin, you can send media to store it."
    )


# ---------- Upload Handler (Admin Only) ----------
async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 Only admin can upload files.")
        return

    message = update.message
    file_id = None
    media_type = None

    if message.video:
        file_id = message.video.file_id
        media_type = "video"
    elif message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        media_type = "document"
    elif message.audio:
        file_id = message.audio.file_id
        media_type = "audio"
    elif message.text:
        file_id = None
        media_type = "text"
    else:
        await update.message.reply_text("⚠️ Unsupported media type.")
        return

    caption = message.caption or ""
    title = None

    media_id = save_media(media_type, file_id, message.text if media_type == "text" else None, user.id, caption, title)

    share_link = f"https://t.me/{BOT_USERNAME}?start=share_{media_id}"
    await update.message.reply_text(f"✅ Saved!\n🔗 Share link:\n{share_link}")


# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_upload))
    app.run_polling()


if __name__ == "__main__":
    main()
