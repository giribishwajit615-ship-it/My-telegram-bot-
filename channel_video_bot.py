# save as telegram_file_linker_bot.py
# Requirements:
#   pip install python-telegram-bot==20.6 (or latest v20+ compatible)
#   Python 3.10+

import logging
import sqlite3
import uuid
import os
from typing import List
from telegram import (
    Update,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaDocument,
    InputFile,
    Message,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
)

import os

# ---------------- CONFIG ----------------
BOT_TOKEN = "8222645012:AAEQMNK31oa5hDo_9OEStfNL7FMBdZMkUFM"       # <-- yahan apna bot token daalein
ADMIN_USER_ID = 7681308594                                 # <-- yahan apna numeric Telegram user id daalein
PRIVATE_CHANNEL_ID = "-1003292247930"                     # <-- yahan apna private channel ID daalein
# ----------------------------------------

if not BOT_TOKEN:
    raise RuntimeError("Please set BOT_TOKEN environment variable")
if ADMIN_USER_ID == 0:
    raise RuntimeError("Please set ADMIN_ID environment variable to your Telegram user id")
if not PRIVATE_CHANNEL_ID:
    raise RuntimeError("Please set PRIVATE_CHANNEL_ID environment variable to the channel id")

# logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ---------- DB helpers ----------
DBFILE = "filelinks.db"

def init_db():
    con = sqlite3.connect(DBFILE)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS links (
      token TEXT PRIMARY KEY,
      creator INTEGER,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS files (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      token TEXT,
      file_id TEXT,
      file_type TEXT,
      file_name TEXT,
      FOREIGN KEY(token) REFERENCES links(token)
    );
    """)
    con.commit()
    con.close()

def save_link(token: str, creator_id: int, file_entries: List[dict]):
    con = sqlite3.connect(DBFILE)
    cur = con.cursor()
    cur.execute("INSERT INTO links(token, creator) VALUES (?, ?)", (token, creator_id))
    for fe in file_entries:
        cur.execute(
            "INSERT INTO files(token, file_id, file_type, file_name) VALUES (?, ?, ?, ?)",
            (token, fe["file_id"], fe.get("file_type", "document"), fe.get("file_name"))
        )
    con.commit()
    con.close()

def get_files_for_token(token: str):
    con = sqlite3.connect(DBFILE)
    cur = con.cursor()
    cur.execute("SELECT file_id, file_type, file_name FROM files WHERE token = ? ORDER BY id ASC", (token,))
    rows = cur.fetchall()
    con.close()
    return [{"file_id": r[0], "file_type": r[1], "file_name": r[2]} for r in rows]

# ---------- Bot handlers ----------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # expecting deep-link: /start TOKEN
    args = context.args
    if not args:
        await update.message.reply_text("Namaste. Yeh file-store bot hai.")
        return
    token = args[0]
    files = get_files_for_token(token)
    if not files:
        await update.message.reply_text("Invalid ya expired link.")
        return

    # send files to the user
    # Try to send as media_group for <=10 compatible media types
    # Build media group when items are photos/videos/documents of supported types
    medias = []
    documents = []
    for f in files:
        fid = f["file_id"]
        ftype = f["file_type"] or "document"
        # We will treat all as documents for simplicity except photos/videos
        if ftype == "photo":
            medias.append(InputMediaPhoto(media=fid, caption=f.get("file_name") or ""))
        elif ftype == "video":
            medias.append(InputMediaVideo(media=fid, caption=f.get("file_name") or ""))
        else:
            documents.append(f)

    try:
        if 1 <= len(medias) <= 10 and not documents:
            # send as media_group
            await update.message.reply_media_group(medias)
        else:
            # send documents individually (works for any count)
            for d in files:
                try:
                    await update.message.bot.send_document(chat_id=update.effective_chat.id, document=d["file_id"], filename=d.get("file_name"))
                except Exception as e:
                    log.warning("Failed to send doc %s: %s", d, e)
    except Exception as e:
        log.exception("Error sending files: %s", e)
        await update.message.reply_text("Kuch error hua files bhejte waqt.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Avoid this message.")

async def incoming_files_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only accept from ADMIN_USER_ID
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("Sirf admin hi files upload kar sakta hai.")
        return

    # Collect attachments in this message. Could be single or multiple (media_group)
    msg: Message = update.message

    files_to_save = []

    # Photos
    if msg.photo:
        # photo is a list of sizes; pick largest
        largest = msg.photo[-1]
        # forward/copy to channel
        forwarded = await largest.get_file()
        # But better approach: forward the whole message to channel to preserve file_id
        sent_msg = await msg.forward(chat_id=PRIVATE_CHANNEL_ID)
        # After forward, extract file id from sent_msg
        if sent_msg.photo:
            fid = sent_msg.photo[-1].file_id
            files_to_save.append({"file_id": fid, "file_type": "photo", "file_name": None})

    # Documents (files)
    if msg.document:
        sent_msg = await msg.forward(chat_id=PRIVATE_CHANNEL_ID)
        if sent_msg.document:
            fid = sent_msg.document.file_id
            fname = sent_msg.document.file_name
            files_to_save.append({"file_id": fid, "file_type": "document", "file_name": fname})

    # Videos
    if msg.video:
        sent_msg = await msg.forward(chat_id=PRIVATE_CHANNEL_ID)
        if sent_msg.video:
            fid = sent_msg.video.file_id
            files_to_save.append({"file_id": fid, "file_type": "video", "file_name": None})

    # If the user sent a media group, python-telegram-bot may give them as separate messages. For safety, check if none collected but there are attachments in context.args etc.
    if not files_to_save:
        await update.message.reply_text("Koi valid file nahi mili. Kya aap file/document/photo bhej rahe the?")
        return

    # create token and save
    token = uuid.uuid4().hex  # long unique token; you can shorten
    save_link(token, user.id, files_to_save)

    # create deep-link
    bot_username = (await context.bot.get_me()).username
    deep_link = f"https://t.me/{bot_username}?start={token}"

    await update.message.reply_text(f"Link created: {deep_link}\nShare karo jis se file mil jaaye.")

# Admin helper to create link from recent channel message ids (optional)
async def make_link_from_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # optional command: /linkfrom <channel_message_id1> <channel_message_id2> ...
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("Sirf admin use kar sakta hai.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /linkfrom <message_id1> [message_id2 ...]")
        return
    files = []
    for mid in args:
        try:
            mid_i = int(mid)
            msg = await context.bot.get_chat(PRIVATE_CHANNEL_ID)
            # fetch message: getChat doesn't fetch messages. Telegram API has getMessage only for bots in PM. So this is left as advanced.
            # For simplicity respond that this feature needs additional implementation.
        except:
            continue
    await update.message.reply_text("Feature not implemented in this example. Use direct upload to bot.")

# ---------- main ----------
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("linkfrom", make_link_from_channel_message))
    # handle incoming files (documents, photos, videos)
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, incoming_files_handler))

    log.info("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
