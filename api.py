import httpx
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://idrama.dramabos.my.id"
AUTH_CODE = "A8D6AB170F7B89F2182561D3B32F390D"

async def get_drama_detail(book_id: str):
    """Fetch drama detail and episodes from the new iDrama API."""
    url = f"{BASE_URL}/drama/{book_id}"
    params = {
        "lang": "id",
        "code": AUTH_CODE
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                # Wrap the flat response in a 'book' key for compatibility with main.py
                # Use 'short_play_name' and other fields accurately from the JSON
                data["bookName"] = data.get("short_play_name")
                data["cover"] = data.get("cover_url")
                data["introduction"] = data.get("introduction")
                
                episodes = data.get("episode_list", [])
                for ep in episodes:
                    ep["bookId"] = book_id
                
                return {
                    "book": data,
                    "list": episodes
                }
            return None
        except Exception as e:
            logger.error(f"Error fetching drama detail for {book_id}: {e}")
            return None

async def get_all_episodes(book_id: str):
    """Fetch episodes list. In iDrama API, this is included in the drama detail."""
    detail = await get_drama_detail(book_id)
    if detail:
        return detail.get("list", [])
    return []

async def get_hot_dramas():
    """Fetch hot/popular dramas using the home/tab structure."""
    home_url = f"{BASE_URL}/home"
    lang_params = {"lang": "id"}
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            home_resp = await client.get(home_url, params=lang_params)
            if home_resp.status_code == 200:
                home_data = home_resp.json()
                tabs = home_data.get("list", []) # Root 'list' for tabs
                if tabs:
                    target_tab_id = None
                    # Search for 'Seding Tren' or similar in rankings/tabs
                    for tab in tabs:
                        sub_navs = tab.get("sub_navs", [])
                        for sub in sub_navs:
                            if any(x in sub.get("title", "").lower() for x in ["tren", "hits", "hot", "populer"]):
                                target_tab_id = sub.get("key")
                                break
                        if target_tab_id: break
                    
                    if not target_tab_id:
                        for tab in tabs:
                            if any(x in tab.get("title", "").lower() for x in ["terbaru", "beranda", "home"]):
                                target_tab_id = tab.get("key")
                                break
                    
                    if not target_tab_id: target_tab_id = tabs[0].get("key")
                    
                    tab_url = f"{BASE_URL}/tab/{target_tab_id}"
                    tab_resp = await client.get(tab_url, params=lang_params)
                    if tab_resp.status_code == 200:
                        sections = tab_resp.json()
                        all_items = []
                        if isinstance(sections, list):
                            for sec in sections:
                                items = sec.get("short_plays", [])
                                if items:
                                    for item in items:
                                        item["bookId"] = item.get("id")
                                        item["bookName"] = item.get("short_play_name")
                                        item["cover"] = item.get("cover_url")
                                    all_items.extend(items)
                        return all_items
            return []
        except Exception as e:
            logger.error(f"Error fetching hot dramas: {e}")
            return []

async def get_home_dramas(page=1, size=50):
    return await get_hot_dramas()

async def search_dramas(query: str, page=1, size=15):
    url = f"{BASE_URL}/search"
    params = {
        "lang": "id",
        "q": query,
        "page": page
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                # Search returns a list of results directly
                items = response.json()
                if isinstance(items, list):
                    for item in items:
                        item["bookId"] = item.get("id")
                        item["bookName"] = item.get("short_play_name")
                    return items
            return []
        except Exception as e:
            logger.error(f"Error searching dramas for {query}: {e}")
            return []

async def get_play_url(book_id: str, ep: int):
    """
    Unlock/Get play URL for a specific episode.
    """
    url = f"{BASE_URL}/unlock/{book_id}/{ep}"
    params = {
        "lang": "id",
        "code": AUTH_CODE
    }
    headers = {
        "Referer": "https://idrama.dramabos.my.id/",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                # Data is in 'target_ep_info'
                info = data.get("target_ep_info", {})
                return info
            return None
        except Exception as e:
            logger.error(f"Error unlocking episode {ep} for drama {book_id}: {e}")
            return None
