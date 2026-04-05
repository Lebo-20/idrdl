import os
import asyncio
import logging
import shutil
import tempfile
import re
import json
import sqlite3
import multiprocessing
from telethon import TelegramClient, events, Button
from dotenv import load_dotenv

load_dotenv()

# Configuration
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
AUTO_CHANNEL = int(os.environ.get("AUTO_CHANNEL", ADMIN_ID))
DB_PATH = "bot_data.db"

# Local imports
from api import (
    get_drama_detail, get_all_episodes, get_hot_dramas, get_home_dramas, search_dramas
)
from downloader import download_all_episodes
from merge import merge_episodes
from uploader import upload_drama

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger("MAIN")

# --- DATABASE LAYER ---
class Database:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS processed (book_id TEXT PRIMARY KEY)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT UNIQUE,
                    title TEXT,
                    chat_id INTEGER,
                    priority INTEGER,
                    status INTEGER DEFAULT 0,
                    error_msg TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def is_processed(self, book_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT 1 FROM processed WHERE book_id = ?", (str(book_id),))
            return cursor.fetchone() is not None

    def add_processed(self, book_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO processed (book_id) VALUES (?)", (str(book_id),))
            conn.commit()

    def add_task(self, book_id, title, chat_id, priority=2):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("INSERT INTO tasks (book_id, title, chat_id, priority, status) VALUES (?, ?, ?, ?, 0)", 
                            (str(book_id), title, chat_id, priority))
                conn.commit()
                return True
        except sqlite3.IntegrityError: return False

    def get_next_task(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id, book_id, title, chat_id, priority FROM tasks WHERE status = 0 ORDER BY priority ASC, created_at ASC LIMIT 1")
            return cursor.fetchone()

    def update_task_status(self, task_id, status, error_msg=None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE tasks SET status = ?, error_msg = ? WHERE id = ?", (status, error_msg, task_id))
            conn.commit()

    def delete_task(self, task_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()

    def reset_processing_tasks(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE tasks SET status = 0 WHERE status = 1")
            conn.commit()

    def get_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            pending = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 0").fetchone()[0]
            active = conn.execute("SELECT title FROM tasks WHERE status = 1 LIMIT 1").fetchone()
            return {"pending": pending, "active": active[0] if active else "Idle"}

db = Database()

# --- ENGINE LOGIC (Process 1) ---
async def process_drama_full(client, book_id, chat_id, status_msg=None):
    data_full = await get_drama_detail(book_id)
    if not data_full: return False
    
    book_data = data_full.get("book", {})
    episodes = await get_all_episodes(book_id) or data_full.get("list", [])
    if not episodes: return False

    title_raw = book_data.get("bookName") or f"Drama_{book_id}"
    title = re.sub(r'[\\/*?:"<>|]', "", title_raw)
    temp_dir = tempfile.mkdtemp(prefix=f"idrama_{book_id}_")
    video_dir = os.path.join(temp_dir, "episodes")
    os.makedirs(video_dir, exist_ok=True)
    
    try:
        if status_msg: await status_msg.edit(f"🎬 Processing **{title}**...")
        if not await download_all_episodes(episodes, video_dir): return False
        output_video_path = os.path.join(temp_dir, f"{title}.mp4")
        if not merge_episodes(video_dir, output_video_path): return False
        return await upload_drama(client, chat_id, title, book_data.get("introduction", ""), book_data.get("cover", ""), output_video_path, book_id=book_id)
    finally:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

async def download_worker(client):
    logger.info("👷 Worker started.")
    db.reset_processing_tasks()
    while True:
        task = db.get_next_task()
        if not task:
            await asyncio.sleep(5)
            continue
        tid, bid, title, cid, prio = task
        db.update_task_status(tid, 1)
        status_msg = await client.send_message(cid, f"🎬 **Mulai Memproses**\n🎬 `{title}`\n🆔 `{bid}`")
        try:
            if await asyncio.wait_for(process_drama_full(client, bid, cid, status_msg), timeout=36000):
                db.add_processed(bid)
                db.delete_task(tid)
                await client.send_message(cid, f"✅ **Selesai:** {title}")
            else:
                db.update_task_status(tid, 3, "Failed")
                await client.send_message(cid, f"❌ **Gagal:** {title}")
        except Exception as e:
            db.update_task_status(tid, 3, str(e))
        finally:
            try: await status_msg.delete()
            except: pass
        await asyncio.sleep(2)

async def auto_mode_loop():
    logger.info("🔍 Auto-detector started.")
    while True:
        try:
            hot = await get_hot_dramas() or []
            home = await get_home_dramas() or []
            for d in (hot + home):
                bid = str(d.get("bookId") or d.get("id") or d.get("action", ""))
                if bid and not db.is_processed(bid):
                    title = d.get("bookName") or d.get("title") or f"ID {bid}"
                    if db.add_task(bid, title, AUTO_CHANNEL, priority=2):
                        logger.info(f"✨ New discovery added to queue: {title}")
            await asyncio.sleep(30 * 60)
        except Exception as e:
            logger.error(f"Loop Error: {e}")
            await asyncio.sleep(60)

def run_auto_process():
    """Target function for auto/worker process."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def _main():
        client = TelegramClient('session_auto', API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ ENGINE (Auto & Worker) is online.")
        await asyncio.gather(download_worker(client), auto_mode_loop())
    
    loop.run_until_complete(_main())

# --- ADMIN LOGIC (Process 2) ---
def run_admin_process():
    """Target function for admin commands process."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def _main():
        client = TelegramClient('session_admin', API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ ADMIN (Commands) is online.")

        @client.on(events.NewMessage(pattern='/start'))
        async def h_start(event):
            await event.reply("🔍 `/cari {judul}`\n📽 `/download {id}`\n📊 `/status`")

        @client.on(events.NewMessage(pattern=r'/cari (.*)'))
        async def h_search(event):
            query = event.pattern_match.group(1).strip()
            res = await search_dramas(query)
            if not res: return await event.reply("❌ Tidak ditemukan.")
            btns = [[Button.inline(f"🎬 {r.get('bookName')[:40]}", f"dl_{r.get('bookId')}")] for r in res[:10]]
            await event.reply(f"✅ Hasil search `{query}`:", buttons=btns)

        @client.on(events.NewMessage(pattern=r'/download\s+(\w+)'))
        async def h_dl(event):
            if event.sender_id != ADMIN_ID: return
            bid = event.pattern_match.group(1).strip()
            if db.is_processed(bid): return await event.reply("✅ Drama sudah pernah diproses.")
            if db.add_task(bid, f"Manual ID {bid}", event.chat_id, priority=1):
                await event.reply(f"📥 Masuk antrean manual (Prio High).")
            else: await event.reply("🕒 Sudah ada dalam antrean.")

        @client.on(events.NewMessage(pattern='/status'))
        async def h_status(event):
            s = db.get_stats()
            await event.reply(f"📊 **STATUS ANTREAN**\n⏳ Menunggu: `{s['pending']}`\n👷 Aktif: `{s['active']}`")

        @client.on(events.CallbackQuery())
        async def h_cb(event):
            if event.data.startswith(b"dl_"):
                bid = event.data.decode().split("_")[1]
                if db.add_task(bid, f"ID {bid}", event.chat_id, priority=1):
                    await event.answer("📥 Berhasil ditambahkan!")
                else: await event.answer("⚠️ Sudah ada di antrean.")

        await client.run_until_disconnected()
    
    loop.run_until_complete(_main())

# --- MAIN ENTRY POINT ---
if __name__ == '__main__':
    # Start both processes from single python main.py command
    p1 = multiprocessing.Process(target=run_auto_process, name="AutoProcess")
    p2 = multiprocessing.Process(target=run_admin_process, name="AdminProcess")
    
    p1.start()
    p2.start()
    
    logger.info("🚀 Dual-process system started (Auto + Admin).")
    
    try:
        p1.join()
        p2.join()
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
        p1.terminate()
        p2.terminate()
