# file: channel_video_bot.py  
# Requirements: python >= 3.9, python-telegram-bot>=20, requests  
  
import uuid  
import sqlite3  
import requests  
import logging  
import datetime  
from telegram import Update  
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters  
  
# === CONFIG ===  
BOT_TOKEN = "8222645012:AAEQMNK31oa5hDo_9OEStfNL7FMBdZMkUFM"  
ADRINO_SHORTEN_API = "https://adrinolinks.in/api"  
ADRINO_API_KEY = "5b33540e7eaa148b24b8cca0d9a5e1b9beb3e634"  
BASE_BOT_USERNAME = "Cornsebot"  # without @  
OWNER_CHAT_ID = 7681308594  
  
DB_PATH = "videos.db"  
  
# === INIT DB ===  
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
    c.execute("""  
        CREATE TABLE IF NOT EXISTS users (  
            user_id INTEGER PRIMARY KEY,  
            token TEXT,  
            first_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP  
        )  
    """)  
    c.execute("""  
        CREATE TABLE IF NOT EXISTS views (  
            id INTEGER PRIMARY KEY AUTOINCREMENT,  
            user_id INTEGER,  
            token TEXT,  
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  
        )  
    """)  
    conn.commit()  
    conn.close()  
  
# === SHORTENER ===  
def shorten_url(long_url: str) -> str:  
    payload = {"api_key": ADRINO_API_KEY, "url": long_url}  
    try:  
        r = requests.post(ADRINO_SHORTEN_API, json=payload, timeout=8)  
        r.raise_for_status()  
        data = r.json()  
        short = data.get("short") or data.get("short_url") or data.get("result")  
        return short or long_url  
    except Exception:  
        logging.exception("Shortener failed")  
        return long_url  
  
# === HANDLERS ===  
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):  
    args = context.args  
    user_id = update.effective_user.id  
  
    if not args:  
        await update.message.reply_text("👋 Hello! Use the special link to get your video.")  
        return  
  
    token = args[0]  
    conn = sqlite3.connect(DB_PATH)  
    c = conn.cursor()  
    c.execute("SELECT first_used FROM users WHERE user_id = ?", (user_id,))  
    row = c.fetchone()  
    now = datetime.datetime.utcnow()  
  
    if row:  
        first_used = datetime.datetime.fromisoformat(row[0])  
        if now - first_used > datetime.timedelta(hours=24):  
            c.execute("UPDATE users SET token=?, first_used=? WHERE user_id=?", (token, now.isoformat(), user_id))  
        else:  
            c.execute("SELECT file_id, caption FROM videos WHERE token = ?", (token,))  
            v = c.fetchone()  
            conn.close()  
            if v:  
                await context.bot.send_video(chat_id=user_id, video=v[0], caption=v[1] or "")  
                conn2 = sqlite3.connect(DB_PATH)  
                conn2.execute("INSERT INTO views (user_id, token) VALUES (?, ?)", (user_id, token))  
                conn2.commit()  
                conn2.close()  
            return  
    else:  
        c.execute("INSERT INTO users (user_id, token, first_used) VALUES (?, ?, ?)", (user_id, token, now.isoformat()))  
  
    c.execute("SELECT file_id, caption FROM videos WHERE token = ?", (token,))  
    v = c.fetchone()  
    conn.commit()  
    conn.close()  
  
    if not v:  
        await update.message.reply_text("❌  expired video link.")  
