import asyncio
import json
from api import get_drama_detail

async def main():
    book_id = "160000641134"
    detail = await get_drama_detail(book_id)
    if detail:
        print(f"Sample info: {json.dumps(detail['list'][0], indent=2)}")
    else:
        print("Detail not found.")

if __name__ == "__main__":
    asyncio.run(main())
