"""
Telegram Video Storage & Share Bot
Single-file Python bot using python-telegram-bot v20 (asyncio).

Features:
- Users send a video to the bot (private chat). Bot uploads it to a private channel and stores metadata in SQLite.
- Bot returns a short deep-link share link: https://t.me/<BOT_USERNAME>?start=share_<id>
- Clicking the link makes the bot send the video directly (channel stays hidden).
- /start greets user.
- /stats and /allstats (admin only) show stored videos and views.
"""

import os
import sqlite3
import logging
import datetime
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# ---------------- CONFIG ----------------
TOKEN = "8222645012:AAEQMNK31oa5hDo_9OEStfNL7FMBdZMkUFM"
BOT_USERNAME = "Cornsebot"  # without @
CHANNEL_ID = -1003292247930  # your private channel ID
ADMIN_ID = 7681308594  # your Telegram user ID
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
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
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

# ---------- DB Interaction Functions ----------
def save_video(file_id: str, uploader_id: int, caption: Optional[str], title: Optional[str]) -> int:
    cur = DB_CONN.cursor()
    cur.execute(
        "INSERT INTO videos (file_id, uploader_id, caption, title, views, created_at) VALUES (?, ?, ?, ?, 0, ?)",
        (file_id, uploader_id, caption, title, datetime.datetime.utcnow().isoformat()),
    )
    DB_CONN.commit()
    return cur.lastrowid


def get_video_by_id(video_id: int):
    cur = DB_CONN.cursor()
    cur.execute("SELECT id, file_id, uploader_id, caption, title, views, created_at FROM videos WHERE id=?", (video_id,))
    return cur.fetchone()


def increment_views(video_id: int):
    cur = DB_CONN.cursor()
    cur.execute("UPDATE videos SET views = views + 1 WHERE id=?", (video_id,))
    DB_CONN.commit()


def get_stats_since(days: int = 1):
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat()
    cur = DB_CONN.cursor()
    cur.execute(
        "SELECT id, title, views, created_at FROM videos WHERE created_at >= ? ORDER BY created_at DESC",
        (cutoff,),
    )
    return cur.fetchall()


# ------------- Telegram Handlers ----------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or f"{user.first_name or ''} {user.last_name or ''}".strip()

    args = context.args if context.args else []
    if args and len(args) >= 1 and args[0].startswith("share_"):
        try:
            vid_id = int(args[0].split("share_")[-1])
        except Exception:
            await update.message.reply_text("Invalid share link.")
            return

        record = get_video_by_id(vid_id)
        if not record:
            await update.message.reply_text("Sorry, that video was not found or has been removed.")
            return

        file_id = record[1]
        title = record[4]
        caption = record[3]

        try:
            await context.bot.send_video(chat_id=update.effective_chat.id, video=file_id, caption=(title or caption or ""))
            increment_views(vid_id)
        except Exception as e:
            logger.exception("Error sending video to user: %s", e)
            await update.message.reply_text("Failed to send the video. Possibly the file was removed or is unavailable.")
            return

        await update.message.reply_text(f"Sent the video for you, {username} 👋")
        return

    await update.message.reply_text(f"Hello 👋, {username}")


async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    video = update.message.video
    document = update.message.document
    caption = update.message.caption or ""

    file_id = None
    title = None

    if video:
        file_id = video.file_id
        title = getattr(video, "file_name", None)
    elif document and document.mime_type and document.mime_type.startswith("video/"):
        file_id = document.file_id
        title = document.file_name
    else:
        await update.message.reply_text("Please send a video file (mp4/mkv) or as a document.")
        return

    vid_db_id = save_video(file_id, user.id, caption, title)

    try:
        await context.bot.send_video(chat_id=CHANNEL_ID, video=file_id, caption=f"Stored by bot. internal_id={vid_db_id}")
    except Exception as e:
        logger.warning("Failed to post to channel: %s", e)

    bot_username = BOT_USERNAME
    if bot_username == "YourBotUsername" or not bot_username:
        try:
            me = await context.bot.get_me()
            bot_username = me.username
        except Exception:
            bot_username = None

    if bot_username:
        share_link = f"https://t.me/{bot_username}?start=share_{vid_db_id}"
    else:
        share_link = f"Use this code with the bot: share_{vid_db_id}"

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="🔗 Open Share Link", url=share_link)]]
    )
    await update.message.reply_text(
        f"✅ Saved video (id={vid_db_id}).\n\nShare link:\n{share_link}\n\n"
        "Anyone clicking this link will receive the video directly (channel remains hidden).",
        reply_markup=keyboard,
    )


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    rows = get_stats_since(days=1)
    if not rows:
        await update.message.reply_text("No videos in the last 24 hours.")
        return

    lines = ["📊 Videos in the last 24 hours:"]
    for r in rows:
        vid_id, title, views, created_at = r
        lines.append(f"ID {vid_id} — {title or 'untitled'} — views: {views} — created: {created_at.split('T')[0]}")

    await update.message.reply_text("\n".join(lines))


async def allstats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    cur = DB_CONN.cursor()
    cur.execute("SELECT id, title, views, created_at FROM videos ORDER BY created_at DESC LIMIT 100")
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("No stored videos yet.")
        return

    lines = ["📁 Recent stored videos:"]
    for r in rows:
        lines.append(f"ID {r[0]} — {r[1] or 'untitled'} — views: {r[2]} — {r[3]}")

    await update.message.reply_text("\n".join(lines))


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Send a video directly to this bot — it will store it and give you a share link.\n\n"
        "🔗 Example: https://t.me/<bot_username>?start=share_<id>\n\n"
        "Admin commands:\n"
        "/stats or /dailystats — show today's stats\n"
        "/allstats — list all stored videos\n"
    )
    await update.message.reply_text(text)


async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I didn’t understand that. Send me a video or use /help.")


# ---------------------- Main ----------------------
def main():
    if not TOKEN or TOKEN.startswith("REPLACE"):
        print("Please set your bot TOKEN in the script before running.")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler(["stats", "dailystats"], stats_handler))
    application.add_handler(CommandHandler("allstats", allstats_handler))
    application.add_handler(CommandHandler("help", help_handler))

    # Handle video and documents that are videos
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, video_handler))

    # Catch all unknown messages
    application.add_handler(MessageHandler(filters.ALL, unknown_handler))

    print("🚀 Bot is starting...")
    application.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()
