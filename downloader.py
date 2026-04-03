import os
import asyncio
import subprocess
import logging
import httpx
from api import get_play_url

logger = logging.getLogger(__name__)

async def download_m3u8(url: str, output_path: str, subtitle_url: str = None, retries: int = 3):
    """
    Downloads M3U8 stream to a single MP4 file using FFmpeg with internal retry mechanism.
    If subtitle_url is provided, it performs hardsubbing with specified styles.
    """
    headers_str = (
        "Referer: https://idrama.dramabos.my.id/\r\n"
    )
    user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"

    # Strip iDrama proxy if present, we'll use our own headers
    if url.startswith("https://idrama.dramabos.my.id/proxy?url="):
        from urllib.parse import unquote, urlparse, parse_qs
        parsed = urlparse(url)
        url = parse_qs(parsed.query).get('url', [url])[0]
        url = unquote(url)

    # Style configuration from user:
    # Font: Standard Symbols PS, Color: White, Size: 10, Bold, Outline: 1 (Black), Offset: 90
    style = (
        "Fontname=Standard Symbols PS,Fontsize=10,PrimaryColour=&HFFFFFF,"
        "Bold=1,Outline=1,OutlineColour=&H000000,MarginV=90"
    )

    for attempt in range(1, retries + 1):
        temp_sub = None
        try:
            command = [
                "ffmpeg", "-y",
                "-headers", headers_str,
                "-user_agent", user_agent,
                "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                "-allowed_extensions", "ALL",
                "-reconnect", "1",
                "-reconnect_at_eof", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
                "-i", url
            ]

            if subtitle_url:
                # Download subtitle to a temporary file
                temp_sub = output_path + ".srt"
                async with httpx.AsyncClient() as client:
                    sub_resp = await client.get(subtitle_url)
                    if sub_resp.status_code == 200:
                        with open(temp_sub, "wb") as f:
                            f.write(sub_resp.content)
                        
                        # Add subtitle filter - use libx264 for encoding as hardsubbing requires re-encoding
                        # Use -preset ultrafast for speed as requested
                        sub_path_fixed = temp_sub.replace('\\', '/')
                        command += [
                            "-vf", f"subtitles={sub_path_fixed}:force_style='{style}'",
                            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                            "-c:a", "aac"
                        ]
                    else:
                        logger.warning(f"Failed to download subtitle from {subtitle_url}")
                        command += ["-c", "copy"] # Fallback to copy if subtitle fails
            else:
                command += ["-c", "copy"]

            command += [
                "-bsf:a", "aac_adtstoasc",
                "-loglevel", "error",
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                if temp_sub and os.path.exists(temp_sub): os.remove(temp_sub)
                return True
            
            error_msg = stderr.decode().strip()
            logger.warning(f"Attempt {attempt} failed for {output_path}: {error_msg}")
        except Exception as e:
            logger.error(f"Error on attempt {attempt} downloading {output_path}: {e}")
        finally:
            if temp_sub and os.path.exists(temp_sub):
                try: os.remove(temp_sub)
                except: pass
        
        if attempt < retries:
            await asyncio.sleep(2 * attempt)
            
    return False

async def download_all_episodes(episodes: list, download_dir: str, semaphore_count: int = 3):
    """
    Downloads all episodes concurrently.
    """
    os.makedirs(download_dir, exist_ok=True)
    semaphore = asyncio.Semaphore(semaphore_count)

    async def single_task(ep_data: dict, index: int):
        """
        Local function that processes one episode independently.
        """
        # Ensure we bind local values early
        book_id = ep_data.get('bookId')
        # Some APIs use 'index' in data, if not use the loop index
        current_index = ep_data.get('index') or index
        
        # Format filename using local index
        ep_num_str = str(current_index).zfill(3)
        filename = f"episode_{ep_num_str}.mp4"
        filepath = os.path.join(download_dir, filename)

        async with semaphore:
            logger.info(f"🚀 Downloading episode {current_index} → {filename}")
            
            # Extract URL or fetch if missing
            play_info_list = ep_data.get('play_info_list', [])
            play_url = ep_data.get('play_url')
            final_url = None

            # Try to find subtitle list in ep_data or fetch it
            subtitle_list = ep_data.get('subtitle_list', [])

            if not play_info_list and not play_url and book_id:
                logger.info(f"Fetching play URL for locked episode {current_index}...")
                play_info = await get_play_url(book_id, current_index)
                if play_info:
                    play_info_list = play_info.get('play_info_list', [])
                    play_url = play_info.get('play_url')
                    if not subtitle_list:
                        subtitle_list = play_info.get('subtitle_list', [])
            if play_info_list:
                # Prioritize 720p or 1080p
                best = next((v for v in play_info_list if v.get('definition') == '720p'), None)
                if not best:
                    best = next((v for v in play_info_list if v.get('definition') == '1080p'), None)
                if not best:
                    # Filter out those with empty play_url
                    valid_list = [v for v in play_info_list if v.get('play_url')]
                    if valid_list:
                        best = valid_list[0]
                
                if best:
                    final_url = best.get('play_url')
                    
            if not final_url and play_url:
                final_url = play_url

            if not final_url:
                logger.error(f"❌ No URL found for episode {current_index}")
                return False

            # Extract subtitle URL if available
            subtitle_url = None
            if subtitle_list:
                # Prioritize Indonesian or English
                target_sub = next((s for s in subtitle_list if s.get('lang') == 'id'), None)
                if not target_sub:
                    target_sub = next((s for s in subtitle_list if s.get('lang') == 'en'), None)
                if not target_sub and subtitle_list:
                    target_sub = subtitle_list[0]
                
                if target_sub:
                    subtitle_url = target_sub.get('subtitle_url')

            # Wrap URL in local Proxy if needed, but for now try direct download
            success = await download_m3u8(final_url, filepath, subtitle_url=subtitle_url)
            
            if success:
                logger.info(f"✅ Downloaded: {filename}")
            else:
                logger.error(f"❌ FAILED after retries: {filename}")
            
            return success

    tasks = [single_task(ep, i+1) for i, ep in enumerate(episodes)]
    results = await asyncio.gather(*tasks)
    
    return all(results)
