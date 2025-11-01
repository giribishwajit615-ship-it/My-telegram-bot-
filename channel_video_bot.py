"""
Telegram Universal Storage & Share Bot (Admin Only)
Supports video, photo, document, audio, and text.
Only ADMIN_ID can use the bot.
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


def get_stats():
    cur = DB_CONN.cursor()
    cur.execute("SELECT COUNT(*), SUM(views) FROM media")
    total, views = cur.fetchone()
    # Top 5 most viewed
    cur.execute("SELECT id, type, views FROM media ORDER BY views DESC LIMIT 5")
    top = cur.fetchall()
    return total or 0, views or 0, top


def get_allstats():
    cur = DB_CONN.cursor()
    cur.execute("SELECT type, COUNT(*) FROM media GROUP BY type")
    rows = cur.fetchall()
    return rows

# ------------- Access Control -------------
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ------------- Handlers ----------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Restrict access
    if not is_admin(user.id):
        await update.message.reply_text("🚫 You are not authorized to use this bot.")
        return

    username = user.username or user.first_name or "User"
    args = context.args if context.args else []

    # If share link
    if args and len(args) >= 1 and args[0].startswith("share_"):
        try:
            mid = int(args[0].split("share_")[-1])
        except Exception:
            await update.message.reply_text("Invalid share link.")
            return

        record = get_media_by_id(mid)
        if not record:
            await update.message.reply_text("File not found or removed.")
            return

        _, mtype, file_id, text_content, uploader_id, caption, title, views, created_at = record

        try:
            if mtype == "video":
                await context.bot.send_video(update.effective_chat.id, file_id, caption=caption or title or "")
            elif mtype == "photo":
                await context.bot.send_photo(update.effective_chat.id, file_id, caption=caption or title or "")
            elif mtype == "document":
                await context.bot.send_document(update.effective_chat.id, file_id, caption=caption or title or "")
            elif mtype == "audio":
                await context.bot.send_audio(update.effective_chat.id, file_id, caption=caption or title or "")
            elif mtype == "text":
                await update.message.reply_text(text_content)
            else:
                await update.message.reply_text("Unknown media type.")
                return

            increment_views(mid)
        except Exception as e:
            logger.exception("Error sending media: %s", e)
            await update.message.reply_text("Failed to send media.")
            return

        await update.message.reply_text(f"✅ Sent the content for you, {username}")
        return

    await update.message.reply_text(f"Hello 👋, {username}\nSend me any photo, video, file, or text to get a share link.")


async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Restrict access
    if not is_admin(user.id):
        await update.message.reply_text("🚫 You are not authorized to use this bot.")
        return

    caption = update.message.caption or ""
    media_type = None
    file_id = None
    text_content = None
    title = None

    if update.message.video:
        media_type = "video"
        file_id = update.message.video.file_id
        title = getattr(update.message.video, "file_name", None)
    elif update.message.photo:
        media_type = "photo"
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        media_type = "document"
        file_id = update.message.document.file_id
        title = update.message.document.file_name
    elif update.message.audio:
        media_type = "audio"
        file_id = update.message.audio.file_id
        title = update.message.audio.file_name
    elif update.message.text:
        media_type = "text"
        text_content = update.message.text
    else:
        await update.message.reply_text("Unsupported message type.")
        return

    mid = save_media(media_type, file_id, text_content, user.id, caption, title)

    # Send to channel
    try:
        if media_type == "text":
            await context.bot.send_message(CHANNEL_ID, f"Stored text (id={mid}):\n{text_content}")
        elif media_type == "photo":
            await context.bot.send_photo(CHANNEL_ID, file_id, caption=f"Stored photo id={mid}")
        elif media_type == "video":
            await context.bot.send_video(CHANNEL_ID, file_id, caption=f"Stored video id={mid}")
        elif media_type == "document":
            await context.bot.send_document(CHANNEL_ID, file_id, caption=f"Stored doc id={mid}")
        elif media_type == "audio":
            await context.bot.send_audio(CHANNEL_ID, file_id, caption=f"Stored audio id={mid}")
    except Exception as e:
        logger.warning("Channel upload failed: %s", e)

    bot_username = BOT_USERNAME
    share_link = f"https://t.me/{bot_username}?start=share_{mid}"

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔗 Open Share Link", url=share_link)]]
    )

    await update.message.reply_text(
        f"✅ Saved ({media_type}) successfully.\nShare link:\n{share_link}",
        reply_markup=keyboard,
    )


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 You are not authorized to use this bot.")
        return

    total, views, top = get_stats()
    msg = f"📊 *Bot Stats*\n\n📦 Total Files: {total}\n👁️ Total Views: {views}\n\n🔥 *Top 5 Most Viewed:*\n"
    if not top:
        msg += "No media yet."
    else:
        for r in top:
            msg += f"• ID {r[0]} | {r[1].capitalize()} | {r[2]} views\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def allstats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 You are not authorized to use this bot.")
        return

    rows = get_allstats()
    msg = "📂 *Detailed Upload Stats:*\n\n"
    total = 0
    for t, count in rows:
        msg += f"• {t.capitalize()}: {count}\n"
        total += count
    msg += f"\n📦 Total Files: {total}"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 You are not authorized to use this bot.")
        return

    await update.message.reply_text(
        "📦 Send any photo, video, file, or text — I’ll store it privately and give you a share link!\n\n"
        "Commands:\n"
        "/stats - Show total uploads and most viewed media\n"
        "/allstats - Show detailed upload breakdown\n"
        "/help - Show this message"
    )


# -------------- Main ----------------
def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("stats", stats_handler))
    application.add_handler(CommandHandler("allstats", allstats_handler))
    application.add_handler(MessageHandler(filters.ALL, media_handler))
    print("🚀 Bot running...")
    application.run_polling()


if __name__ == "__main__":
    main()
