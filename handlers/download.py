"""
handlers/download.py — הוספת הורדות ל-TorBox:
מתוך תוצאת חיפוש, מקישור magnet, או מקובץ .torrent.
"""
import os
import tempfile

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
        if r.get("cached") and r.get("magnet"):
            data = await torbox_api.add_magnet(r["magnet"])
        elif r.get("magnet") and not r.get("generated_magnet"):
            data = await torbox_api.add_magnet(r["magnet"])
        elif r.get("source") == "prowlarr" and r.get("torrent_url"):
            filename, content = await prowlarr_api.fetch_torrent(r["torrent_url"])
            data = await torbox_api.add_torrent_file(filename, content)
        elif r.get("magnet"):
            data = await torbox_api.add_magnet(r["magnet"])
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

    torbox_id = (data or {}).get("torrent_id") or (data or {}).get("id")
    await db.log_download(q.from_user.id, r["name"], r["size"], torbox_id, r["hash"])

    eta = "מיידית ⚡" if r["cached"] else "מספר דקות"
    await q.edit_message_text(
        f"✅ <b>נוסף בהצלחה!</b>\n\n"
        f"📋 {fmt.escape(r['name'][:60])}\n"
        f"📦 {parser.human_size(r['size'])}\n"
        f"⏱ זמן משוער: {eta}\n\n"
        f"עקוב אחר ההתקדמות ב'ההורדות שלי' 📡",
        parse_mode="HTML",
        reply_markup=kb.main_menu(await _is_admin(q.from_user.id)))


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


# ───────────────────────── קובץ .torrent ─────────────────────────
@require_role(config.ROLE_USER)
async def handle_torrent_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".torrent"):
        return
    status = await update.message.reply_text("📥 מעבד את קובץ ה-torrent...")
    path = ""
    try:
        tg_file = await doc.get_file()
        tmp_dir = tempfile.gettempdir()
        path = os.path.join(tmp_dir, doc.file_name)
        await tg_file.download_to_drive(path)

        with open(path, "rb") as f:
            data = await torbox_api.add_torrent_file(doc.file_name, f.read())
        torbox_id = data.get("torrent_id") or data.get("id")
        name = data.get("name", doc.file_name)
        await db.log_download(update.effective_user.id, name, 0, torbox_id, "")
        await status.edit_text(f"✅ נוסף בהצלחה!\n📋 {fmt.escape(name[:60])}", parse_mode="HTML")
    except torbox_api.TorBoxError as e:
        await status.edit_text(f"⚠️ {e}")
    except Exception as e:
        await status.edit_text(f"⚠️ שגיאה בעיבוד הקובץ: {e}")
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


async def _is_admin(user_id):
    user = await db.get_user(user_id)
    return user and user["role"] >= config.ROLE_ADMIN
