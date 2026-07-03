"""
handlers/status.py — מעקב הורדות, קישורי הורדה, ביטול.
"""
from telegram import Update
from telegram.ext import ContextTypes

import config
import database as db
from handlers.auth import require_role
from services import torbox_api, keyboards as kb, formatter as fmt, public_links


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

    try:
        queued_torrents = await torbox_api.queued_list("torrent")
        queued_webdls = await torbox_api.queued_list("webdl")
    except Exception as e:
        # Import logging locally to prevent any import loop or missing logger reference
        import logging
        logging.getLogger(__name__).warning(f"Failed to fetch queued downloads for status: {e}")
        queued_torrents = []
        queued_webdls = []

    if isinstance(torrents, dict):
        torrents = [torrents]
    torrents = torrents or []

    if isinstance(webdls, dict):
        webdls = [webdls]
    webdls = webdls or []
    for w in webdls:
        w["is_webdl"] = True

    if isinstance(queued_torrents, dict):
        queued_torrents = [queued_torrents]
    queued_torrents = queued_torrents or []
    for qt in queued_torrents:
        qt["is_queued"] = True
        qt["progress"] = 0

    if isinstance(queued_webdls, dict):
        queued_webdls = [queued_webdls]
    queued_webdls = queued_webdls or []
    for qw in queued_webdls:
        qw["is_queued"] = True
        qw["is_webdl"] = True
        qw["progress"] = 0

    items = torrents + webdls + queued_torrents + queued_webdls

    # בדיקה האם יש לפחות הורדה אחת שהושלמה בכל הרשימה
    has_finished_anywhere = False
    btn_items_all = []
    for it in items:
        is_webdl = it.get("is_webdl", False)
        is_queued = it.get("is_queued", False)
        tid = str(it.get("id") or it.get("torrent_id") or it.get("webdl_id"))
        
        if is_queued:
            if is_webdl:
                tid = f"qw_{tid}"
            else:
                tid = f"qt_{tid}"
        elif is_webdl:
            tid = f"w_{tid}"
            
        name = it.get("name", "?")
        progress = it.get("progress", 0) or 0
        pct = round(progress * 100) if progress <= 1 else round(progress)
        finished = not is_queued and (it.get("download_finished") or it.get("download_present") or it.get("download_state") == "completed" or pct >= 100)
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

    try:
        await edit(text, parse_mode="HTML",
                   reply_markup=kb.status_keyboard(page_btn_items, page=page, total_pages=total_pages, has_finished_anywhere=has_finished_anywhere),
                   disable_web_page_preview=True)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            raise



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
            public_url = None
            try:
                public_url = await public_links.get_or_create_download_url(
                    user_id=q.from_user.id,
                    item_type="webdl" if is_webdl else "torrent",
                    torbox_id=tid,
                )
            except Exception:
                public_url = None

            if public_url:
                text = (
                    f"🔗 <b>קישור הורדה קבוע:</b>\n\n{public_url}\n\n"
                    "הקישור יוצר קישור TorBox חדש בכל לחיצה, בלי לחשוף את ה-API key."
                )
            else:
                text = (
                    f"🔗 <b>קישור הורדה:</b>\n\n{link}\n\n"
                    "⚠️ הקישור זמני — הורד בקרוב."
                )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ מחק הורדה זו מהחשבון", callback_data=f"cancel:{tid_raw}")]
            ])
            await q.message.reply_text(
                text,
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
    
    is_queued_torrent = tid_raw.startswith("qt_")
    is_queued_webdl = tid_raw.startswith("qw_")
    is_webdl = tid_raw.startswith("w_")
    
    if is_queued_torrent:
        tid = tid_raw[3:]
    elif is_queued_webdl:
        tid = tid_raw[3:]
    elif is_webdl:
        tid = tid_raw[2:]
    else:
        tid = tid_raw

    try:
        if is_queued_torrent:
            await torbox_api.delete_queued(tid, "torrent")
        elif is_queued_webdl:
            await torbox_api.delete_queued(tid, "webdl")
        elif is_webdl:
            await torbox_api.delete_webdl(tid)
            await db.disable_public_links_for_item("webdl", tid)
        else:
            await torbox_api.delete_torrent(int(tid))
            await db.disable_public_links_for_item("torrent", tid)
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
    deleted_items = []
    
    # בדיקת טורנטים
    for t in torrents:
        tid = t.get("id") or t.get("torrent_id")
        progress = t.get("progress", 0) or 0
        pct = round(progress * 100) if progress <= 1 else round(progress)
        finished = t.get("download_finished") or t.get("download_present") or pct >= 100
        if finished and tid:
            delete_tasks.append(torbox_api.delete_torrent(int(tid)))
            deleted_items.append(("torrent", tid))
            
    # בדיקת הורדות ישירות
    for w in webdls:
        wid = w.get("id") or w.get("webdl_id")
        progress = w.get("progress", 0) or 0
        pct = round(progress * 100) if progress <= 1 else round(progress)
        finished = w.get("download_finished") or w.get("download_present") or w.get("download_state") == "completed" or pct >= 100
        if finished and wid:
            delete_tasks.append(torbox_api.delete_webdl(str(wid)))
            deleted_items.append(("webdl", wid))
            
    if not delete_tasks:
        await q.answer("📭 לא נמצאו הורדות שהושלמו למחיקה", show_alert=True)
        await show_status(update, context)
        return
        
    try:
        await asyncio.gather(*delete_tasks)
        for item_type, item_id in deleted_items:
            await db.disable_public_links_for_item(item_type, item_id)
        await q.answer("✅ היסטוריית ההורדות נמחקה בהצלחה!", show_alert=True)
    except Exception as e:
        await q.answer(f"חלק מהמחיקות נכשלו: {e}", show_alert=True)
        
    await show_status(update, context)
