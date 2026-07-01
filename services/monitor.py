"""
services/monitor.py — משימת רקע לניטור השלמת הורדות ושליחת התראות.
מבצע בדיקה מול TorBox ומסנכרן מול בסיס הנתונים המקומי.
"""
import asyncio
import logging
import time
import datetime
import database as db
from services import torbox_api

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


async def check_downloads_status(application):
    """בודק את סטטוס ההורדות שעדיין לא נשלחה עבורן התראה."""
    # 1. שליפת הורדות לא מדווחות מבסיס הנתונים
    unnotified = await db.get_unnotified_downloads()
    if not unnotified:
        return

    # מיפוי לפי torbox_id ולפי hash לצורך חיפוש מהיר
    db_map_by_id = {}
    db_map_by_hash = {}
    for dl in unnotified:
        tid = dl.get("torbox_id")
        thash = dl.get("hash")
        if tid is not None:
            db_map_by_id.setdefault(str(tid), []).append(dl)
        if thash:
            db_map_by_hash.setdefault(thash.lower().strip(), []).append(dl)

    if not db_map_by_id and not db_map_by_hash:
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
        tid = str(item.get("id") or item.get("torrent_id") or "")
        item_hash = (item.get("hash") or item.get("info_hash") or "").lower().strip()

        # חיפוש רשומות מתאימות בבסיס הנתונים
        matching_dls = []
        if tid in db_map_by_id:
            matching_dls.extend(db_map_by_id[tid])
        if item_hash and item_hash in db_map_by_hash:
            for dl in db_map_by_hash[item_hash]:
                if dl not in matching_dls:
                    matching_dls.append(dl)

        if not matching_dls:
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
        for dl in matching_dls:
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
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=text,
                            parse_mode="HTML",
                            disable_web_page_preview=True
                        )
                        await db.mark_download_as_notified(dl["id"])
                        logger.info("[MONITOR] Successfully notified user %s with link for %s", user_id, dl["name"])
                    else:
                        # אם עבר פחות מ-60 דקות מאז שהטורנט נוצר, נמתין לסיבוב הבא כדי לקבל קישור תקין
                        c_time = parse_time(item.get("created_at"))
                        now = datetime.datetime.utcnow()
                        age_min = (now - c_time).total_seconds() / 60.0 if c_time else 999
                        
                        if age_min >= 60:
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
                            await db.mark_download_as_notified(dl["id"])
                            logger.info("[MONITOR] Notified user %s without link (timeout) for %s", user_id, dl["name"])
                        else:
                            logger.info("[MONITOR] Link for %s (ID: %s) is not ready yet (age: %.1f min). Retrying in next cycle...", dl["name"], tid, age_min)
                except Exception as e:
                    logger.warning("[MONITOR] Failed to send message to user %s: %s", user_id, e)
            else:
                # משתמש כיבה התראות - פשוט מסמנים כנודע
                await db.mark_download_as_notified(dl["id"])



async def check_and_clean_old_torrents():
    """
    מנגנון ניקוי אוטומטי המבוסס על שתי רמות:
    1. מחיקת הורדות שהושלמו (Finished) ושגילן עולה על שעתיים (120 דקות).
    2. מחיקת ההורדה הפעילה הכי ישנה (גיל >= 30 דק') במידה ויש הורדות בתור הממתינות ל-Slot פנוי.
    """
    try:
        queued_torrents = await torbox_api.queued_list("torrent")
        queued_webdls = await torbox_api.queued_list("webdl")
    except Exception as e:
        logger.warning("[CLEANUP] Failed to fetch queued items: %s", e)
        return

    if isinstance(queued_torrents, dict):
        queued_torrents = [queued_torrents]
    queued_torrents = queued_torrents or []
    
    if isinstance(queued_webdls, dict):
        queued_webdls = [queued_webdls]
    queued_webdls = queued_webdls or []

    total_queued = len(queued_torrents) + len(queued_webdls)

    try:
        torrents = await torbox_api.my_list()
        webdls = await torbox_api.webdl_list()
    except Exception as e:
        logger.warning("[CLEANUP] Failed to fetch active items: %s", e)
        return

    if isinstance(torrents, dict):
        torrents = [torrents]
    torrents = torrents or []

    if isinstance(webdls, dict):
        webdls = [webdls]
    webdls = webdls or []

    all_active = []
    
    now = datetime.datetime.utcnow()

    # בונים רשימה של הורדות פעילות/שהושלמו בשרת
    for t in torrents:
        c_time = parse_time(t.get("created_at"))
        if c_time:
            progress = t.get("progress", 0) or 0
            pct = round(progress * 100) if progress <= 1 else round(progress)
            finished = bool(t.get("download_finished") or t.get("download_present") or t.get("download_state") == "completed" or pct >= 100)
            
            all_active.append({
                "id": t.get("id") or t.get("torrent_id"),
                "name": t.get("name"),
                "created_at": c_time,
                "is_webdl": False,
                "finished": finished
            })

    for w in webdls:
        c_time = parse_time(w.get("created_at"))
        if c_time:
            progress = w.get("progress", 0) or 0
            pct = round(progress * 100) if progress <= 1 else round(progress)
            finished = bool(w.get("download_finished") or w.get("download_present") or w.get("download_state") == "completed" or pct >= 100)
            
            all_active.append({
                "id": w.get("id") or w.get("webdl_id"),
                "name": w.get("name"),
                "created_at": c_time,
                "is_webdl": True,
                "finished": finished
            })

    if not all_active:
        return

    # ─── שלב 1: מחיקת קבצים שהושלמו ועבר עליהם שעתיים (120 דקות) ───
    deleted_any = False
    remaining_active = []
    for item in all_active:
        age_minutes = (now - item["created_at"]).total_seconds() / 60.0
        if item["finished"] and age_minutes >= 120:
            logger.info("[CLEANUP] Retention policy: Deleting finished download %r (age %.1f min >= 120 min) to keep account clean...", 
                        item["name"], age_minutes)
            try:
                if item["is_webdl"]:
                    await torbox_api.delete_webdl(item["id"])
                else:
                    await torbox_api.delete_torrent(int(item["id"]))
                deleted_any = True
            except Exception as e:
                logger.error("[CLEANUP] Failed to delete finished item %s: %s", item["id"], e)
                remaining_active.append(item)
        else:
            remaining_active.append(item)

    # ─── שלב 2: מנגנון סבב הורדות (Queue Rotator) - רק אם יש קבצים שממתינים בתור ───
    if total_queued > 0:
        logger.info("[CLEANUP] Found %d items waiting in the queue. Evaluating active queue rotation...", total_queued)
        if not remaining_active:
            logger.info("[CLEANUP] No remaining active downloads found to rotate.")
            return

        # מיון לפי תאריך יצירה עולה (הכי ישן ראשון)
        remaining_active.sort(key=lambda x: x["created_at"])
        oldest = remaining_active[0]

        age_minutes = (now - oldest["created_at"]).total_seconds() / 60.0
        logger.info("[CLEANUP] Oldest active download is %r (ID: %s, created: %s), age is %.1f minutes", 
                    oldest["name"], oldest["id"], oldest["created_at"], age_minutes)

        if age_minutes >= 30:
            logger.info("[CLEANUP] Queue Rotator: Deleting oldest active download %r (age %.1f min >= 30 min) to free up slot for queued items...", 
                        oldest["name"], age_minutes)
            try:
                if oldest["is_webdl"]:
                    await torbox_api.delete_webdl(oldest["id"])
                else:
                    await torbox_api.delete_torrent(int(oldest["id"]))
                logger.info("[CLEANUP] Successfully deleted %r", oldest["name"])
                deleted_any = True
            except Exception as e:
                logger.error("[CLEANUP] Failed to rotate oldest item %s: %s", oldest["id"], e)
        else:
            logger.info("[CLEANUP] Oldest active download %r is only %.1f minutes old (< 30 min). Waiting...", 
                        oldest["name"], age_minutes)

    # ─── שלב 3: הפעלה יזומה של ההורדה הבאה בתור במידה והתפנה slot ───
    if total_queued > 0 and (deleted_any or len(remaining_active) < 3):
        next_queued = None
        qtype = "torrent"
        if queued_torrents:
            next_queued = queued_torrents[0]
            qtype = "torrent"
        elif queued_webdls:
            next_queued = queued_webdls[0]
            qtype = "webdl"

        if next_queued:
            qid = next_queued.get("id")
            logger.info("[CLEANUP] Attempting to start queued item %r (ID: %s)...", next_queued.get("name"), qid)
            try:
                await torbox_api.control_queued(qid, "start", qtype)
                logger.info("[CLEANUP] Successfully started queued item %r", next_queued.get("name"))
            except Exception as e:
                logger.warning("[CLEANUP] Failed to start queued item %s: %s", qid, e)



