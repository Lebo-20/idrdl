import os
import asyncio
import logging
import shutil
import tempfile
import re
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()

# Shared DB manager
from database import db

# Local imports for API/Processing
from api import (
    get_drama_detail, get_all_episodes, get_hot_dramas, get_home_dramas
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

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s ENGINE: %(levelname)s - %(message)s')
logger = logging.getLogger("ENGINE")

# Initialize client with its own session file
client = TelegramClient('dramabox_engine', API_ID, API_HASH)

async def download_worker():
    """Worker that picks up tasks from the database queue."""
    logger.info("👷 Workers engine started.")
    
    # Simple crash recovery: reset tasks stuck in status 1
    db.reset_processing_tasks()
    
    while True:
        task = db.get_next_task()
        if not task:
            await asyncio.sleep(5)
            continue
            
        task_id, book_id, title, chat_id, priority = task
        logger.info(f"⚡ [Queue] Processing task: {title} ({book_id}) - Priority {priority}")
        
        # Mark as processing (status 1)
        db.update_task_status(task_id, 1)
        
        status_msg = None
        # Usually for manual (P1), we want to send updates. For auto (P2), maybe just log or to channel.
        try:
            status_msg = await client.send_message(
                chat_id, 
                f"🎬 **Mulai Memproses**\n🎬 `{title}`\n🆔 `{book_id}`\n⏳ Mohon tunggu..."
            )
        except Exception as e:
            logger.warning(f"Failed to send start message for task: {e}")

        try:
            # Set a long timeout (10 hours) as requested
            success = await asyncio.wait_for(process_drama_full(book_id, chat_id, status_msg), timeout=36000)
            
            if success:
                db.add_processed(book_id)
                db.delete_task(task_id) # Task completed, remove or mark as finished
                logger.info(f"✅ Success processing {title}")
                try: await client.send_message(chat_id, f"✅ **Selesai:** {title}")
                except: pass
            else:
                logger.error(f"❌ Failed processing {title}")
                db.update_task_status(task_id, 3, "Download/Upload failed")
                try: await client.send_message(chat_id, f"❌ **Gagal:** {title}")
                except: pass
        except asyncio.TimeoutError:
            logger.error(f"⌛ Task {title} timed out after 10 hours.")
            db.update_task_status(task_id, 3, "Timed out")
        except Exception as e:
            logger.error(f"Worker Error: {e}")
            db.update_task_status(task_id, 3, str(e))
        finally:
            if status_msg:
                try: await status_msg.delete()
                except: pass
                
        await asyncio.sleep(2) # Brief rest between tasks

async def process_drama_full(book_id, chat_id, status_msg=None):
    """Core download/merge/upload logic."""
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
    title = re.sub(r'[\\/*?:"<>|]', "", title_raw) # Sanitize
    
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
        return upload_success
            
    except Exception as e:
        logger.error(f"Error processing {book_id}: {e}")
        try:
            if status_msg: await status_msg.edit(f"❌ Error: {e}")
        except: pass
        return False
    finally:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

async def auto_mode_loop():
    """Periodically check for new Hot and Home dramas."""
    logger.info("🔍 [Engine] Auto-detector started.")
    is_initial_run = True
    
    while True:
        try:
            interval = 5 if is_initial_run else 30 
            logger.info(f"🔍 [Engine] Scanning for new dramas...")
            
            hot_dramas = await get_hot_dramas() or []
            popular_dramas = await get_home_dramas() or []
            
            all_src = hot_dramas + popular_dramas
            added_count = 0
            
            for d in all_src:
                bid = str(d.get("bookId") or d.get("id") or d.get("action", ""))
                if not bid: continue
                
                # Check processed table
                if not db.is_processed(bid):
                    title = d.get("bookName") or d.get("tags") or d.get("title") or f"ID {bid}"
                    # Try to add to tasks table (will ignore if already queued)
                    if db.add_task(bid, title, AUTO_CHANNEL, priority=2):
                        logger.info(f"✨ New discovery: {title} ({bid})")
                        added_count += 1
            
            is_initial_run = False
            if added_count == 0:
                logger.debug("No new dramas this scan.")
            
            await asyncio.sleep(interval * 60)
            
        except Exception as e:
            logger.error(f"⚠️ Loop error: {e}")
            await asyncio.sleep(60)

async def main():
    logger.info("Initializing engine...")
    await client.start(bot_token=BOT_TOKEN)
    
    # Run both tasks concurrently
    await asyncio.gather(
        download_worker(),
        auto_mode_loop()
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
