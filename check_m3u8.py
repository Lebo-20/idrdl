import asyncio
import httpx
from api import get_play_url

async def main():
    book_id = "31001267802"
    chapter_id = "16502090" # Example from logs
    
    play_data = await get_play_url(chapter_id, book_id)
    if not play_data:
        print("No play data.")
        return
        
    multi = play_data.get("multiVideos", [])
    if not multi:
        print("No videos.")
        return
        
    m3u8_url = multi[0].get("filePath")
    print(f"M3U8 URL: {m3u8_url}")
    
    headers = {
        "Referer": "https://www.flickreels.net/",
        "Origin": "https://www.flickreels.net/",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(m3u8_url, headers=headers)
        print("M3U8 Content Head (first 500 chars):")
        print(resp.text[:500])
        
        # Count how many #EXTINF lines
        inf_count = resp.text.count("#EXTINF")
        print(f"Total Segments (#EXTINF): {inf_count}")

if __name__ == "__main__":
    asyncio.run(main())
