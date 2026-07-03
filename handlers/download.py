"""
handlers/download.py — הוספת הורדות ל-TorBox:
מתוך תוצאת חיפוש, מקישור magnet, או מקובץ .torrent.
"""
import os
import tempfile
import asyncio
import uuid
import logging
logger = logging.getLogger(__name__)

from telegram import Update
from telegram.ext import ContextTypes

import config
import database as db
from handlers.auth import require_role
from services import torbox_api, prowlarr_api, keyboards as kb, formatter as fmt, parser, public_links


# ───────────────────────── הורדה מתוצאה ─────────────────────────
async def download_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """dl:<gidx> — מוסיף את הטוררנט הנבחר ל-TorBox."""
    q = update.callback_query
    gidx = int(q.data.split(":")[1])
    filtered = context.user_data.get("filtered", [])
    if gidx >= len(filtered):
        await q.answer("התוצאה כבר לא זמינה", show_alert=True)
        return
    r = filtered[gidx]
    await q.answer("📥 מוסיף ל-TorBox...")

    msg = "⚡ כבר בקאש! מוסיף ומכין הורדה..." if r["cached"] else "📥 שולח לשרת TorBox..."
    await q.edit_message_text(msg)

    try:
        magnet = r.get("magnet")
        torrent_url = r.get("torrent_url")
        source = r.get("source")

        if r.get("is_webdl"):
            webdl_link = magnet or torrent_url
            if webdl_link:
                logger.info(f"[DOWNLOAD] Sending WebDL link to TorBox: {webdl_link[:80]}")
                data = await torbox_api.create_webdl(webdl_link)
                is_webdl_download = True
            else:
                raise ValueError("לא נמצא קישור תקין להורדה")
        elif r.get("cached") and magnet:
            data = await torbox_api.add_magnet(magnet)
        elif magnet and not r.get("generated_magnet"):
            data = await torbox_api.add_magnet(magnet)
        elif source == "prowlarr" and torrent_url:
            try:
                filename, content = await prowlarr_api.fetch_torrent(torrent_url)
                data = await torbox_api.add_torrent_file(filename, content)
            except prowlarr_api.MagnetRedirect as mr:
                data = await torbox_api.add_magnet(mr.magnet_url)
        elif magnet:
            data = await torbox_api.add_magnet(magnet)
        elif r.get("hash"):
            data = await torbox_api.add_hash(r["hash"])
        else:
            await q.edit_message_text("⚠️ לתוצאה הזו אין magnet, hash או קובץ torrent.", reply_markup=kb.back_home())
            return
    except prowlarr_api.ProwlarrError as e:
        await q.edit_message_text(f"⚠️ {e}", reply_markup=kb.back_home())
        return
    except torbox_api.TorBoxError as e:
        err_msg = str(e)
        if "already queued" in err_msg.lower():
            handled = await _handle_already_queued(q.from_user.id, r.get("name"), r.get("hash"), is_webdl=r.get("is_webdl", False), status_msg=q.message)
            if handled:
                return
        if "cannot be downloaded" in err_msg.lower() or "not supported" in err_msg.lower():
            err_msg += "\n\nייתכן שה-Hoster (למשל Rapidgator) כרגע לא זמין ב-TorBox.\nבדוק ב: https://torbox.app/hosters"
        await q.edit_message_text(f"⚠️ {err_msg}", reply_markup=kb.back_home(), disable_web_page_preview=True)
        return

    except Exception as e:
        await q.edit_message_text(f"⚠️ שגיאה: {e}", reply_markup=kb.back_home())
        return

    is_webdl_download = r.get("is_webdl", False)
    if is_webdl_download:
        torbox_id = (data or {}).get("webdownload_id") or (data or {}).get("data", {}).get("webdownload_id")
    else:
        torbox_id = (data or {}).get("torrent_id") or (data or {}).get("id")
    logger.info(f"[DOWNLOAD] TorBox returned id={torbox_id} | is_webdl={is_webdl_download} | raw_data={data}")
        
    await db.log_download(q.from_user.id, r["name"], r["size"], torbox_id, r.get("hash", ""))

    eta = "מיידית ⚡" if r["cached"] else "מספר דקות"
    await q.edit_message_text(
        f"✅ <b>נוסף בהצלחה!</b>\n\n"
        f"📋 {fmt.escape(r['name'][:60])}\n"
        f"📦 {parser.human_size(r['size'])}\n"
        f"⏱ זמן משוער: {eta}\n\n"
        f"עקוב אחר ההתקדמות ב'ההורדות שלי' 📡",
        parse_mode="HTML",
        reply_markup=kb.main_menu(await _is_admin(q.from_user.id)))

    if torbox_id:
        await _try_send_direct_link(q.message, torbox_id, q.from_user.id, is_webdl=is_webdl_download)


# ───────────────────────── magnet ישיר ─────────────────────────
@require_role(config.ROLE_USER)
async def handle_magnet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    magnet = update.message.text.strip()
    status = await update.message.reply_text("📥 מוסיף את ה-magnet ל-TorBox...")
    try:
        data = await torbox_api.add_magnet(magnet)
    except Exception as e:
        if "already queued" in str(e).lower():
            thash, name = parse_magnet_info(magnet)
            handled = await _handle_already_queued(update.effective_user.id, name, thash, is_webdl=False, status_msg=status)
            if handled:
                return
        await status.edit_text(f"⚠️ שגיאה: {e}")
        return
    thash, parsed_name = parse_magnet_info(magnet)
    torbox_id = (data or {}).get("torrent_id") or (data or {}).get("id")
    name = (data or {}).get("name") or parsed_name or "magnet"
    item_hash = (data or {}).get("hash") or (data or {}).get("info_hash") or thash or ""
    await db.log_download(update.effective_user.id, name, 0, torbox_id, item_hash)
    await status.edit_text(
        f"✅ נוסף בהצלחה!\n📋 {fmt.escape(name[:60])}\n\n"
        f"עקוב ב'ההורדות שלי' 📡",
        parse_mode="HTML")

    if torbox_id:
        await _try_send_direct_link(update.message, torbox_id, update.effective_user.id)


# ───────────────────────── קובץ .torrent ─────────────────────────
@require_role(config.ROLE_USER)
async def handle_torrent_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name or not doc.file_name.lower().endswith(".torrent"):
        return
    status = await update.message.reply_text("📥 מעבד את קובץ ה-torrent...")
    path = ""
    try:
        tg_file = await doc.get_file()
        tmp_dir = tempfile.gettempdir()
        safe_filename = os.path.basename(doc.file_name) or "download.torrent"
        # Avoid race conditions and file collisions between concurrent users
        unique_filename = f"{uuid.uuid4()}_{safe_filename}"
        path = os.path.join(tmp_dir, unique_filename)
        await tg_file.download_to_drive(path)

        with open(path, "rb") as f:
            data = await torbox_api.add_torrent_file(safe_filename, f.read())
        torbox_id = (data or {}).get("torrent_id") or (data or {}).get("id")
        name = (data or {}).get("name") or safe_filename
        item_hash = (data or {}).get("hash") or (data or {}).get("info_hash") or ""
        await db.log_download(update.effective_user.id, name, 0, torbox_id, item_hash)
        await status.edit_text(f"✅ נוסף בהצלחה!\n📋 {fmt.escape(name[:60])}", parse_mode="HTML")

        if torbox_id:
            await _try_send_direct_link(update.message, torbox_id, update.effective_user.id)

    except torbox_api.TorBoxError as e:
        if "already queued" in str(e).lower():
            name_fallback = safe_filename[:-8] if safe_filename.lower().endswith(".torrent") else safe_filename
            handled = await _handle_already_queued(update.effective_user.id, name_fallback, "", is_webdl=False, status_msg=status)
            if handled:
                return
        await status.edit_text(f"⚠️ {e}")
    except Exception as e:
        if "already queued" in str(e).lower():
            name_fallback = safe_filename[:-8] if safe_filename.lower().endswith(".torrent") else safe_filename
            handled = await _handle_already_queued(update.effective_user.id, name_fallback, "", is_webdl=False, status_msg=status)
            if handled:
                return
        await status.edit_text(f"⚠️ שגיאה בעיבוד הקובץ: {e}")
    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


# ───────────────────────── הורדה ישירה (Debrid) ─────────────────────────
@require_role(config.ROLE_USER)
async def handle_debrid_convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    from handlers.menu import clear_user_states
    clear_user_states(context)
    
    logger.info(f"[DEBRID CONVERT] User {update.effective_user.id} requested conversion of link: {link[:60]}...")
    status = await update.message.reply_text("📥 ממיר את הקישור ב-TorBox...")
    try:
        logger.debug("[DEBRID CONVERT] Calling torbox_api.create_webdl...")
        data = await torbox_api.create_webdl(link)
        logger.debug(f"[DEBRID CONVERT] create_webdl returned successfully: {data}")
    except torbox_api.TorBoxError as e:
        err_msg = str(e)
        if "already queued" in err_msg.lower():
            import urllib.parse
            path_part = urllib.parse.urlparse(link).path
            name_fallback = os.path.basename(path_part)
            handled = await _handle_already_queued(update.effective_user.id, name_fallback, "", is_webdl=True, status_msg=status)
            if handled:
                return
        if "cannot be downloaded" in err_msg.lower() or "not supported" in err_msg.lower():
            err_msg += "\n\nייתכן שה-Hoster כרגע לא זמין ב-TorBox.\nבדוק ב: https://torbox.app/hosters"
        logger.error(f"[DEBRID CONVERT] TorBox error: {e}")
        await status.edit_text(f"⚠️ {err_msg}", disable_web_page_preview=True)
        return
    except Exception as e:
        err_msg = str(e)
        if "already queued" in err_msg.lower():
            import urllib.parse
            path_part = urllib.parse.urlparse(link).path
            name_fallback = os.path.basename(path_part)
            handled = await _handle_already_queued(update.effective_user.id, name_fallback, "", is_webdl=True, status_msg=status)
            if handled:
                return
        logger.error(f"[DEBRID CONVERT] Error during conversion: {e}")
        await status.edit_text(f"⚠️ שגיאה: {e}")
        return
        
    torbox_id = (data or {}).get("webdownload_id") or (data or {}).get("data", {}).get("webdownload_id")
    name = (data or {}).get("name") or (data or {}).get("data", {}).get("name") or "WebDL Download"
    logger.info(f"[DEBRID CONVERT] Success: torbox_id={torbox_id} | name={name} | raw_data={data}")
    await db.log_download(update.effective_user.id, name, 0, torbox_id, "")
    await status.edit_text(
        f"✅ נוסף בהצלחה להורדות ישירות!\n📋 {fmt.escape(name[:60])}\n\n"
        f"עקוב ב'ההורדות שלי' 📡",
        parse_mode="HTML")

    if torbox_id:
        await _try_send_direct_link(update.message, torbox_id, update.effective_user.id, is_webdl=True)

async def _try_send_direct_link(message, torbox_id, user_id, is_webdl=False):
    # Try up to 3 times to get the link if the torrent is cached, since TorBox API might take a few seconds to process
    for attempt in range(3):
        try:
            await asyncio.sleep(1.5)
            if is_webdl:
                dl_data = await torbox_api.request_webdl_link(torbox_id)
            else:
                dl_data = await torbox_api.request_download_link(torbox_id)
            link = None
            if isinstance(dl_data, str):
                link = dl_data
            elif isinstance(dl_data, dict):
                link = dl_data.get("link")

            if link:
                public_url = None
                try:
                    public_url = await public_links.get_or_create_download_url(
                        user_id=user_id,
                        item_type="webdl" if is_webdl else "torrent",
                        torbox_id=torbox_id,
                    )
                except Exception as e:
                    logger.warning("Failed to create public download link for %s: %s", torbox_id, e)

                if public_url:
                    text = (
                        f"🔗 <b>קישור הורדה קבוע מוכן עבורך:</b>\n\n{public_url}\n\n"
                        "הקישור יוצר קישור TorBox חדש בכל לחיצה, בלי לחשוף את ה-API key."
                    )
                else:
                    text = (
                        f"🔗 <b>קישור הורדה ישיר מוכן עבורך:</b>\n\n{link}\n\n"
                        "⚠️ הקישור זמני — הורד בקרוב."
                    )

                await message.reply_text(
                    text,
                    parse_mode="HTML", disable_web_page_preview=True
                )
                await db.mark_download_by_torbox_id_as_notified(torbox_id, user_id)
                return
        except Exception:
            pass


async def _is_admin(user_id):
    user = await db.get_user(user_id)
    return user and user["role"] >= config.ROLE_ADMIN


def parse_magnet_info(magnet: str):
    import re
    from urllib.parse import unquote
    thash = ""
    name = ""
    m_hash = re.search(r"(?i)urn:btih:([a-f0-9]{32,40})", magnet)
    if m_hash:
        thash = m_hash.group(1).lower()
    else:
        m_hash_b32 = re.search(r"(?i)urn:btih:([a-z2-7]{32})", magnet)
        if m_hash_b32:
            thash = m_hash_b32.group(1).lower()
    m_name = re.search(r"(?i)dn=([^&]+)", magnet)
    if m_name:
        name = unquote(m_name.group(1))
    return thash, name


async def _handle_already_queued(user_id, name: str, thash: str, is_webdl: bool = False, status_msg = None, reply_to_message = None):
    logger.info(f"[ALREADY_QUEUED] Handling already queued for user={user_id} | name={name!r} | hash={thash!r} | is_webdl={is_webdl}")
    try:
        if is_webdl:
            active_items = await torbox_api.webdl_list()
        else:
            active_items = await torbox_api.my_list()
    except Exception as e:
        logger.error(f"[ALREADY_QUEUED] Failed to fetch active list: {e}", exc_info=True)
        active_items = []

    if isinstance(active_items, dict):
        active_items = [active_items]
    active_items = active_items or []

    try:
        qtype = "webdl" if is_webdl else "torrent"
        queued_items = await torbox_api.queued_list(qtype)
    except Exception as e:
        logger.error(f"[ALREADY_QUEUED] Failed to fetch queued list: {e}", exc_info=True)
        queued_items = []

    if isinstance(queued_items, dict):
        queued_items = [queued_items]
    queued_items = queued_items or []

    items = active_items + queued_items
    logger.info(f"[ALREADY_QUEUED] TorBox returned {len(active_items)} active and {len(queued_items)} queued items (total: {len(items)})")


    found_item = None
    if thash:
        clean_hash = thash.lower().strip()
        logger.info(f"[ALREADY_QUEUED] Attempting match by hash: {clean_hash}")
        for item in items:
            item_hash = (item.get("hash") or item.get("info_hash") or "").lower().strip()
            logger.debug(f"  Comparing with item hash: {item_hash!r} (name: {item.get('name')!r})")
            if item_hash == clean_hash:
                logger.info(f"[ALREADY_QUEUED] Match found by hash! name={item.get('name')!r}")
                found_item = item
                break

    if not found_item and name:
        clean_name = name.lower().strip()
        logger.info(f"[ALREADY_QUEUED] Attempting match by name: {clean_name}")
        for item in items:
            item_name = (item.get("name") or "").lower().strip()
            logger.debug(f"  Comparing with item name: {item_name!r}")
            if clean_name in item_name or item_name in clean_name:
                logger.info(f"[ALREADY_QUEUED] Match found by name! name={item.get('name')!r}")
                found_item = item
                break

    if found_item:
        tid = found_item.get("id") or found_item.get("torrent_id") or found_item.get("webdl_id")

            
        progress = found_item.get("progress", 0) or 0
        pct = round(progress * 100) if progress <= 1 else round(progress)
        finished = found_item.get("download_finished") or found_item.get("download_present") or found_item.get("download_state") == "completed" or pct >= 100

        # רישום ההורדה עבור משתמש זה במסד הנתונים כדי שיקבל התראה כשתסתיים
        if not await db.is_download_logged(user_id, tid):
            await db.log_download(user_id, found_item.get("name") or name or "Download", found_item.get("size", 0), tid, thash)

        if finished:
            success_text = (
                f"✅ <b>ההורדה כבר קיימת והושלמה!</b>\n\n"
                f"📋 {fmt.escape((found_item.get('name') or name)[:60])}\n"
                f"📦 {parser.human_size(found_item.get('size', 0))}\n"
            )
            if status_msg:
                try:
                    await status_msg.edit_text(success_text, parse_mode="HTML")
                except Exception:
                    pass
            elif reply_to_message:
                await reply_to_message.reply_text(success_text, parse_mode="HTML")
                
            msg_for_link = status_msg or reply_to_message
            if msg_for_link:
                await _try_send_direct_link(msg_for_link, tid, user_id, is_webdl=is_webdl)
            return True
        else:
            progress_text = (
                f"⏳ <b>ההורדה הזו כבר נמצאת בתור ההורדות שלך ומורידה כעת!</b>\n\n"
                f"📋 {fmt.escape(found_item.get('name') or name)}\n"
                f"📊 התקדמות: {pct}%\n\n"
                f"תוכל לעקוב אחריה בתפריט 'ההורדות שלי' 📡\n"
                f"🔔 תקבל התראה אוטומטית עם קישור ברגע שהיא תסתיים!"
            )
            if status_msg:
                try:
                    await status_msg.edit_text(progress_text, parse_mode="HTML")
                except Exception:
                    pass
            elif reply_to_message:
                await reply_to_message.reply_text(progress_text, parse_mode="HTML")
            return True
    return False
