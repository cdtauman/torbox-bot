"""Helpers for stable public download links."""
from urllib.parse import quote

import config
import database as db


def is_enabled() -> bool:
    return bool(config.PUBLIC_LINKS_ENABLED and config.PUBLIC_BASE_URL)


def _path_prefix() -> str:
    prefix = config.PUBLIC_LINK_PATH_PREFIX.strip("/")
    return f"/{prefix}" if prefix else ""


def build_public_url(token: str) -> str:
    return f"{config.PUBLIC_BASE_URL}{_path_prefix()}/{quote(token)}"


async def get_or_create_download_url(
    user_id: int,
    item_type: str,
    torbox_id,
    name: str = "",
    file_id=None,
) -> str | None:
    if not is_enabled() or not torbox_id:
        return None

    token = await db.get_or_create_public_link(
        user_id=user_id,
        item_type=item_type,
        torbox_id=torbox_id,
        name=name,
        file_id=file_id,
    )
    return build_public_url(token)
