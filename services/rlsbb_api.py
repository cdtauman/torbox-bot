import aiohttp
from bs4 import BeautifulSoup
import re

async def search(query: str) -> list[dict]:
    """
    מחפש ב-RLSBB ומחזיר רשימת תוצאות שיש להן קישורי Rapidgator/Protected.
    פורמט התוצאה:
    {
        "title": "...",
        "magnet": "...", # we will store the webdl links here as comma-separated or first one
        "size": "N/A",
        "seeders": -1,
        "leechers": -1,
        "source": "RLSBB",
        "is_webdl": True
    }
    """
    url = f"https://rlsbb.to/?s={query}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Posts in RLSBB are typically under <article> since it's a newer WP theme
    posts = soup.find_all("article")
    if not posts:
        # Fallback to div class="post"
        posts = soup.find_all("div", class_="post")

    for post in posts:
        title_tag = post.find("h2") or post.find("h1")
        if not title_tag:
            continue
            
        a_tag = title_tag.find("a")
        if not a_tag:
            continue
            
        title = a_tag.text.strip()

        content = post.find("div", class_="entry-content") or post.find("div", class_="postContent")
        if not content:
            content = post

        links = content.find_all("a", href=True)
        valid_links = []
        for link in links:
            href = link['href']
            text = link.text.strip().lower()
            if "rapidgator.net" in href or ("protected.to" in href and "rapidgator" in text):
                valid_links.append(href)

        if valid_links:
            results.append({
                "title": title,
                "magnet": valid_links[0], # Using the first valid link
                "size": "N/A", 
                "seeders": -1,
                "leechers": -1,
                "source": "RLSBB",
                "is_webdl": True
            })

    return results
