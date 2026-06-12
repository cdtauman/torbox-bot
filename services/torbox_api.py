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


# ───────────────────────── חיפוש (Stremio Addon + TorrentsCSV) ─────────────────────────
import logging
import re
logger = logging.getLogger(__name__)

def _parse_torrentio(streams):
    """מנרמל תוצאות מ-Torrentio למבנה שהבוט מצפה לו"""
    results = []
    for s in streams:
        if "infoHash" not in s:
            continue
        title = s.get("title", "")
        name = title.split("\n")[0] if title else s.get("name", "Unknown")
        
        size_bytes = 0
        seeders = 0
        
        match_seed = re.search(r'👤\s*(\d+)', title)
        if match_seed: 
            seeders = int(match_seed.group(1))
            
        match_size = re.search(r'💾\s*([\d\.]+)\s*(GB|MB|KB)', title)
        if match_size:
            val = float(match_size.group(1))
            unit = match_size.group(2)
            if unit == "GB": size_bytes = int(val * 1024**3)
            elif unit == "MB": size_bytes = int(val * 1024**2)
            elif unit == "KB": size_bytes = int(val * 1024)
            
        results.append({
            "info_hash": s.get("infoHash"),
            "name": name,
            "size": size_bytes,
            "seeders": seeders,
            "leechers": 0
        })
    return results

async def search(query: str, check_cache: bool = True):
    """
    חיפוש משולב:
    מנסה תחילה להשתמש ב-Torrentio (כמו ב-Stremio) דרך Cinemeta.
    אם אין תוצאות או אם אין עונה/פרק בסדרה, נופל ל-TorrentsCSV.
    """
    results = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    # זיהוי עונה ופרק
    match = re.search(r'(?i)s(\d{1,2})\s*e(\d{1,2})', query)
    async with aiohttp.ClientSession() as session:
        if match:
            # --- חיפוש סדרה ב-Torrentio ---
            season = int(match.group(1))
            episode = int(match.group(2))
            clean_query = re.sub(r'(?i)s\d{1,2}\s*e\d{1,2}', '', query).strip()
            
            c_url = f"https://v3-cinemeta.strem.io/catalog/series/top/search={clean_query}.json"
            try:
                async with session.get(c_url, headers=headers) as resp:
                    if resp.status == 200:
                        c_data = await resp.json(content_type=None)
                        metas = c_data.get("metas", [])
                        if metas:
                            imdb_id = metas[0].get("imdb_id")
                            if imdb_id:
                                t_url = f"https://torrentio.strem.fun/stream/series/{imdb_id}:{season}:{episode}.json"
                                async with session.get(t_url, headers=headers) as t_resp:
                                    if t_resp.status == 200:
                                        t_data = await t_resp.json(content_type=None)
                                        streams = t_data.get("streams", [])
                                        if streams:
                                            results = _parse_torrentio(streams)
                                    else:
                                        logger.error(f"Torrentio returned {t_resp.status}: {await t_resp.text()}")
            except Exception as e:
                logger.error(f"Torrentio series search failed: {e}")
        else:
            # --- חיפוש סרט ב-Torrentio ---
            c_url = f"https://v3-cinemeta.strem.io/catalog/movie/top/search={query}.json"
            try:
                async with session.get(c_url, headers=headers) as resp:
                    if resp.status == 200:
                        c_data = await resp.json(content_type=None)
                        metas = c_data.get("metas", [])
                        if metas:
                            imdb_id = metas[0].get("imdb_id")
                            if imdb_id:
                                t_url = f"https://torrentio.strem.fun/stream/movie/{imdb_id}.json"
                                async with session.get(t_url, headers=headers) as t_resp:
                                    if t_resp.status == 200:
                                        t_data = await t_resp.json(content_type=None)
                                        streams = t_data.get("streams", [])
                                        if streams:
                                            results = _parse_torrentio(streams)
                                    else:
                                        logger.error(f"Torrentio returned {t_resp.status}: {await t_resp.text()}")
            except Exception as e:
                logger.error(f"Torrentio movie search failed: {e}")

        # --- Fallback: Torrents-CSV ---
        if not results:
            url = "https://torrents-csv.com/service/search"
            params = {"q": query, "size": 50}
            try:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        csv_results = data.get("torrents", [])
                        if isinstance(csv_results, list):
                            for r in csv_results:
                                if "infohash" in r and "info_hash" not in r:
                                    r["info_hash"] = r["infohash"]
                                if "size_bytes" in r and "size" not in r:
                                    r["size"] = r["size_bytes"]
                            results = csv_results
            except Exception as e:
                logger.error(f"TorrentsCSV search failed: {e}")

    if not results:
        return []

    # הגבלת כמות תוצאות
    results = results[:60]
    
    # בדיקת קאש ב-TorBox
    if check_cache and results:
        hashes = [r.get("info_hash") for r in results if r.get("info_hash")]
        if hashes:
            try:
                cached_data = await check_cached(hashes)
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
                pass  # מתעלם משגיאות קאש
                
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
