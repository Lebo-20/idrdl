import os
import asyncio
import logging
import json
from telethon import TelegramClient, events, Button
from dotenv import load_dotenv

load_dotenv()

# Shared DB manager
from database import db

# API imports
from api import search_dramas

# Configuration
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s ADMIN: %(levelname)s - %(message)s')
logger = logging.getLogger("ADMIN")

# Initialize client
client = TelegramClient('dramabox_admin', API_ID, API_HASH)

def get_panel_buttons():
    stats = db.get_queue_stats()
    active = db.get_active_task_info()
    return [
        [Button.inline(f"📋 Status Queue: {stats['pending']} pending", b"noop")],
        [Button.inline(f"👷 Worker: {active}", b"noop")],
        [Button.inline("🔄 Refresh Status", b"refresh_status")],
        [Button.inline("🗑 Clear Completed (DB Cleanup)", b"cleanup")]
    ]

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply(
        "👋 **iDrama BOT Admin Console [SPLIT PROCESS]**\n\n"
        "🔍 `/cari {judul}` - Mencari drama\n"
        "📽 `/download {id}` - Request download manual\n"
        "📊 `/status` - Cek antrean\n"
        "🎛 `/panel` - Dashboard admin"
    )

@client.on(events.NewMessage(pattern=r'/cari (.*)'))
async def on_search(event):
    query = event.pattern_match.group(1).strip()
    if not query:
        await event.reply("❌ Masukkan judul drama. Contoh: `/cari istri ceo`")
        return
        
    status = await event.reply(f"🔍 Mencari drama: **{query}**...")
    results = await search_dramas(query)
    
    if not results:
        await status.edit(f"❌ Tidak ditemukan hasil untuk `{query}`.")
        return
        
    buttons = []
    # Limit results
    for item in results[:10]:
        title = item.get("bookName") or item.get("title") or "Unknown"
        bid = item.get("bookId") or item.get("id")
        if bid:
            buttons.append([Button.inline(f"🎬 {title[:40]}", f"dl_{bid}")])
            
    await status.edit(f"✅ Ditemukan {len(buttons)} hasil untuk **{query}**:", buttons=buttons)

@client.on(events.NewMessage(pattern=r'/download\s+(\w+)'))
async def on_download(event):
    if event.sender_id != ADMIN_ID: return
        
    book_id = event.pattern_match.group(1).strip()
    if db.is_processed(book_id):
        await event.reply(f"⚠️ Drama ID `{book_id}` sudah pernah diproses.")
        return
        
    # Queue task with Priority 1 (Manual)
    # We don't have the title yet, but the engine will fetch it from API
    if db.add_task(book_id, f"Manual Request ID {book_id}", event.chat_id, priority=1):
        await event.reply(f"📥 **Antrean Diterima**\n🆔 `{book_id}`\n📊 Status: Menunggu antrean (Prioritas Manual)")
    else:
        await event.reply(f"🕒 Drama `{book_id}` sudah ada di antrean.")

@client.on(events.NewMessage(pattern='/status'))
async def check_queue(event):
    stats = db.get_queue_stats()
    active = db.get_active_task_info()
    msg = (
        f"📊 **BOT STATUS**\n"
        f"⏳ Pending: `{stats['pending']}` drama\n"
        f"👷 Current Task: `{active}`\n"
    )
    await event.reply(msg)

@client.on(events.NewMessage(pattern='/panel'))
async def panel(event):
    if event.sender_id != ADMIN_ID: return
    await event.reply("🎛 **iDrama BOT Control Panel [ADMIN PROCESS]**", buttons=get_panel_buttons())

@client.on(events.NewMessage(pattern=r'/update'))
async def update_bot(event):
    if event.sender_id != ADMIN_ID: return
    import subprocess
    import sys
    
    status_msg = await event.reply("🔄 [ADMIN] Pulling updates from GitHub...")
    try:
        result = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True)
        await status_msg.edit(f"✅ Pull results:\n`{result.stdout}`\n\n**Note:** Silakan restart manual script `engine.py` dan `admin.py` atau jalankan `start_all.bat`.")
    except Exception as e:
        await status_msg.edit(f"❌ Pull error: {e}")

@client.on(events.CallbackQuery())
async def handle_callback(event):
    data = event.data
    
    if data.startswith(b"dl_"):
        book_id = data.decode().split("_")[1]
        if db.add_task(book_id, f"Manual ID {book_id}", event.chat_id, priority=1):
            await event.answer("📥 Berhasil ditambahkan ke antrean (Manual)")
        else:
            await event.answer("⚠️ Sudah ada di antrean.")
            
    elif data == b"refresh_status":
        await event.edit("🎛 **iDrama BOT Panel Updated**", buttons=get_panel_buttons())
        await event.answer("Refreshed.")
        
    elif data == b"cleanup":
        # Usually for manual DB cleanup of old failed tasks
        # Or just clear status 3
        # For now just no-op or simple feedback
        await event.answer("Cleanup triggered (Optional implementation)")
        
    elif data == b"noop":
        await event.answer()

async def main():
    logger.info("Initializing Admin process...")
    await client.start(bot_token=BOT_TOKEN)
    logger.info("Admin bot is online. Listening for commands.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
