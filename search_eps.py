import asyncio
from api import search_dramas, get_all_episodes

async def main():
    queries = ["cinta", "ceo", "boss"]
    for q in queries:
        dramas = await search_dramas(q)
        for d in dramas[:5]:
            bid = str(d.get("bookId") or d.get("id"))
            name = d.get("bookName")
            eps = await get_all_episodes(bid)
            print(f"[{name}] ID: {bid}, Episodes: {len(eps)}")

if __name__ == "__main__":
    asyncio.run(main())
