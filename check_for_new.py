import asyncio
import json
from api import get_hot_dramas, get_home_dramas

async def main():
    with open("processed.json", "r") as f:
        processed = set(json.load(f))
    
    hot = await get_hot_dramas()
    home = await get_home_dramas()
    
    print(f"Hot: {len(hot)}, Home: {len(home)}")
    
    all_seen = []
    for d in hot + home:
        bid = str(d.get("bookId") or d.get("id") or d.get("action", ""))
        all_seen.append(bid)
        if bid not in processed:
             print(f"NEW FOUND: {bid} - {d.get('bookName') or d.get('tags')}")
        else:
             print(f"Already processed: {bid}")

if __name__ == "__main__":
    asyncio.run(main())
