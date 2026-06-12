"""
services/torbox_api.py — עטיפה אסינכרונית ל-TorBox API
Endpoints רשמיים: https://api-docs.torbox.app
"""
import aiohttp

import config

BASE = f"{config.TORBOX_BASE_URL}/{config.TORBOX_API_VERSION}/api"


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


# ───────────────────────── חיפוש (חלופה ציבורית) ─────────────────────────
async def search(query: str, check_cache: bool = True):
    """
    חיפוש טורנטים דרך apibay (The Pirate Bay) כתחליף למנוע החיפוש החסום של TorBox.
    עדיין מבצע בדיקת קאש מול שרתי TorBox לזיהוי הורדה מיידית.
    """
    url = "https://apibay.org/q.php"
    params = {"q": query}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params) as resp:
                results = await resp.json(content_type=None)
        except Exception:
            raise TorBoxError("לא הצלחתי להתחבר למנוע החיפוש החלופי.")
            
        if not isinstance(results, list):
            return []
            
        # apibay returns {"id":"0","name":"No results returned"...} if empty
        if len(results) == 1 and results[0].get("id") == "0":
            return []
            
        # הגבלת כמות תוצאות למניעת עומס
        results = results[:60]
        
        # בדיקת קאש ב-TorBox
        if check_cache and results:
            hashes = [r.get("info_hash") for r in results if r.get("info_hash")]
            if hashes:
                try:
                    cached_data = await check_cached(hashes)
                    # format=object returns a list or dict depending on TorBox API version
                    if isinstance(cached_data, dict):
                        for r in results:
                            thash = r.get("info_hash", "").lower()
                            if any(k.lower() == thash for k in cached_data.keys()):
                                r["cached"] = True
                    elif isinstance(cached_data, list):
                        cached_hashes = [item.get("hash", "").lower() for item in cached_data]
                        for r in results:
                            if r.get("info_hash", "").lower() in cached_hashes:
                                r["cached"] = True
                except Exception:
                    pass  # מתעלם משגיאות קאש ומחזיר תוצאות בכל מקרה
                    
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
