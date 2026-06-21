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

    import database as db

    page = 0
    q = update.callback_query
    if q:
        await q.answer()
        edit = q.edit_message_text
        if q.data and q.data.startswith("dlpage:"):
            try:
                page = int(q.data.split(":")[1])
            except (ValueError, IndexError):
                page = 0
    else:
        edit = update.message.reply_text

    try:
        torrents = await torbox_api.my_list()
        webdls = await torbox_api.webdl_list()
    except Exception as e:
        await edit(f"⚠️ שגיאה בטעינת ההורדות: {e}", reply_markup=kb.back_home())
        return

    if isinstance(torrents, dict):
        torrents = [torrents]
    torrents = torrents or []

    if isinstance(webdls, dict):
        webdls = [webdls]
    webdls = webdls or []
    for w in webdls:
        w["is_webdl"] = True
        
    items = torrents + webdls

    # בדיקה האם יש לפחות הורדה אחת שהושלמה בכל הרשימה
    has_finished_anywhere = False
    btn_items_all = []
    for it in items:
        is_webdl = it.get("is_webdl", False)
        tid = str(it.get("id") or it.get("torrent_id") or it.get("webdl_id"))
        if is_webdl:
            tid = f"w_{tid}"
            
        name = it.get("name", "?")
        progress = it.get("progress", 0) or 0
        pct = round(progress * 100) if progress <= 1 else round(progress)
        finished = it.get("download_finished") or it.get("download_present") or it.get("download_state") == "completed" or pct >= 100
        if finished:
            has_finished_anywhere = True
        btn_items_all.append((tid, name, finished))

    # לוגיקת דפדוף
    user = await db.get_user(update.effective_user.id)
    per_page = user["settings"].get("per_page", 5) if (user and "settings" in user) else 5
    
    total_items = len(items)
    total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
        
    start_idx = page * per_page
    end_idx = start_idx + per_page
    
    page_items = items[start_idx:end_idx]
    page_btn_items = btn_items_all[start_idx:end_idx]

    text = fmt.status_list(page_items, page=page, total_pages=total_pages, total_items=total_items, start_index=start_idx+1)

    await edit(text, parse_mode="HTML",
               reply_markup=kb.status_keyboard(page_btn_items, page=page, total_pages=total_pages, has_finished_anywhere=has_finished_anywhere),
               disable_web_page_preview=True)


async def get_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """link:<torbox_id> — מבקש קישור הורדה ישיר."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    q = update.callback_query
    await q.answer("🔗 מכין קישור...")
    tid_raw = q.data.split(":")[1]
    is_webdl = tid_raw.startswith("w_")
    tid = tid_raw[2:] if is_webdl else tid_raw
    try:
        if is_webdl:
            data = await torbox_api.request_webdl_link(tid)
        else:
            data = await torbox_api.request_download_link(tid)
        link = None
        if isinstance(data, str):
            link = data
        elif isinstance(data, dict):
            link = data.get("link")

        if link:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ מחק הורדה זו מהחשבון", callback_data=f"cancel:{tid_raw}")]
            ])
            await q.message.reply_text(
                f"🔗 <b>קישור הורדה:</b>\n\n{link}\n\n"
                "⚠️ הקישור זמני — הורד בקרוב.",
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            await q.answer("⚠️ לא נמצא קישור הורדה תקין עבור טורנט זה.", show_alert=True)
    except Exception as e:
        await q.answer(f"שגיאה: {e}", show_alert=True)


async def cancel_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """cancel:<torbox_id> — מבטל/מוחק הורדה."""
    q = update.callback_query
    tid_raw = q.data.split(":")[1]
    is_webdl = tid_raw.startswith("w_")
    tid = tid_raw[2:] if is_webdl else tid_raw
    try:
        if is_webdl:
            await torbox_api.delete_webdl(tid)
        else:
            await torbox_api.delete_torrent(int(tid))
        await q.answer("❌ ההורדה בוטלה")
    except Exception as e:
        await q.answer(f"שגיאה: {e}", show_alert=True)
        return
    await show_status(update, context)


@require_role(config.ROLE_USER)
async def confirm_clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מבקש אישור לפני מחיקת כל היסטוריית ההורדות שהושלמו."""
    q = update.callback_query
    await q.answer()
    
    text = (
        "⚠️ <b>האם אתה בטוח שברצונך למחוק את כל היסטוריית ההורדות שהושלמו?</b>\n\n"
        "פעולה זו תסיר את כל ההורדות שהסתיימו מרשימת ההורדות שלך ב-TorBox. "
        "פעולה זו אינה מוחקת הורדות פעילות שנמצאות בתהליך."
    )
    await q.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=kb.confirm_clear_history_keyboard()
    )


@require_role(config.ROLE_USER)
async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מוחק את כל ההורדות שהושלמו (torrents + webdls)."""
    q = update.callback_query
    await q.answer("🗑️ מוחק היסטוריה...")
    
    try:
        torrents = await torbox_api.my_list()
        webdls = await torbox_api.webdl_list()
    except Exception as e:
        await q.answer(f"שגיאה בקבלת ההורדות: {e}", show_alert=True)
        await show_status(update, context)
        return

    if isinstance(torrents, dict):
        torrents = [torrents]
    torrents = torrents or []

    if isinstance(webdls, dict):
        webdls = [webdls]
    webdls = webdls or []
    
    import asyncio
    delete_tasks = []
    
    # בדיקת טורנטים
    for t in torrents:
        tid = t.get("id") or t.get("torrent_id")
        progress = t.get("progress", 0) or 0
        pct = round(progress * 100) if progress <= 1 else round(progress)
        finished = t.get("download_finished") or t.get("download_present") or pct >= 100
        if finished and tid:
            delete_tasks.append(torbox_api.delete_torrent(int(tid)))
            
    # בדיקת הורדות ישירות
    for w in webdls:
        wid = w.get("id") or w.get("webdl_id")
        progress = w.get("progress", 0) or 0
        pct = round(progress * 100) if progress <= 1 else round(progress)
        finished = w.get("download_finished") or w.get("download_present") or w.get("download_state") == "completed" or pct >= 100
        if finished and wid:
            delete_tasks.append(torbox_api.delete_webdl(str(wid)))
            
    if not delete_tasks:
        await q.answer("📭 לא נמצאו הורדות שהושלמו למחיקה", show_alert=True)
        await show_status(update, context)
        return
        
    try:
        await asyncio.gather(*delete_tasks)
        await q.answer("✅ היסטוריית ההורדות נמחקה בהצלחה!", show_alert=True)
    except Exception as e:
        await q.answer(f"חלק מהמחיקות נכשלו: {e}", show_alert=True)
        
    await show_status(update, context)
