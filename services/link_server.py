"""Small aiohttp server that redirects stable public links to fresh TorBox URLs."""
import logging
import time

from aiohttp import web

import config
import database as db
from services import public_links, torbox_api

logger = logging.getLogger(__name__)

_rate_buckets: dict[tuple[str, str, int], int] = {}


def _route_path() -> str:
    prefix = config.PUBLIC_LINK_PATH_PREFIX.strip("/")
    return f"/{prefix}/{{token}}" if prefix else "/{token}"


def _client_ip(request: web.Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.headers.get("X-Real-IP") or request.remote or "unknown"


def _rate_limited(token: str, client_ip: str) -> bool:
    limit = config.PUBLIC_LINK_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return False

    bucket = int(time.time() // 60)
    key = (token, client_ip, bucket)
    _rate_buckets[key] = _rate_buckets.get(key, 0) + 1

    if len(_rate_buckets) > 10000:
        stale = [k for k in _rate_buckets if k[2] < bucket - 1]
        for stale_key in stale:
            _rate_buckets.pop(stale_key, None)

    return _rate_buckets[key] > limit


def _extract_download_url(data) -> str | None:
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return data.get("link") or data.get("url")
    return None


def _plain(status: int, message: str) -> web.Response:
    return web.Response(status=status, text=message, content_type="text/plain")


async def handle_public_download(request: web.Request) -> web.StreamResponse:
    token = request.match_info.get("token", "").strip()
    if not token:
        return _plain(404, "Download link not found.")

    client_ip = _client_ip(request)
    if _rate_limited(token, client_ip):
        return _plain(429, "Too many requests. Please try again in a minute.")

    row = await db.get_public_link(token)
    if not row:
        return _plain(404, "Download link not found or disabled.")

    item_type = row.get("item_type")
    torbox_id = row.get("torbox_id")
    file_id = row.get("file_id") or None

    try:
        if item_type == "webdl":
            data = await torbox_api.request_webdl_link(torbox_id, file_id=file_id)
        else:
            data = await torbox_api.request_download_link(torbox_id, file_id=file_id)

        download_url = _extract_download_url(data)
        if not download_url:
            logger.warning("[PUBLIC_LINK] TorBox returned no URL for token=%s...", token[:6])
            return _plain(404, "The download is not available yet. Please try again later.")

        await db.record_public_link_access(token)
        raise web.HTTPFound(location=download_url)
    except web.HTTPException:
        raise
    except Exception as exc:
        logger.warning("[PUBLIC_LINK] Failed to refresh token=%s...: %s", token[:6], exc)
        return _plain(
            502,
            "Could not create a fresh TorBox link. The file may no longer exist in TorBox.",
        )


async def start_link_server(application):
    if not public_links.is_enabled():
        logger.info("Public download links disabled. Set PUBLIC_BASE_URL to enable them.")
        return

    app = web.Application()
    app.router.add_get(_route_path(), handle_public_download)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.PUBLIC_LINK_HOST, config.PUBLIC_LINK_PORT)
    await site.start()

    application.bot_data["public_link_runner"] = runner
    logger.info(
        "Public download link server listening on %s:%s%s; public base URL: %s",
        config.PUBLIC_LINK_HOST,
        config.PUBLIC_LINK_PORT,
        _route_path().replace("{token}", "<token>"),
        config.PUBLIC_BASE_URL,
    )


async def stop_link_server(application):
    runner = application.bot_data.pop("public_link_runner", None)
    if runner:
        await runner.cleanup()
