"""
services/prowlarr_api.py — חיפוש דרך Prowlarr.

Prowlarr רץ על השרת כ-indexer manager בלבד. הבוט משתמש בו לחיפוש,
ואת ההורדה בפועל ממשיך לשלוח ל-TorBox.
"""
import logging
import re
from urllib.parse import urljoin, urlparse, urlunparse

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


def _protocol(release: dict) -> str:
    value = str(release.get("protocol") or "torrent").lower()
    if value in ("usenet", "1"):
        return "usenet"
    return "torrent"


def _map_release(release: dict, cached_hashes: dict | None = None) -> dict:
    protocol = _protocol(release)
    thash = _extract_hash(release) if protocol == "torrent" else ""
    cached = _is_cached(cached_hashes, thash) if thash else False
    download_url = release.get("downloadUrl") or ""

    return {
        "title": release.get("title") or release.get("sortTitle") or "ללא שם",
        "size": release.get("size") or 0,
        "seeders": release.get("seeders") or 0,
        "leechers": release.get("leechers") or 0,
        "hash": thash,
        "magnet": release.get("magnetUrl") or "",
        "download_url": download_url,
        "torrent_url": download_url if protocol == "torrent" else "",
        "nzb_url": download_url if protocol == "usenet" else "",
        "published": release.get("publishDate") or "",
        "tracker": release.get("indexer") or "",
        "indexer": release.get("indexer") or "",
        "guid": release.get("guid") or "",
        "indexer_id": release.get("indexerId"),
        "cached": cached,
        "source": "prowlarr",
        "result_type": protocol,
        "protocol": protocol,
    }


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
    """מחזיר תוצאות Torrent ו-Usenet מ-Prowlarr במבנה אחיד."""
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

    allowed = set()
    if config.SEARCH_INCLUDE_TORRENTS:
        allowed.add("torrent")
    if config.SEARCH_INCLUDE_USENET:
        allowed.add("usenet")

    releases = [r for r in data if _protocol(r) in allowed]
    torrent_releases = [r for r in releases if _protocol(r) == "torrent"]
    cached_hashes = await _check_cached(torrent_releases)

    results = [_map_release(r, cached_hashes) for r in releases]
    logger.info(
        "[PROWLARR] query=%r results=%s torrents=%s usenet=%s",
        query,
        len(results),
        sum(1 for r in results if r["result_type"] == "torrent"),
        sum(1 for r in results if r["result_type"] == "usenet"),
    )
    return results[:config.SEARCH_LIMIT]


def _download_headers(url: str) -> dict:
    """Headers להורדה; מפתח Prowlarr נשלח רק ל-origin המוגדר."""
    headers = {
        "Accept": "*/*",
        "User-Agent": "torbox-bot/1.0",
    }
    parsed = urlparse(url)
    base = urlparse(config.PROWLARR_URL)
    if (
        parsed.scheme.lower() == base.scheme.lower()
        and parsed.netloc.lower() == base.netloc.lower()
    ):
        headers["X-Api-Key"] = config.PROWLARR_API_KEY
    return headers


def _redirect_url(current_url: str, location: str) -> str:
    """מנרמל redirect; aliases מקומיים חוזרים ל-origin המוגדר."""
    if not location:
        raise ProwlarrError("Prowlarr החזיר redirect ללא Location")
    if location.lower().startswith("magnet:"):
        return location

    candidate = urljoin(current_url, location)
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ProwlarrError("Prowlarr החזיר redirect לא תקין")

    base = urlparse(config.PROWLARR_URL)
    local_aliases = {"127.0.0.1", "localhost", "prowlarr"}
    if (parsed.hostname or "").lower() in ({(base.hostname or "").lower()} | local_aliases):
        return _absolute_url(candidate)

    # Redirect חיצוני יכול להיות יעד ההורדה של ה-indexer,
    # אך לעולם לא יקבל את X-Api-Key של Prowlarr.
    return candidate


async def _fetch_download_bytes(session, download_url: str):
    """מוריד קובץ עם redirects ידניים כדי לא לדלוף API key."""
    current_url = _absolute_url(download_url)
    for _ in range(5):
        async with session.get(
            current_url,
            headers=_download_headers(current_url),
            allow_redirects=False,
        ) as resp:
            if resp.status in (301, 302, 303, 307, 308):
                current_url = _redirect_url(current_url, resp.headers.get("Location", ""))
                if current_url.lower().startswith("magnet:"):
                    raise MagnetRedirect(current_url)
                continue
            return resp.status, resp.headers, str(resp.url), await resp.read()

    raise ProwlarrError("יותר מדי redirects בזמן הורדה דרך Prowlarr")


async def fetch_nzb(download_url: str) -> tuple[str, bytes]:
    """מוריד NZB דרך Prowlarr כדי להעביר אותו ל-TorBox."""
    _require_config()
    if not download_url:
        raise ProwlarrError("לתוצאת Usenet אין קישור NZB להורדה")

    timeout = aiohttp.ClientTimeout(total=config.PROWLARR_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        status, headers, _, data = await _fetch_download_bytes(session, download_url)
        if status != 200:
            detail = data.decode("utf-8", errors="replace")[:300]
            raise ProwlarrError(f"לא הצלחתי להוריד NZB מ-Prowlarr: {detail or status}")
        preview = data[:4096].lower()
        if b"<nzb" not in preview and b"<?xml" not in preview:
            raise ProwlarrError("Prowlarr לא החזיר קובץ NZB תקין")
        filename = _filename_from_headers(
            headers,
            default="prowlarr-result.nzb",
            suffix=".nzb",
        )
        return filename, data


async def fetch_torrent(download_url: str) -> tuple[str, bytes]:
    """מוריד קובץ torrent דרך proxy של Prowlarr כדי לשלוח אותו ל-TorBox."""
    _require_config()
    if not download_url:
        raise ProwlarrError("לתוצאה אין קישור torrent להורדה")

    if download_url.lower().startswith("magnet:"):
        raise MagnetRedirect(download_url)

    timeout = aiohttp.ClientTimeout(total=config.PROWLARR_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            status, headers, _, data = await _fetch_download_bytes(session, download_url)
            if status != 200:
                detail = data.decode("utf-8", errors="replace")[:300]
                raise ProwlarrError(
                    f"לא הצלחתי להוריד torrent מ-Prowlarr: {detail or status}"
                )
            filename = _filename_from_headers(headers) or "prowlarr-result.torrent"
            return filename, data
        except MagnetRedirect:
            raise
        except ProwlarrError:
            raise
        except Exception as e:
            err_msg = str(e)
            match = re.search(
                r'(magnet:\\?xt=urn:btih:[^\\s\\\'\"\\>]+)',
                err_msg,
                re.IGNORECASE,
            )
            if match:
                raise MagnetRedirect(match.group(1))
            raise ProwlarrError(f"לא הצלחתי להוריד torrent מ-Prowlarr: {e}")

def _absolute_url(url: str) -> str:
    """
    מחזיר URL שעובר תמיד דרך מופע Prowlarr שהוגדר.
    כך לא מדליפים X-Api-Key ל-host חיצוני אם indexer מחזיר URL לא צפוי.
    """
    if not url.startswith(("http://", "https://")):
        return _base_url(url)

    target = urlparse(url)
    base = urlparse(config.PROWLARR_URL)
    target_host = (target.hostname or "").lower()
    base_host = (base.hostname or "").lower()

    local_aliases = {"127.0.0.1", "localhost", "prowlarr"}
    allowed_hosts = {base_host} | local_aliases
    if target_host not in allowed_hosts:
        raise ProwlarrError("Prowlarr החזיר כתובת הורדה חיצונית לא צפויה")

    # Prowlarr עשוי להחזיר localhost גם כשהבוט רץ ב-Docker ולהפך.
    # משמרים path/query אבל תמיד משתמשים ב-origin שהוגדר ב-PROWLARR_URL.
    return urlunparse((
        base.scheme or target.scheme,
        base.netloc or target.netloc,
        target.path,
        target.params,
        target.query,
        target.fragment,
    ))


def _filename_from_headers(headers, default="prowlarr-result.torrent", suffix=".torrent") -> str:
    disposition = headers.get("Content-Disposition", "")
    match = re.search(r'filename="?([^";]+)"?', disposition)
    if match:
        filename = match.group(1).strip()
        return filename if filename.lower().endswith(suffix) else f"{filename}{suffix}"
    return default


def _error_detail(data) -> str:
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error") or data.get("detail") or "")
    if isinstance(data, list) and data:
        return str(data[0])
    return ""
