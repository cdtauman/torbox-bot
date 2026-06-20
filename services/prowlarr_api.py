"""
services/prowlarr_api.py — חיפוש דרך Prowlarr.

Prowlarr רץ על השרת כ-indexer manager בלבד. הבוט משתמש בו לחיפוש,
ואת ההורדה בפועל ממשיך לשלוח ל-TorBox.
"""
import logging
import re
from urllib.parse import urljoin

import aiohttp

import config
from services import torbox_api

logger = logging.getLogger(__name__)

_BTIH = re.compile(r"(?i)urn:btih:([a-z0-9]{32,40})")


class ProwlarrError(Exception):
    """שגיאה ידידותית מחיפוש Prowlarr."""
    pass


class MagnetRedirect(Exception):
    """שגיאה המציינת שההורדה הופנתה ל-magnet link."""
    def __init__(self, magnet_url: str):
        self.magnet_url = magnet_url
        super().__init__(magnet_url)


def _headers():
    return {
        "X-Api-Key": config.PROWLARR_API_KEY,
        "Accept": "application/json",
        "User-Agent": "torbox-bot/1.0",
    }


def _require_config():
    if not config.PROWLARR_URL:
        raise ProwlarrError("חסר PROWLARR_URL בקובץ .env")
    if not config.PROWLARR_API_KEY:
        raise ProwlarrError("חסר PROWLARR_API_KEY בקובץ .env")


def _base_url(path: str) -> str:
    return urljoin(config.PROWLARR_URL.rstrip("/") + "/", path.lstrip("/"))


def _extract_hash(release: dict) -> str:
    info_hash = (release.get("infoHash") or release.get("info_hash") or "").lower()
    if info_hash:
        return info_hash

    magnet = release.get("magnetUrl") or release.get("magnet") or ""
    match = _BTIH.search(magnet)
    return match.group(1).lower() if match else ""


def _map_release(release: dict, cached_hashes: dict | None = None) -> dict:
    thash = _extract_hash(release)
    cached = _is_cached(cached_hashes, thash) if thash else False

    return {
        "title": release.get("title") or release.get("sortTitle") or "ללא שם",
        "size": release.get("size") or 0,
        "seeders": release.get("seeders") or 0,
        "leechers": release.get("leechers") or 0,
        "hash": thash,
        "magnet": release.get("magnetUrl") or "",
        "download_url": release.get("downloadUrl") or "",
        "torrent_url": release.get("downloadUrl") or "",
        "published": release.get("publishDate") or "",
        "tracker": release.get("indexer") or "",
        "indexer": release.get("indexer") or "",
        "guid": release.get("guid") or "",
        "indexer_id": release.get("indexerId"),
        "cached": cached,
        "source": "prowlarr",
    }


def _is_torrent_release(release: dict) -> bool:
    protocol = release.get("protocol")
    if protocol is None:
        return True

    value = str(protocol).lower()
    # Prowlarr usually serializes this as "torrent"; some clients expose the
    # Servarr enum number where Torrent is 2.
    return value in ("torrent", "2")


def _is_cached(cache_data, thash: str) -> bool:
    if not cache_data or not thash:
        return False

    value = cache_data.get(thash) or cache_data.get(thash.upper())
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return bool(value.get("cached") or value.get("is_cached") or value.get("hash"))
    return bool(value)


async def _check_cached(releases: list[dict]) -> dict:
    hashes = sorted({_extract_hash(r) for r in releases if _extract_hash(r)})
    if not hashes:
        return {}

    try:
        return await torbox_api.check_cached(hashes)
    except Exception as exc:
        logger.warning("[PROWLARR] cache check failed: %s: %s", type(exc).__name__, exc)
        return {}


async def search(query: str) -> list[dict]:
    """מחזיר תוצאות גולמיות במבנה ש-parser.normalize יודע לנרמל."""
    _require_config()
    timeout = aiohttp.ClientTimeout(total=config.PROWLARR_TIMEOUT)
    params = {
        "query": query,
        "type": "search",
        "limit": str(config.PROWLARR_LIMIT),
    }

    async with aiohttp.ClientSession(timeout=timeout) as session:
        url = _base_url("/api/v1/search")
        logger.info("[PROWLARR] search query=%r", query)
        async with session.get(url, headers=_headers(), params=params) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                detail = (await resp.text())[:300]
                raise ProwlarrError(f"Prowlarr החזיר תשובה לא תקינה: {detail or resp.status}")

            if resp.status != 200:
                detail = _error_detail(data) or f"HTTP {resp.status}"
                raise ProwlarrError(f"שגיאה בחיפוש מול Prowlarr: {detail}")

    if not isinstance(data, list):
        raise ProwlarrError("Prowlarr החזיר מבנה תשובה לא צפוי")

    torrent_releases = [r for r in data if _is_torrent_release(r)]
    cached_hashes = await _check_cached(torrent_releases)
    results = [_map_release(r, cached_hashes) for r in torrent_releases]
    results.sort(key=lambda r: r.get("seeders") or 0, reverse=True)
    logger.info("[PROWLARR] query=%r results=%s", query, len(results))
    return results[:config.SEARCH_LIMIT]


async def fetch_torrent(download_url: str) -> tuple[str, bytes]:
    """מוריד קובץ torrent דרך proxy של Prowlarr כדי לשלוח אותו ל-TorBox."""
    _require_config()
    if not download_url:
        raise ProwlarrError("לתוצאה אין קישור torrent להורדה")

    # If the download URL itself is already a magnet link, raise immediately
    if download_url.lower().startswith("magnet:"):
        raise MagnetRedirect(download_url)

    timeout = aiohttp.ClientTimeout(total=config.PROWLARR_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(_absolute_url(download_url), headers=_headers(), allow_redirects=True) as resp:
                final_url = str(resp.url)
                if final_url.startswith("magnet:"):
                    raise MagnetRedirect(final_url)

                data = await resp.read()
                if resp.status != 200:
                    detail = data.decode("utf-8", errors="replace")[:300]
                    raise ProwlarrError(f"לא הצלחתי להוריד torrent מ-Prowlarr: {detail or resp.status}")

                filename = _filename_from_headers(resp.headers) or "prowlarr-result.torrent"
                return filename, data
        except MagnetRedirect:
            raise
        except Exception as e:
            err_msg = str(e)
            match = re.search(r'(magnet:\?xt=urn:btih:[^\s\'"\>]+)', err_msg, re.IGNORECASE)
            if match:
                raise MagnetRedirect(match.group(1))
            raise ProwlarrError(f"לא הצלחתי להוריד torrent מ-Prowlarr: {e}")


def _absolute_url(url: str) -> str:
    if url.startswith(("http://", "https://")):
        url = url.replace("127.0.0.1:9696", "prowlarr:9696").replace("localhost:9696", "prowlarr:9696")
        return url
    return _base_url(url)


def _filename_from_headers(headers) -> str:
    disposition = headers.get("Content-Disposition", "")
    match = re.search(r'filename="?([^";]+)"?', disposition)
    if match:
        filename = match.group(1).strip()
        return filename if filename.lower().endswith(".torrent") else f"{filename}.torrent"
    return ""


def _error_detail(data) -> str:
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error") or data.get("detail") or "")
    if isinstance(data, list) and data:
        return str(data[0])
    return ""
