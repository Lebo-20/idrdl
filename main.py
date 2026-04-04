import os
import asyncio
import logging
import shutil
import tempfile
import random
import json
from telethon import TelegramClient, events, Button
from dotenv import load_dotenv

load_dotenv()

# Local imports
from api import (
    get_drama_detail, get_all_episodes, get_hot_dramas, get_home_dramas, search_dramas
)
from downloader import download_all_episodes
from merge import merge_episodes
from uploader import upload_drama

# Configuration
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
AUTO_CHANNEL = int(os.environ.get("AUTO_CHANNEL", ADMIN_ID))
PROCESSED_FILE = "processed.json"

# Initialize state
def load_processed():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r") as f:
                return set(json.load(f))
        except: pass
    return set()

def save_processed(data):
    with open(PROCESSED_FILE, "w") as f:
        json.dump(list(data), f)

processed_ids = load_processed()

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Bot State
class BotState:
    is_auto_running = True
    is_processing = False
    download_queue = asyncio.Queue()
    queued_ids = set() # To track items currently in the queue
    current_task_info = "Idle"

# Initialize client
client = TelegramClient('dramabox_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

def get_panel_buttons():
    status_text = "🟢 RUNNING" if BotState.is_auto_running else "🔴 STOPPED"
    queue_size = BotState.download_queue.qsize()
    return [
        [Button.inline("▶️ Start Auto", b"start_auto"), Button.inline("⏹ Stop Auto", b"stop_auto")],
        [Button.inline(f"📊 Status: {status_text}", b"status")],
        [Button.inline(f"⏳ Antrean: {queue_size} drama", b"status")]
    ]

@client.on(events.NewMessage(pattern=r'/update'))
async def update_bot(event):
    if event.sender_id != ADMIN_ID:
        await event.reply("❌ Perintah ini hanya untuk Admin utama.")
        return
    import subprocess
    import sys
    import os
    
    status_msg = await event.reply("🔄 Menarik pembaruan dari GitHub...")
    try:
        # Run git pull
        result = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True)
        if "Already up to date" in result.stdout and "--force" not in event.text:
             await status_msg.edit(f"✅ Sudah yang terbaru:\n```\n{result.stdout}\n```")
             return

        await status_msg.edit(f"✅ Repositori berhasil di-pull:\n```\n{result.stdout}\n```\n\nSedang memulai ulang sistem...")
        
        # Disconnect client properly before restart
        await client.disconnect()

        # Robust restart for Windows/Linux
        if os.name == 'nt':
            # On Windows, spawning a new process and exiting the old one is often more reliable
            subprocess.Popen([sys.executable] + sys.argv)
            sys.exit()
        else:
            # Unix-like
            os.execl(sys.executable, sys.executable, *sys.argv)
            
    except Exception as e:
        logger.error(f"Update error: {e}")
        try: await status_msg.edit(f"❌ Gagal melakukan update: {e}")
        except: pass

@client.on(events.NewMessage(pattern='/panel'))
async def panel(event):
    if event.chat_id != ADMIN_ID:
        return
    await event.reply("🎛 **iDrama Bot Control Panel**", buttons=get_panel_buttons())

@client.on(events.CallbackQuery())
async def panel_callback(event):
    if event.sender_id != ADMIN_ID:
        return
        
    data = event.data
    
    try:
        if data == b"start_auto":
            BotState.is_auto_running = True
            await event.answer("Auto-mode started!")
            await event.edit("🎛 **iDrama Bot Control Panel**", buttons=get_panel_buttons())
        elif data == b"stop_auto":
            BotState.is_auto_running = False
            await event.answer("Auto-mode stopped!")
            await event.edit("🎛 **iDrama Bot Control Panel**", buttons=get_panel_buttons())
        elif data == b"status":
            await event.answer(f"Status: {'Running' if BotState.is_auto_running else 'Stopped'}")
            await event.edit("🎛 **iDrama Bot Control Panel**", buttons=get_panel_buttons())
        elif data.startswith(b"dl_"):
            book_id = data.decode().split("_")[1]
            await event.answer("Starting download...")
            # Trigger download logic (similar to /download command but as a task)
            asyncio.create_task(handle_one_download(event.chat_id, book_id))
    except Exception as e:
        if "message is not modified" in str(e).lower(): pass
        else: logger.error(f"Callback error: {e}")

async def download_worker():
    """Background worker that processes the download queue one by one."""
    global processed_ids
    logger.info("👷 Download worker started.")
    while True:
        try:
            # item is a dict: {'chat_id': ..., 'book_id': ..., 'title': ..., 'status_msg': ...}
            item = await BotState.download_queue.get()
            chat_id = item['chat_id']
            book_id = item['book_id']
            title = item.get('title', f'ID {book_id}')
            status_msg = item.get('status_msg')
            
            BotState.is_processing = True
            BotState.current_task_info = f"Processing {title}"
            
            logger.info(f"⚡ [Queue] Processing task: {title} ({book_id})")
            
            # If no status_msg was provided (auto-mode), create a start message
            if not status_msg:
                try:
                    status_msg = await client.send_message(
                        chat_id, 
                        f"🎬 **Mulai Memproses (Antrean)**\n🎬 `{title}`\n🆔 `{book_id}`\n⏳ Mohon tunggu..."
                    )
                except: pass

            success = await process_drama_full(book_id, chat_id, status_msg)
            
            if success:
                processed_ids.add(book_id)
                save_processed(processed_ids)
                logger.info(f"✅ Success processing {title}")
                try: await client.send_message(chat_id, f"✅ **Selesai:** {title}")
                except: pass
            else:
                logger.error(f"❌ Failed processing {title}")
                # We don't add to processed_ids if it failed, so it can be re-scanned/re-queued
                try: await client.send_message(chat_id, f"❌ **Gagal:** {title}")
                except: pass
                
            # Delete status message if it survived
            if status_msg:
                try: await status_msg.delete()
                except: pass

        except Exception as e:
            logger.error(f"Worker Error: {e}")
        finally:
            # Remove from queued tracking regardless of success/fail
            if 'book_id' in item:
                BotState.queued_ids.discard(item['book_id'])
            
            BotState.is_processing = False
            BotState.current_task_info = "Idle"
            BotState.download_queue.task_done()
            await asyncio.sleep(2) # Brief rest between tasks

async def handle_one_download(chat_id, book_id, title=None):
    """Adds a drama to the download queue."""
    # Check if already processed
    if book_id in processed_ids:
        await client.send_message(chat_id, f"✅ Drama `{book_id}` sudah pernah diproses sebelumnya.")
        return

    # Check if currently in queue
    if book_id in BotState.queued_ids:
        await client.send_message(chat_id, f"🕒 Drama `{book_id}` sedang dalam antrean. Mohon bersabar.")
        return
    
    # Mark as queued
    BotState.queued_ids.add(book_id)
    
    queue_size = BotState.download_queue.qsize()
    status_text = "Sedang diproses..." if BotState.is_processing and queue_size == 0 else f"Masuk antrean ke-{queue_size + 1}"
    
    msg = await client.send_message(chat_id, f"📥 **Pesan Diterima**\n🆔 `{book_id}`\n📊 Status: {status_text}")
    
    # Put in queue
    await BotState.download_queue.put({
        'chat_id': chat_id,
        'book_id': book_id,
        'title': title or f"ID {book_id}",
        'status_msg': msg
    })

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("Welcome to iDrama Downloader Bot! 🎉\n\nGunakan perintah:\n🔍 `/cari {judul}` - Mencari drama\n📽 `/download {bookId}` - Download ID drama tertentu.")

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
    # Limit to 10 results for clarity
    for item in results[:10]:
        title = item.get("bookName") or item.get("title") or "Unknown"
        bid = item.get("bookId") or item.get("id")
        if bid:
            buttons.append([Button.inline(f"🎬 {title[:40]}", f"dl_{bid}")])
            
    await status.edit(f"✅ Ditemukan {len(buttons)} hasil untuk **{query}**:", buttons=buttons)

@client.on(events.NewMessage(pattern=r'/download\s+(\w+)'))
async def on_download(event):
    chat_id = event.chat_id
    if chat_id != ADMIN_ID:
        await event.reply("❌ Maaf, perintah ini hanya untuk admin.")
        return
        
    if BotState.is_processing:
        await event.reply("⚠️ Sedang memproses drama lain.")
        return
        
    book_id = event.pattern_match.group(1).strip()
    logger.info(f"Manual download triggered for ID: {book_id}")
    await handle_one_download(chat_id, book_id)

async def process_drama_full(book_id, chat_id, status_msg=None):
    """Refactored logic for iDrama API."""
    data_full = await get_drama_detail(book_id)
    if not data_full:
        if status_msg: await status_msg.edit(f"❌ Detail drama `{book_id}` tidak ditemukan.")
        return False
        
    book_data = data_full.get("book", {})
    episodes = await get_all_episodes(book_id)
    if not episodes:
        episodes = data_full.get("list", [])
        
    if not episodes:
        if status_msg: await status_msg.edit(f"❌ Episode drama `{book_id}` tidak ditemukan.")
        return False

    title_raw = book_data.get("bookName") or f"Drama_{book_id}"
    # Sanitize title for filename
    import re
    title = re.sub(r'[\\/*?:"<>|]', "", title_raw)
    
    description = book_data.get("introduction") or "No description."
    poster = book_data.get("cover") or ""
    
    temp_dir = tempfile.mkdtemp(prefix=f"idrama_{book_id}_")
    video_dir = os.path.join(temp_dir, "episodes")
    os.makedirs(video_dir, exist_ok=True)
    
    try:
        if status_msg: await status_msg.edit(f"🎬 Processing **{title}** (iDrama)...")
        
        # Download
        success = await download_all_episodes(episodes, video_dir)
        if not success:
            if status_msg: await status_msg.edit("❌ Download Gagal.")
            return False

        # Merge
        # Ensure title used here is the sanitized version
        output_video_path = os.path.join(temp_dir, f"{title}.mp4")
        merge_success = merge_episodes(video_dir, output_video_path)
        if not merge_success:
            if status_msg: await status_msg.edit("❌ Merge Gagal.")
            return False

        # Upload
        upload_success = await upload_drama(
            client, chat_id, 
            title, description, 
            poster, output_video_path,
            book_id=book_id
        )
        
        if upload_success:
            return True
        else:
            if status_msg: await status_msg.edit("❌ Upload Gagal.")
            return False
            
    except Exception as e:
        logger.error(f"Error processing {book_id}: {e}")
        if status_msg: await status_msg.edit(f"❌ Error: {e}")
        return False
    finally:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

async def auto_mode_loop():
    """Logic to periodically check for Hot and Home dramas."""
    global processed_ids
    
    is_initial_run = True
    
    while True:
        if not BotState.is_auto_running:
            await asyncio.sleep(5)
            continue
            
        try:
            interval = 5 if is_initial_run else 30 
            logger.info(f"🔍 [iDrama] Scanning for new dramas...")
            
            hot_dramas = await get_hot_dramas() or []
            popular_dramas = await get_home_dramas() or []
            
            all_new = []
            seen_in_scan = set()
            
            for d in hot_dramas + popular_dramas:
                bid = str(d.get("bookId") or d.get("id") or d.get("action", ""))
                if bid and bid not in processed_ids and bid not in seen_in_scan:
                    all_new.append(d)
                    seen_in_scan.add(bid)
            
            if not all_new:
                logger.info("😴 No new dramas found.")
                is_initial_run = False
                await asyncio.sleep(interval * 60)
                continue

            for drama in all_new:
                if not BotState.is_auto_running: break
                
                bid = str(drama.get("bookId") or drama.get("id") or drama.get("action", ""))
                title = drama.get("bookName") or drama.get("tags") or drama.get("title") or "Unknown"
                
                logger.info(f"✨ New discovery added to queue: {title} ({bid})")
                
                # Push to queue instead of processing directly
                BotState.queued_ids.add(bid) # Prevent scanning it back while in queue
                
                await BotState.download_queue.put({
                    'chat_id': AUTO_CHANNEL,
                    'book_id': bid,
                    'title': title,
                    'status_msg': None
                })
                
                await asyncio.sleep(2)
            
            is_initial_run = False
            await asyncio.sleep(interval * 60)
            
        except Exception as e:
            logger.error(f"⚠️ Loop error: {e}")
            await asyncio.sleep(60)

if __name__ == '__main__':
    logger.info("iDrama Bot Active.")
    client.loop.create_task(auto_mode_loop())
    client.loop.create_task(download_worker())
    client.run_until_disconnected()
