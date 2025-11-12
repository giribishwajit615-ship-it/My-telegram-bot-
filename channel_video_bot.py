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
    InputFile,
    Message,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = "8222645012:AAEQMNK31oa5hDo_9OEStfNL7FMBdZMkUFM"       # <-- yahan apna bot token daalein
ADMIN_USER_ID = [7681308594, 8244432792]                        # <-- aap aur aapke dost ke numeric Telegram user id
PRIVATE_CHANNEL_ID = "-1003292247930"                           # <-- yahan apna private channel ID daalein
# ----------------------------------------

if not BOT_TOKEN:
    raise RuntimeError("Please set BOT_TOKEN environment variable")
if not ADMIN_USER_ID or len(ADMIN_USER_ID) == 0:
    raise RuntimeError("Please set ADMIN_USER_ID list to your Telegram numeric user ids")
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
    args = context.args
    if not args:
        await update.message.reply_text("Namaste. Yeh file-store bot hai.")
        return
    token = args[0]
    files = get_files_for_token(token)
    if not files:
        await update.message.reply_text("Invalid ya expired link.")
        return

    medias = []
    documents = []
    for f in files:
        fid = f["file_id"]
        ftype = f["file_type"] or "document"
        if ftype == "photo":
            medias.append(InputMediaPhoto(media=fid, caption=f.get("file_name") or ""))
        elif ftype == "video":
            medias.append(InputMediaVideo(media=fid, caption=f.get("file_name") or ""))
        else:
            documents.append(f)

    try:
        if 1 <= len(medias) <= 10 and not documents:
            await update.message.reply_media_group(medias)
        else:
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
    user = update.effective_user
    if user.id not in ADMIN_USER_ID:  # ✅ multi-admin fix
        await update.message.reply_text("Sirf admin hi files upload kar sakta hai.")
        return

    msg: Message = update.message
    files_to_save = []

    if msg.photo:
        sent_msg = await msg.forward(chat_id=PRIVATE_CHANNEL_ID)
        if sent_msg.photo:
            fid = sent_msg.photo[-1].file_id
            files_to_save.append({"file_id": fid, "file_type": "photo", "file_name": None})

    if msg.document:
        sent_msg = await msg.forward(chat_id=PRIVATE_CHANNEL_ID)
        if sent_msg.document:
            fid = sent_msg.document.file_id
            fname = sent_msg.document.file_name
            files_to_save.append({"file_id": fid, "file_type": "document", "file_name": fname})

    if msg.video:
        sent_msg = await msg.forward(chat_id=PRIVATE_CHANNEL_ID)
        if sent_msg.video:
            fid = sent_msg.video.file_id
            files_to_save.append({"file_id": fid, "file_type": "video", "file_name": None})

    if not files_to_save:
        await update.message.reply_text("Koi valid file nahi mili. Kya aap file/document/photo bhej rahe the?")
        return

    token = uuid.uuid4().hex
    save_link(token, user.id, files_to_save)
    bot_username = (await context.bot.get_me()).username
    deep_link = f"https://t.me/{bot_username}?start={token}"
    await update.message.reply_text(f"Link created: {deep_link}\nShare karo jis se file mil jaaye.")

async def make_link_from_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_USER_ID:  # ✅ multi-admin fix
        await update.message.reply_text("Sirf admin use kar sakta hai.")
        return
    await update.message.reply_text("Feature not implemented. Use direct upload to bot.")

# ---------- main ----------
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("linkfrom", make_link_from_channel_message))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, incoming_files_handler))

    log.info("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
