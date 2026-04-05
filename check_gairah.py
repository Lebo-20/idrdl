import asyncio
import json
from api import get_drama_detail

async def main():
    book_id = "160000641134"
    detail = await get_drama_detail(book_id)
    if detail:
        # print(json.dumps(detail, indent=2))
        print(f"Title: {detail['book'].get('bookName')}")
        print(f"Total Episodes: {len(detail['list'])}")
        if detail['list']:
            first_ep = detail['list'][0]
            print(f"First Ep Sample: index={first_ep.get('index')}, name={first_ep.get('episode_name')}")
            print(f"Play URL present: {bool(first_ep.get('play_url'))}")
            # print(f"Sample info: {first_ep}")
    else:
        print("Detail not found.")

if __name__ == "__main__":
    asyncio.run(main())
