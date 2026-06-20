"""
services/monitor.py — משימת רקע לניטור השלמת הורדות ושליחת התראות.
מבצע בדיקה מול TorBox ומסנכרן מול בסיס הנתונים המקומי.
"""
import asyncio
import logging
import time
import database as db
from services import torbox_api

logger = logging.getLogger(__name__)


async def start_monitoring(application):
    """מפעיל משימת רקע אסינכרונית לבדיקת סטטוס הורדות."""
    logger.info("Starting background download monitor task...")
    while True:
        try:
            await asyncio.sleep(45)  # בדיקה כל 45 שניות
            await check_downloads_status(application)
        except asyncio.CancelledError:
            logger.info("Background download monitor task cancelled.")
            break
        except Exception as e:
            logger.exception("Error in background download monitor: %s", e)


async def check_downloads_status(application):
    """בודק את סטטוס ההורדות שעדיין לא נשלחה עבורן התראה."""
    # 1. שליפת הורדות לא מדווחות מבסיס הנתונים
    unnotified = await db.get_unnotified_downloads()
    if not unnotified:
        return

    # מיפוי לפי torbox_id לצורך חיפוש מהיר
    db_map = {}
    for dl in unnotified:
        tid = dl.get("torbox_id")
        if tid is not None:
            db_map.setdefault(tid, []).append(dl)

    if not db_map:
        return

    # 2. שליפת רשימת ההורדות הפעילות מ-TorBox
    try:
        torbox_items = await torbox_api.my_list()
    except Exception as e:
        logger.warning("[MONITOR] Failed to fetch my_list from TorBox: %s", e)
        return

    if isinstance(torbox_items, dict):
        torbox_items = [torbox_items]
    torbox_items = torbox_items or []

    # 3. מעבר על ההורדות מתוך TorBox ובדיקה אם הן הושלמו
    for item in torbox_items:
        tid = item.get("id") or item.get("torrent_id")
        if not tid or tid not in db_map:
            continue

        # בדיקה האם ההורדה הסתיימה
        finished = bool(
            item.get("download_finished") or 
            item.get("download_present") or 
            (item.get("progress", 0) or 0) >= 1
        )
        if not finished:
            continue

        # הורדה הסתיימה! משיכת קישור הורדה ישיר
        logger.info("[MONITOR] Torrent %s (ID: %s) finished. Preparing notifications.", item.get("name"), tid)
        link = None
        try:
            dl_data = await torbox_api.request_download_link(tid)
            if isinstance(dl_data, str):
                link = dl_data
            elif isinstance(dl_data, dict):
                link = dl_data.get("link")
        except Exception as e:
            logger.warning("[MONITOR] Failed to fetch download link for %s: %s", tid, e)

        # שליחת התראה לכל משתמש שביקש את הטורנט הזה
        for dl in db_map[tid]:
            user_id = dl["user_id"]

            # בדיקה האם המשתמש הפעיל התראות בהגדרות שלו
            user = await db.get_user(user_id)
            notify_enabled = True
            if user and isinstance(user.get("settings"), dict):
                notify_enabled = bool(user["settings"].get("notify", 1))

            if notify_enabled:
                try:
                    if link:
                        text = (
                            f"🎉 <b>ההורדה שלך מוכנה!</b>\n\n"
                            f"📋 {dl['name'][:100]}\n\n"
                            f"🔗 <b>קישור הורדה ישיר:</b>\n{link}\n\n"
                            f"⚠️ הקישור זמני — הורד בקרוב."
                        )
                    else:
                        text = (
                            f"🎉 <b>ההורדה שלך מוכנה!</b>\n\n"
                            f"📋 {dl['name'][:100]}\n\n"
                            f"📡 ניתן לקבל את קישור ההורדה מתפריט 'ההורדות שלי'."
                        )
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.warning("[MONITOR] Failed to send message to user %s: %s", user_id, e)

            # סימון כנשלח בכל מקרה במסד הנתונים
            await db.mark_download_as_notified(dl["id"])
