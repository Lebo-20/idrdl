import asyncio
from api import search_dramas

async def main():
    query = "Gairah Terlarang"
    results = await search_dramas(query)
    if results:
        for res in results:
            print(f"Title: {res.get('bookName')}, ID: {res.get('bookId')}")
    else:
        print("No results found.")

if __name__ == "__main__":
    asyncio.run(main())
