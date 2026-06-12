"""
services/torbox_api.py — עטיפה אסינכרונית ל-TorBox API.

חיפוש: מנוע החיפוש הרשמי של TorBox — search-api.torbox.app (Orion).
        אמין, מתארח אצל TorBox (אין חסימות Cloudflare/IP כמו ב-Jackett מקומי),
        תוצאות cached, ומחזיר את השדות ש-services/parser.py כבר יודע לנרמל.
הורדה/רשימה/שליטה: ה-API הראשי — api.torbox.app/v1/api.

Docs: https://api-docs.torbox.app , https://search-api.torbox.app
"""
import re
import logging

import aiohttp

import config

logger = logging.getLogger(__name__)

BASE = f"{config.TORBOX_BASE_URL}/{config.TORBOX_API_VERSION}/api"
SEARCH_BASE = config.TORBOX_SEARCH_URL.rstrip("/")

# זמן המתנה לבקשת חיפוש בודדת
_SEARCH_TIMEOUT = aiohttp.ClientTimeout(total=25)


class TorBoxError(Exception):
    """שגיאה שהוחזרה מ-TorBox עם הודעה ידידותית."""
    pass


def _headers():
    return {"Authorization": f"Bearer {config.TORBOX_API_KEY}"}


async def _get(session, path, params=None):
    url = f"{BASE}{path}"
    async with session.get(url, headers=_headers(), params=params) as resp:
        data = await resp.json(content_type=None)
        if not data.get("success", False):
            raise TorBoxError(data.get("detail") or data.get("error") or "שגיאה לא ידועה מ-TorBox")
        return data.get("data")


async def _post(session, path, json_body=None, data_body=None):
    url = f"{BASE}{path}"
    async with session.post(url, headers=_headers(), json=json_body, data=data_body) as resp:
        data = await resp.json(content_type=None)
        if not data.get("success", False):
            raise TorBoxError(data.get("detail") or data.get("error") or "שגיאה לא ידועה מ-TorBox")
        return data.get("data")


# ───────────────────────── חיפוש (TorBox Search API) ─────────────────────────
_SXXEXX = re.compile(r'(?i)\bS(\d{1,2})[\s._-]?E(\d{1,3})\b')
_SXX = re.compile(r'(?i)\bS(\d{1,2})\b')


def _query_variants(query: str) -> list:
    """
    בונה רשימת ניסוחים מהמדויק לרחב — כדי "להבין כוונה" ולא להיתקע על טקסט מדויק.
    דוגמה: 'Welcome to Wrexham S05E06' →
        ['Welcome to Wrexham S05E06', 'Welcome to Wrexham S05', 'Welcome to Wrexham']
    התוצאות ממוזגות, כך שגם פרק בודד וגם חבילת-עונה יופיעו.
    """
    q = query.strip()
    variants = [q]

    m = _SXXEXX.search(q)
    if m:
        season = int(m.group(1))
        title = _SXXEXX.sub("", q).strip(" .-_")
        # חבילת עונה (S05) ושם נקי — מה שמצאת שמחזיר תוצאות גם כשהפרק לא
        variants.append(f"{title} S{season:02d}")
        variants.append(title)
    else:
        m2 = _SXX.search(q)
        if m2:
            title = _SXX.sub("", q).strip(" .-_")
            if title:
                variants.append(title)

    # הסרת כפילויות תוך שמירת סדר
    seen, out = set(), []
    for v in variants:
        key = v.lower()
        if v and key not in seen:
            seen.add(key)
            out.append(v)
    return out


def _torrent_key(t: dict) -> str:
    """מפתח ייחודי לטורנט לצורך מיזוג בלי כפילויות."""
    h = (t.get("hash") or t.get("info_hash") or "").lower()
    if h:
        return h
    mag = t.get("magnet") or ""
    mm = re.search(r"(?i)urn:btih:([a-z0-9]{32,40})", mag)
    if mm:
        return mm.group(1).lower()
    return (t.get("raw_title") or t.get("title") or "").lower()


async def _search_once(session, query: str, check_cache: bool) -> list:
    """בקשת חיפוש בודדת ל-search-api. מחזיר רשימת torrents גולמית (או [])."""
    from urllib.parse import quote
    url = f"{SEARCH_BASE}/torrents/search/{quote(query)}"
    params = {"metadata": "false"}
    if check_cache:
        params["check_cache"] = "true"
    try:
        logger.debug(f"[TBSEARCH] GET {url} | params={params}")
        async with session.get(url, params=params, headers=_headers(),
                               timeout=_SEARCH_TIMEOUT) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200 or not body.get("success", False):
                detail = body.get("error") or body.get("detail") or f"HTTP {resp.status}"
                logger.warning(f"[TBSEARCH] query={query!r} failed: {detail}")
                return []
            torrents = (body.get("data") or {}).get("torrents", []) or []
            logger.info(f"[TBSEARCH] query={query!r} → {len(torrents)} torrents")
            return torrents
    except Exception as e:
        logger.error(f"[TBSEARCH] query={query!r} error: {type(e).__name__}: {e}")
        return []


async def search(query: str, check_cache: bool = True):
    """
    חיפוש דרך מנוע החיפוש הרשמי של TorBox.
    מנסה כמה ניסוחים (מהמדויק לרחב) וממזג — כדי שתמיד יחזרו תוצאות רלוונטיות.
    מחזיר רשימת torrents גולמיים; services/parser.normalize ממיר למבנה האחיד.
    """
    if not config.TORBOX_API_KEY:
        logger.error("TORBOX_API_KEY not set in .env")
        return []

    variants = _query_variants(query)
    merged: dict = {}

    async with aiohttp.ClientSession() as session:
        for v in variants:
            torrents = await _search_once(session, v, check_cache)
            for t in torrents:
                merged.setdefault(_torrent_key(t), t)
            # מספיק תוצאות — אין צורך להרחיב עוד
            if len(merged) >= config.SEARCH_ENOUGH:
                break

    results = list(merged.values())
    # מיון לפי seeders והגבלה
    results.sort(key=lambda t: t.get("last_known_seeders") or t.get("seeders") or 0, reverse=True)
    results = results[:config.SEARCH_LIMIT]
    cached_n = sum(1 for t in results if t.get("cached"))
    logger.info(f"[TBSEARCH] query={query!r} | variants={len(variants)} | "
                f"merged={len(results)} | cached={cached_n}")
    return results


# ───────────────────────── הורדה ─────────────────────────
async def add_magnet(magnet: str):
    """מוסיף magnet ל-TorBox. מחזיר נתוני הטורנט שנוצר."""
    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field("magnet", magnet)
        return await _post(session, "/torrents/createtorrent", data_body=form)


async def add_hash(thash: str):
    """מוסיף טורנט לפי hash (בונה magnet בסיסי)."""
    magnet = f"magnet:?xt=urn:btih:{thash}"
    return await add_magnet(magnet)


# ───────────────────────── רשימה / סטטוס ─────────────────────────
async def my_list(torrent_id=None):
    """רשימת ההורדות של המשתמש. אם נתון id — מחזיר אחד בלבד."""
    params = {"bypass_cache": "true"}
    if torrent_id is not None:
        params["id"] = str(torrent_id)
    async with aiohttp.ClientSession() as session:
        return await _get(session, "/torrents/mylist", params=params)


async def check_cached(hashes):
    """בדיקה אילו hashes כבר בקאש. מקבל רשימה, מחזיר dict."""
    if isinstance(hashes, str):
        hashes = [hashes]
    params = [("hash", h) for h in hashes]
    params.append(("format", "object"))
    params.append(("list_files", "false"))
    async with aiohttp.ClientSession() as session:
        try:
            return await _get(session, "/torrents/checkcached", params=params)
        except TorBoxError:
            return {}


# ───────────────────────── קישור הורדה ─────────────────────────
async def request_download_link(torrent_id, file_id=None):
    """מבקש קישור הורדה ישיר (זמני) לטורנט שהושלם."""
    params = {"token": config.TORBOX_API_KEY, "torrent_id": str(torrent_id)}
    if file_id is not None:
        params["file_id"] = str(file_id)
    async with aiohttp.ClientSession() as session:
        return await _get(session, "/torrents/requestdl", params=params)


# ───────────────────────── שליטה ─────────────────────────
async def control(torrent_id, operation: str):
    """
    פעולות שליטה: 'delete', 'pause', 'resume', 'reannounce'.
    """
    async with aiohttp.ClientSession() as session:
        return await _post(session, "/torrents/controltorrent",
                           json_body={"torrent_id": torrent_id, "operation": operation})


async def delete_torrent(torrent_id):
    return await control(torrent_id, "delete")
