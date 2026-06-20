"""
handlers/status.py — מעקב הורדות, קישורי הורדה, ביטול.
"""
from telegram import Update
from telegram.ext import ContextTypes

import config
from handlers.auth import require_role
from services import torbox_api, keyboards as kb, formatter as fmt


@require_role(config.ROLE_USER)
async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מציג את כל ההורדות הפעילות + כפתורי פעולה."""
    context.user_data["awaiting_broadcast"] = False
    context.user_data["awaiting_search"] = False
    search_task = context.user_data.get("search_task")
    if search_task and not search_task.done():
        try:
            search_task.cancel()
        except Exception:
            pass
    context.user_data["search_task"] = None

    q = update.callback_query
    if q:
        await q.answer()
        edit = q.edit_message_text
    else:
        edit = update.message.reply_text

    try:
        items = await torbox_api.my_list()
    except Exception as e:
        await edit(f"⚠️ שגיאה בטעינת ההורדות: {e}", reply_markup=kb.back_home())
        return

    if isinstance(items, dict):
        items = [items]
    items = items or []

    text = fmt.status_list(items)
    btn_items = []
    for it in items:
        tid = it.get("id") or it.get("torrent_id")
        name = it.get("name", "?")
        finished = it.get("download_finished") or it.get("download_present") or \
                   (it.get("progress", 0) or 0) >= 1
        btn_items.append((tid, name, finished))

    await edit(text, parse_mode="HTML",
               reply_markup=kb.status_keyboard(btn_items),
               disable_web_page_preview=True)


async def get_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """link:<torbox_id> — מבקש קישור הורדה ישיר."""
    q = update.callback_query
    await q.answer("🔗 מכין קישור...")
    tid = q.data.split(":")[1]
    try:
        data = await torbox_api.request_download_link(tid)
        link = data if isinstance(data, str) else (data or {}).get("link") or str(data)
        await q.message.reply_text(
            f"🔗 <b>קישור הורדה:</b>\n\n{link}\n\n"
            "⚠️ הקישור זמני — הורד בקרוב.",
            parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        await q.answer(f"שגיאה: {e}", show_alert=True)


async def cancel_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """cancel:<torbox_id> — מבטל/מוחק הורדה."""
    q = update.callback_query
    tid = q.data.split(":")[1]
    try:
        await torbox_api.delete_torrent(int(tid))
        await q.answer("❌ ההורדה בוטלה")
    except Exception as e:
        await q.answer(f"שגיאה: {e}", show_alert=True)
        return
    await show_status(update, context)
