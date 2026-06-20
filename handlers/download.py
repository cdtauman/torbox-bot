"""
handlers/download.py — הוספת הורדות ל-TorBox:
מתוך תוצאת חיפוש, מקישור magnet, או מקובץ .torrent.
"""
import os
import tempfile
import asyncio
import uuid

from telegram import Update
from telegram.ext import ContextTypes

import config
import database as db
from handlers.auth import require_role
from services import torbox_api, prowlarr_api, keyboards as kb, formatter as fmt, parser


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
        await q.edit_message_text(f"⚠️ {e}", reply_markup=kb.back_home())
        return
    except Exception as e:
        await q.edit_message_text(f"⚠️ שגיאה: {e}", reply_markup=kb.back_home())
        return

    is_webdl_download = r.get("is_webdl", False)
    if is_webdl_download:
        torbox_id = (data or {}).get("data", {}).get("webdl_id") or (data or {}).get("webdl_id")
    else:
        torbox_id = (data or {}).get("torrent_id") or (data or {}).get("id")
        
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
        await _try_send_direct_link(q.message, torbox_id, is_webdl=is_webdl_download)


# ───────────────────────── magnet ישיר ─────────────────────────
@require_role(config.ROLE_USER)
async def handle_magnet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    magnet = update.message.text.strip()
    status = await update.message.reply_text("📥 מוסיף את ה-magnet ל-TorBox...")
    try:
        data = await torbox_api.add_magnet(magnet)
    except Exception as e:
        await status.edit_text(f"⚠️ שגיאה: {e}")
        return
    torbox_id = (data or {}).get("torrent_id") or (data or {}).get("id")
    name = (data or {}).get("name", "magnet")
    await db.log_download(update.effective_user.id, name, 0, torbox_id, "")
    await status.edit_text(
        f"✅ נוסף בהצלחה!\n📋 {fmt.escape(name[:60])}\n\n"
        f"עקוב ב'ההורדות שלי' 📡",
        parse_mode="HTML")

    if torbox_id:
        await _try_send_direct_link(update.message, torbox_id)


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
        await db.log_download(update.effective_user.id, name, 0, torbox_id, "")
        await status.edit_text(f"✅ נוסף בהצלחה!\n📋 {fmt.escape(name[:60])}", parse_mode="HTML")

        if torbox_id:
            await _try_send_direct_link(update.message, torbox_id)

    except torbox_api.TorBoxError as e:
        await status.edit_text(f"⚠️ {e}")
    except Exception as e:
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
    except Exception as e:
        logger.error(f"[DEBRID CONVERT] Error during conversion: {e}")
        await status.edit_text(f"⚠️ שגיאה: {e}")
        return
        
    torbox_id = (data or {}).get("data", {}).get("webdl_id") or (data or {}).get("webdl_id")
    name = (data or {}).get("data", {}).get("name") or "WebDL Download"
    await db.log_download(update.effective_user.id, name, 0, torbox_id, "")
    await status.edit_text(
        f"✅ נוסף בהצלחה להורדות ישירות!\n📋 {fmt.escape(name[:60])}\n\n"
        f"עקוב ב'ההורדות שלי' 📡",
        parse_mode="HTML")

    if torbox_id:
        await _try_send_direct_link(update.message, torbox_id, is_webdl=True)

async def _try_send_direct_link(message, torbox_id, is_webdl=False):
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
                await message.reply_text(
                    f"🔗 <b>קישור הורדה ישיר מוכן עבורך:</b>\n\n{link}\n\n"
                    "⚠️ הקישור זמני — הורד בקרוב.",
                    parse_mode="HTML", disable_web_page_preview=True
                )
                return
        except Exception:
            pass


async def _is_admin(user_id):
    user = await db.get_user(user_id)
    return user and user["role"] >= config.ROLE_ADMIN
