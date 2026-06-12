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


# ───────────────────────── חיפוש (Jackett — מקומי, ללא חסימות) ────────────────────�async def _jackett_fetch(session, params: dict) -> list:
    """פונקציית עזר: שולח בקשה לJackett ומחזיר רשימת Results."""
    url = f"{JACKETT_URL}/api/v2.0/indexers/all/results"
    full_params = {"apikey": JACKETT_KEY, **params}
    try:
        logger.debug(f"[JACKETT] GET params={params}")
        async with session.get(url, params=full_params, timeout=aiohttp.ClientTimeout(total=25)) as resp:
            logger.debug(f"[JACKETT] Response status={resp.status}")
            if resp.status != 200:
                body = await resp.text()
                logger.error(f"[JACKETT] HTTP {resp.status}: {body[:300]}")
                return []
            data = await resp.json(content_type=None)
            results = data.get("Results", [])
            logger.info(f"[JACKETT] Got {len(results)} raw results for params={params}")
            return results
    except Exception as e:
        logger.error(f"[JACKETT] Request failed: {type(e).__name__}: {e}")
        return []


def _parse_raw(raw_list: list) -> list:
    """ממיר תוצאות גולמיות מJackett למבנה אחיד."""
    results = []
    for r in raw_list:
        info_hash = r.get("InfoHash") or ""
        magnet = r.get("MagnetUri") or ""
        if not info_hash and "urn:btih:" in magnet:
            m = re.search(r"urn:btih:([a-fA-F0-9]{40})", magnet)
            info_hash = m.group(1) if m else ""
        results.append({
            "info_hash": info_hash.lower(),
            "name": r.get("Title", "Unknown"),
            "size": r.get("Size", 0),
            "seeders": r.get("Seeders", 0),
            "leechers": r.get("Peers", 0),
            "magnet": magnet,
        })
    return results


async def search(query: str, check_cache: bool = True):
    """
    חיפוש דרך Jackett עם זיהוי חכם של סדרות/סרטים.

    לסדרות (SxxExx): משתמש ב-t=tvsearch עם season/ep נפרדים —
    זה האופן הנכון ב-Torznab שמניב הרבה יותר תוצאות.
    לסרטים/חיפוש כללי: t=search רגיל.
    """
    if not JACKETT_KEY:
        logger.error("JACKETT_API_KEY not set in .env")
        return []

    # זיהוי SxxExx (למשל S05E06 או s5e6)
    tv_match = re.search(r'(?i)\bS(\d{1,2})[\s._-]?E(\d{1,2})\b', query)

    raw = []
    async with aiohttp.ClientSession() as session:
        if tv_match:
            season = int(tv_match.group(1))
            episode = int(tv_match.group(2))
            # שם הסדרה בלבד (בלי SxxExx)
            show_name = re.sub(r'(?i)\bS\d{1,2}[\s._-]?E\d{1,2}\b', '', query).strip()
            logger.info(f"[JACKETT] TV search | show={show_name!r} S{season:02d}E{episode:02d}")

            # חיפוש tvsearch עם עונה+פרק — הדרך הנכונה
            tv_raw = await _jackett_fetch(session, {
                "t": "tvsearch",
                "q": show_name,
                "season": season,
                "ep": episode,
            })
            raw.extend(tv_raw)

            # fallback: חיפוש כללי עם השאילתה המלאה (SxxExx כמחרוזת)
            if len(raw) < 5:
                logger.info("[JACKETT] tvsearch gave few results, trying general search fallback")
                gen_raw = await _jackett_fetch(session, {
                    "t": "search",
                    "Query": f"{show_name} S{season:02d}E{episode:02d}",
                })
                # מיזוג ללא כפילויות
                existing_hashes = {r.get("InfoHash", "").lower() for r in raw}
                for r in gen_raw:
                    if r.get("InfoHash", "").lower() not in existing_hashes:
                        raw.append(r)
        else:
            # חיפוש כללי (סרט / משחק / תוכנה / שם בלבד)
            logger.info(f"[JACKETT] General search | query={query!r}")
            raw = await _jackett_fetch(session, {
                "t": "search",
                "Query": query,
            })

    logger.info(f"[JACKETT] Total raw after all searches: {len(raw)}")
    if not raw:
        logger.warning(f"[JACKETT] No results at all for query={query!r}")
        return []

    results = _parse_raw(raw)

    # מיון לפי seeders, הגבלה ל-60
    results.sort(key=lambda x: x.get("seeders", 0), reverse=True)
    results = results[:60]
    logger.info(f"[JACKETT] After processing: {len(results)} results (top 60 by seeders)")

    # בדיקת קאש ב-TorBox
    if check_cache and results:
        hashes = [r["info_hash"] for r in results if r.get("info_hash")]
        if hashes:
            try:
                cached_data = await check_cached(hashes)
                if isinstance(cached_data, dict):
                    for r in results:
                        if any(k.lower() == r["info_hash"] for k in cached_data.keys()):
                            r["cached"] = True
                elif isinstance(cached_data, list):
                    cached_hashes = {item.get("hash", "").lower() for item in cached_data}
                    for r in results:
                        if r["info_hash"] in cached_hashes:
                            r["cached"] = True
            except Exception:
                pass

    return results

= {item.get("hash", "").lower() for item in cached_data}
                    for r in results:
                        if r["info_hash"] in cached_hashes:
                            r["cached"] = True
            except Exception:
                pass

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
