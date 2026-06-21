"""
services/rlsbb_api.py — גרידת RLSBB לקישורי Debrid (הורדות ישירות).
מחפש באתר RLSBB ומחזיר קישורים ישירים (Rapidgator, Nitroflare וכו').
לפני הצגת התוצאות, בודק מול TorBox API אילו hosters פעילים כרגע
ומסנן קישורים מ-hosters כבויים.
"""
import aiohttp
from bs4 import BeautifulSoup
import re
import urllib.parse
import logging

logger = logging.getLogger(__name__)

# רשימת hosters שאנחנו מחפשים ב-RLSBB
ALL_HOSTERS = [
    "rapidgator.net", "rg.to",
    "nitroflare.com", "nitro.download",
    "1fichier.com",
    "turbobit.net",
    "filefactory.com",
    "clicknupload.click", "clicknupload.com", "clicknupload.to",
    "hitfile.net",
    "mediafire.com",
    "mega.nz", "mega.io",
    "katfile.com",
    "mexashare.com",
    "uploadgig.com",
]


async def get_online_hosters() -> set[str]:
    """
    שואל את TorBox API אילו hosters פעילים כרגע.
    מחזיר set של דומיינים פעילים.
    """
    import config
    url = f"{config.TORBOX_BASE_URL}/{config.TORBOX_API_VERSION}/api/webdl/hosters"
    headers = {
        "Authorization": f"Bearer {config.TORBOX_API_KEY}",
        "Accept": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"[HOSTERS] Failed to fetch hosters: HTTP {resp.status}")
                    return set()  # אם לא הצלחנו לשלוף, נחזיר set ריק (לא נסנן)
                data = await resp.json(content_type=None)
                if not data.get("success"):
                    return set()
                online_domains = set()
                for h in data.get("data", []):
                    if h.get("status") == True:
                        for domain in h.get("domains", []):
                            online_domains.add(domain.lower())
                logger.info(f"[HOSTERS] {len(online_domains)} online domains fetched from TorBox")
                return online_domains
    except Exception as e:
        logger.warning(f"[HOSTERS] Error fetching hosters: {e}")
        return set()


def _extract_hoster_name(url: str) -> str:
    """מחלץ את שם ה-hoster מתוך URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        # הסר www.
        if host.startswith("www."):
            host = host[4:]
        return host.lower()
    except Exception:
        return ""


async def search(query: str) -> list[dict]:
    """
    מחפש ב-RLSBB ומחזיר רשימת תוצאות שיש להן קישורי Debrid.
    מסנן אוטומטית קישורים מ-hosters שכרגע כבויים ב-TorBox.
    מחזיר כל קישור כתוצאה נפרדת עם שם הקובץ.
    """
    query_encoded = urllib.parse.quote_plus(query)
    url = f"https://search.rlsbb.to/?s={query_encoded}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    # שלב 1: שלוף את ה-hosters הפעילים מ-TorBox
    online_domains = await get_online_hosters()
    if online_domains:
        logger.info(f"[RLSBB] Filtering by {len(online_domains)} online TorBox domains")
    else:
        logger.warning("[RLSBB] Could not fetch online hosters, showing all results (unfiltered)")

    # שלב 2: גרד את RLSBB
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
    except Exception as e:
        logger.error(f"[RLSBB] Failed to fetch search page: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    posts = soup.find_all("article")
    if not posts:
        posts = soup.find_all("div", class_="post")

    for post in posts:
        title_tag = post.find("h2") or post.find("h1")
        if not title_tag:
            continue

        a_tag = title_tag.find("a")
        if not a_tag:
            continue

        post_title = a_tag.text.strip()

        content = post.find("div", class_="entry-content") or post.find("div", class_="postContent")
        if not content:
            content = post

        html_content = str(content)

        # שלוף את כל הקישורים באמצעות regex
        raw_urls = set(re.findall(r'https?://[^\'"\s<>]+', html_content))

        valid_links = []
        for link in raw_urls:
            link_lower = link.lower()
            # דלג על protected.to
            if "protected.to" in link_lower:
                continue

            # בדוק אם זה hoster מוכר
            hoster_domain = _extract_hoster_name(link)
            if not hoster_domain:
                continue

            is_known_hoster = any(h in hoster_domain for h in ALL_HOSTERS) or any(hoster_domain in h for h in ALL_HOSTERS)
            if not is_known_hoster:
                continue

            # אם יש לנו רשימת hosters פעילים — סנן
            if online_domains:
                is_online = any(d in hoster_domain or hoster_domain in d for d in online_domains)
                if not is_online:
                    continue

            valid_links.append(link)

        for link in valid_links:
            # חלץ את שם הקובץ מהקישור
            filename = link.split("/")[-1]
            if filename.endswith(".html"):
                filename = filename[:-5]
            # נקה URL encoding
            filename = urllib.parse.unquote(filename)

            hoster = _extract_hoster_name(link)
            clean_title = f"{post_title} [{filename}]" if filename else post_title

            results.append({
                "title": clean_title,
                "magnet": link,
                "size": "N/A",
                "seeders": -1,
                "leechers": -1,
                "source": f"RLSBB ({hoster})",
                "is_webdl": True,
            })

    logger.info(f"[RLSBB] query={query!r} | posts={len(posts)} | results={len(results)}")
    return results
