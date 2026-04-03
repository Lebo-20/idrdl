import asyncio
import httpx
from api import get_play_url, BASE_URL

async def api_call(chapter_id, book_id, code=None):
    url = f"{BASE_URL}/play/{chapter_id}"
    params = {
        "bookId": book_id,
        "lang": "in"
    }
    if code:
        params["code"] = code
        
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
        multi = data.get("data", {}).get("multiVideos", [])
        if not multi: return None
        return multi[0].get("filePath")

async def check_duration(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        return resp.text.count("#EXTINF")

async def main():
    bid = "31001267802"
    cid = "16502090"
    
    url_no_code = await api_call(cid, bid)
    url_with_code = await api_call(cid, bid, "A8D6AB170F7B89F2182561D3B32F390D")
    
    print(f"URL NO CODE: {url_no_code}")
    print(f"URL WITH CODE: {url_with_code}")
    
    if url_no_code:
        dur_no = await check_duration(url_no_code)
        print(f"Duration No Code: {dur_no}")
    
    if url_with_code:
        dur_with = await check_duration(url_with_code)
        print(f"Duration With Code: {dur_with}")

if __name__ == "__main__":
    asyncio.run(main())
