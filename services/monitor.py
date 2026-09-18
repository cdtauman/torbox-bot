"""
services/monitor.py — משימת רקע לניטור השלמת הורדות ושליחת התראות.
מבצע בדיקה מול TorBox ומסנכרן מול בסיס הנתונים המקומי.
"""
import asyncio
import logging
import time
import datetime
import config
import database as db
from services import public_links, torbox_api

logger = logging.getLogger(__name__)


def parse_time(t_str):
    if not t_str:
        return None
    t_str = t_str.replace("Z", "")
    if "." in t_str:
        t_str = t_str.split(".")[0]
    try:
        return datetime.datetime.fromisoformat(t_str)
    except Exception:
        return None



async def start_monitoring(application):
    """מפעיל משימת רקע אסינכרונית לבדיקת סטטוס הורדות."""
    logger.info("Starting background download monitor task...")
    
    # ריצה ראשונית מיידית עם עליית הבוט
    try:
        await check_downloads_status(application)
        await check_and_clean_old_torrents()
    except Exception as e:
        logger.exception("Error in initial background download monitor run: %s", e)

    while True:
        try:
            await asyncio.sleep(45)  # בדיקה כל 45 שניות
            await check_downloads_status(application)
            await check_and_clean_old_torrents()
        except asyncio.CancelledError:
            logger.info("Background download monitor task cancelled.")
            break
        except Exception as e:
            logger.exception("Error in background download monitor: %s", e)


def _as_list(value):
    if isinstance(value, dict):
        return [value]
    return value or []


def _item_id(item: dict, item_type: str) -> str:
    fields = {
        "torrent": ("id", "torrent_id"),
        "usenet": ("id", "usenet_id", "usenetdownload_id"),
        "webdl": ("id", "webdl_id", "webdownload_id"),
    }[item_type]
    for field in fields:
        value = item.get(field)
        if value is not None:
            return str(value)
    return ""


def _is_finished(item: dict) -> bool:
    progress = item.get("progress", 0) or 0
    pct = progress * 100 if progress <= 1 else progress
    return bool(
        item.get("download_finished")
        or item.get("download_present")
        or item.get("download_state") == "completed"
        or pct >= 100
    )


async def _request_link(item_type: str, item_id):
    if item_type == "usenet":
        return await torbox_api.request_usenet_link(item_id)
    if item_type == "webdl":
        return await torbox_api.request_webdl_link(item_id)
    return await torbox_api.request_download_link(item_id)


async def check_downloads_status(application):
    """בודק השלמות ושולח התראות עבור Torrent, Usenet ו-WebDL."""
    unnotified = await db.get_unnotified_downloads()
    if not unnotified:
        return

    try:
        torrents, usenet, webdls = await asyncio.gather(
            torbox_api.my_list(),
            torbox_api.usenet_list(),
            torbox_api.webdl_list(),
        )
    except Exception as e:
        logger.warning("[MONITOR] Failed to fetch TorBox download lists: %s", e)
        return

    items_by_type = {
        "torrent": _as_list(torrents),
        "usenet": _as_list(usenet),
        "webdl": _as_list(webdls),
    }

    by_type_and_id = {}
    torrent_by_hash = {}
    for item_type, items in items_by_type.items():
        for item in items:
            tid = _item_id(item, item_type)
            if tid:
                by_type_and_id[(item_type, tid)] = item
            if item_type == "torrent":
                item_hash = (item.get("hash") or item.get("info_hash") or "").lower().strip()
                if item_hash:
                    torrent_by_hash[item_hash] = item

    for dl in unnotified:
        item_type = dl.get("item_type") or "torrent"
        if item_type not in ("torrent", "usenet", "webdl"):
            item_type = "torrent"

        tid = str(dl.get("torbox_id") or "")
        item = by_type_and_id.get((item_type, tid))

        if not item and item_type == "torrent":
            thash = (dl.get("hash") or "").lower().strip()
            if thash:
                item = torrent_by_hash.get(thash)
                if item:
                    tid = _item_id(item, "torrent")

        if not item or not _is_finished(item):
            continue

        logger.info(
            "[MONITOR] %s %s finished. Preparing notification for user=%s.",
            item_type,
            tid,
            dl.get("user_id"),
        )

        link = None
        try:
            link_data = await _request_link(item_type, tid)
            if isinstance(link_data, str):
                link = link_data
            elif isinstance(link_data, dict):
                link = link_data.get("link") or link_data.get("url")
        except Exception as e:
            logger.warning("[MONITOR] Failed to fetch %s link for %s: %s", item_type, tid, e)

        user_id = dl["user_id"]
        user = await db.get_user(user_id)
        notify_enabled = True
        if user and isinstance(user.get("settings"), dict):
            notify_enabled = bool(user["settings"].get("notify", 1))

        if not notify_enabled:
            await db.mark_download_as_notified(dl["id"])
            continue

        try:
            if link:
                public_url = None
                try:
                    public_url = await public_links.get_or_create_download_url(
                        user_id=user_id,
                        item_type=item_type,
                        torbox_id=tid,
                        name=dl.get("name", ""),
                    )
                except Exception as e:
                    logger.warning("[MONITOR] Failed to create public link for %s: %s", tid, e)

                download_url = public_url or link
                source_badge = {
                    "torrent": "🧲 Torrent",
                    "usenet": "📰 Usenet",
                    "webdl": "🔗 WebDL",
                }[item_type]
                link_label = "קישור הורדה קבוע" if public_url else "קישור הורדה ישיר"
                link_note = (
                    "הקישור מרענן קישור TorBox בכל לחיצה."
                    if public_url
                    else "⚠️ הקישור זמני — מומלץ להשתמש בו בקרוב."
                )
                text = (
                    f"🎉 <b>ההורדה שלך מוכנה!</b>\n\n"
                    f"📋 {dl['name'][:100]}\n"
                    f"🌐 {source_badge}\n\n"
                    f"🔗 <b>{link_label}:</b>\n{download_url}\n\n"
                    f"{link_note}"
                )
                await application.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                await db.mark_download_as_notified(dl["id"])
            else:
                c_time = parse_time(item.get("created_at"))
                now = datetime.datetime.utcnow()
                age_min = (now - c_time).total_seconds() / 60.0 if c_time else 999

                if age_min >= 60:
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "🎉 <b>ההורדה שלך מוכנה!</b>\n\n"
                            f"📋 {dl['name'][:100]}\n\n"
                            "📡 ניתן לקבל את הקישור מתפריט 'ההורדות שלי'."
                        ),
                        parse_mode="HTML",
                    )
                    await db.mark_download_as_notified(dl["id"])
                else:
                    logger.info(
                        "[MONITOR] Link for %s %s is not ready yet (age %.1f min).",
                        item_type,
                        tid,
                        age_min,
                    )
        except Exception as e:
            logger.warning("[MONITOR] Failed to notify user %s: %s", user_id, e)


async def _delete_item(item_type: str, item_id):
    if item_type == "usenet":
        await torbox_api.delete_usenet(item_id)
    elif item_type == "webdl":
        await torbox_api.delete_webdl(item_id)
    else:
        await torbox_api.delete_torrent(int(item_id))
    await db.disable_public_links_for_item(item_type, item_id)


async def check_and_clean_old_torrents():
    """
    שומר תאימות לשם הישן, אבל מטפל כיום בכל סוגי ההורדות:
    Torrent, Usenet ו-WebDL.
    """
    try:
        queued_torrents, queued_usenet, queued_webdls = await asyncio.gather(
            torbox_api.queued_list("torrent"),
            torbox_api.queued_list("usenet"),
            torbox_api.queued_list("webdl"),
        )
        torrents, usenet, webdls = await asyncio.gather(
            torbox_api.my_list(),
            torbox_api.usenet_list(),
            torbox_api.webdl_list(),
        )
    except Exception as e:
        logger.warning("[CLEANUP] Failed to fetch TorBox items: %s", e)
        return

    queued_by_type = {
        "torrent": _as_list(queued_torrents),
        "usenet": _as_list(queued_usenet),
        "webdl": _as_list(queued_webdls),
    }
    active_by_type = {
        "torrent": _as_list(torrents),
        "usenet": _as_list(usenet),
        "webdl": _as_list(webdls),
    }
    total_queued = sum(len(items) for items in queued_by_type.values())

    now = datetime.datetime.utcnow()
    all_active = []
    for item_type, items in active_by_type.items():
        for raw in items:
            c_time = parse_time(raw.get("created_at"))
            item_id = _item_id(raw, item_type)
            if not c_time or not item_id:
                continue
            all_active.append({
                "id": item_id,
                "name": raw.get("name") or "?",
                "created_at": c_time,
                "item_type": item_type,
                "finished": _is_finished(raw),
            })

    if not all_active:
        return

    deleted_any = False
    remaining_active = []
    completed_ttl = config.AUTO_DELETE_COMPLETED_AFTER_MINUTES

    # 1. Retention להורדות שהושלמו.
    for item in all_active:
        age_minutes = (now - item["created_at"]).total_seconds() / 60.0
        if completed_ttl > 0 and item["finished"] and age_minutes >= completed_ttl:
            logger.info(
                "[CLEANUP] Deleting finished %s %r (age %.1f min >= %s).",
                item["item_type"],
                item["name"],
                age_minutes,
                completed_ttl,
            )
            try:
                await _delete_item(item["item_type"], item["id"])
                deleted_any = True
            except Exception as e:
                logger.error(
                    "[CLEANUP] Failed to delete finished %s %s: %s",
                    item["item_type"],
                    item["id"],
                    e,
                )
                remaining_active.append(item)
        else:
            remaining_active.append(item)

    # 2. אם יש תור תקוע, מפנים את ההורדה הפעילה הישנה ביותר לפי המדיניות.
    if total_queued > 0 and remaining_active:
        rotation_candidates = list(remaining_active)
        if completed_ttl <= 0:
            rotation_candidates = [item for item in rotation_candidates if not item["finished"]]

        if rotation_candidates:
            oldest = min(rotation_candidates, key=lambda item: item["created_at"])
            age_minutes = (now - oldest["created_at"]).total_seconds() / 60.0
            rotate_after = config.QUEUE_ROTATE_ACTIVE_AFTER_MINUTES

            if rotate_after > 0 and age_minutes >= rotate_after:
                logger.info(
                    "[CLEANUP] Rotating oldest %s %r (age %.1f min >= %s).",
                    oldest["item_type"],
                    oldest["name"],
                    age_minutes,
                    rotate_after,
                )
                try:
                    await _delete_item(oldest["item_type"], oldest["id"])
                    deleted_any = True
                    remaining_active = [item for item in remaining_active if item is not oldest]
                except Exception as e:
                    logger.error(
                        "[CLEANUP] Failed to rotate %s %s: %s",
                        oldest["item_type"],
                        oldest["id"],
                        e,
                    )

    # 3. אחרי שהתפנה מקום, מתחילים פריט ממתין. סדר יציב: Torrent, Usenet, WebDL.
    if total_queued > 0 and (deleted_any or len(remaining_active) < 3):
        next_queued = None
        qtype = None
        for candidate_type in ("torrent", "usenet", "webdl"):
            if queued_by_type[candidate_type]:
                next_queued = queued_by_type[candidate_type][0]
                qtype = candidate_type
                break

        if next_queued and qtype:
            qid = next_queued.get("id") or next_queued.get("queued_id")
            if qid is not None:
                try:
                    await torbox_api.control_queued(qid, "start", qtype)
                    logger.info(
                        "[CLEANUP] Started queued %s item %r.",
                        qtype,
                        next_queued.get("name"),
                    )
                except Exception as e:
                    logger.warning(
                        "[CLEANUP] Failed to start queued %s %s: %s",
                        qtype,
                        qid,
                        e,
                    )

