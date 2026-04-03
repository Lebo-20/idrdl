import asyncio
import logging
from api import get_hot_dramas, get_home_dramas, get_all_episodes, get_drama_detail

logging.basicConfig(level=logging.INFO)

async def check_all():
    hot = await get_hot_dramas() or []
    home = await get_home_dramas() or []
    all_dramas = hot + home
    
    unique_ids = set()
    for d in all_dramas:
        bid = d.get('bookId')
        if not bid or bid in unique_ids: continue
        unique_ids.add(bid)
        
        name = d.get('bookName')
        detail = await get_drama_detail(bid)
        expected = detail.get('book', {}).get('chapterCount', 0) if detail else "?"
        
        eps = await get_all_episodes(bid)
        found = len(eps)
        print(f"Drama: {name} ({bid}) -> Expected: {expected}, Found: {found}")
        if len(unique_ids) >= 10: break

if __name__ == "__main__":
    asyncio.run(check_all())
