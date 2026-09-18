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
    """מציג Torrent, Usenet ו-WebDL במסך סטטוס אחד."""
    import asyncio
    import logging

    context.user_data["awaiting_broadcast"] = False
    context.user_data["awaiting_search"] = False
    search_task = context.user_data.get("search_task")
    if search_task and not search_task.done():
        try:
            search_task.cancel()
        except Exception:
            pass
    context.user_data["search_task"] = None

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
        torrents, usenet, webdls = await asyncio.gather(
            torbox_api.my_list(),
            torbox_api.usenet_list(),
            torbox_api.webdl_list(),
        )
    except Exception as e:
        await edit(f"⚠️ שגיאה בטעינת ההורדות: {e}", reply_markup=kb.back_home())
        return

    try:
        queued_torrents, queued_usenet, queued_webdls = await asyncio.gather(
            torbox_api.queued_list("torrent"),
            torbox_api.queued_list("usenet"),
            torbox_api.queued_list("webdl"),
        )
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to fetch queued downloads: %s", e)
        queued_torrents, queued_usenet, queued_webdls = [], [], []

    def _as_list(value):
        if isinstance(value, dict):
            return [value]
        return value or []

    torrents = _as_list(torrents)
    usenet = _as_list(usenet)
    webdls = _as_list(webdls)
    queued_torrents = _as_list(queued_torrents)
    queued_usenet = _as_list(queued_usenet)
    queued_webdls = _as_list(queued_webdls)

    for it in torrents:
        it["item_type"] = "torrent"
    for it in usenet:
        it["item_type"] = "usenet"
        it["is_usenet"] = True
    for it in webdls:
        it["item_type"] = "webdl"
        it["is_webdl"] = True

    for it, item_type in (
        *((x, "torrent") for x in queued_torrents),
        *((x, "usenet") for x in queued_usenet),
        *((x, "webdl") for x in queued_webdls),
    ):
        it["item_type"] = item_type
        it["is_queued"] = True
        it["progress"] = 0
        if item_type == "usenet":
            it["is_usenet"] = True
        elif item_type == "webdl":
            it["is_webdl"] = True

    items = torrents + usenet + webdls + queued_torrents + queued_usenet + queued_webdls

    has_finished_anywhere = False
    btn_items_all = []
    prefix_map = {
        ("torrent", False): "",
        ("usenet", False): "u_",
        ("webdl", False): "w_",
        ("torrent", True): "qt_",
        ("usenet", True): "qu_",
        ("webdl", True): "qw_",
    }

    for it in items:
        item_type = it.get("item_type", "torrent")
        is_queued = it.get("is_queued", False)
        raw_id = str(
            it.get("id")
            or it.get("torrent_id")
            or it.get("usenet_id")
            or it.get("usenetdownload_id")
            or it.get("webdl_id")
            or it.get("webdownload_id")
            or ""
        )
        tid = prefix_map[(item_type, is_queued)] + raw_id

        name = it.get("name", "?")
        progress = it.get("progress", 0) or 0
        pct = round(progress * 100) if progress <= 1 else round(progress)
        finished = not is_queued and (
            it.get("download_finished")
            or it.get("download_present")
            or it.get("download_state") == "completed"
            or pct >= 100
        )
        if finished:
            has_finished_anywhere = True
        btn_items_all.append((tid, name, finished))

    user = await db.get_user(update.effective_user.id)
    per_page = user["settings"].get("per_page", 5) if (user and "settings" in user) else 5

    total_items = len(items)
    total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1
    page = max(0, min(page, total_pages - 1))
    start_idx = page * per_page
    end_idx = start_idx + per_page

    page_items = items[start_idx:end_idx]
    page_btn_items = btn_items_all[start_idx:end_idx]
    text = fmt.status_list(
        page_items,
        page=page,
        total_pages=total_pages,
        total_items=total_items,
        start_index=start_idx + 1,
    )

    try:
        await edit(
            text,
            parse_mode="HTML",
            reply_markup=kb.status_keyboard(
                page_btn_items,
                page=page,
                total_pages=total_pages,
                has_finished_anywhere=has_finished_anywhere,
            ),
            disable_web_page_preview=True,
        )
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            raise


async def get_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מבקש קישור הורדה לפי סוג הפריט המקודד ב-callback."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    q = update.callback_query
    await q.answer("🔗 מכין קישור...")
    tid_raw = q.data.split(":")[1]

    is_usenet = tid_raw.startswith("u_")
    is_webdl = tid_raw.startswith("w_")
    if is_usenet or is_webdl:
        tid = tid_raw[2:]
    else:
        tid = tid_raw

    try:
        if is_usenet:
            data = await torbox_api.request_usenet_link(tid)
            item_type = "usenet"
        elif is_webdl:
            data = await torbox_api.request_webdl_link(tid)
            item_type = "webdl"
        else:
            data = await torbox_api.request_download_link(tid)
            item_type = "torrent"

        link = data if isinstance(data, str) else (data or {}).get("link")
        if not link:
            await q.answer("⚠️ עדיין אין קישור הורדה זמין לפריט הזה.", show_alert=True)
            return

        public_url = None
        try:
            public_url = await public_links.get_or_create_download_url(
                user_id=q.from_user.id,
                item_type=item_type,
                torbox_id=tid,
            )
        except Exception:
            public_url = None

        if public_url:
            text = (
                f"🔗 <b>קישור הורדה קבוע:</b>\n\n{public_url}\n\n"
                "הקישור מרענן קישור TorBox בעת כל לחיצה."
            )
        else:
            text = (
                f"🔗 <b>קישור הורדה:</b>\n\n{link}\n\n"
                "⚠️ הקישור הישיר זמני."
            )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ מחק הורדה זו מהחשבון", callback_data=f"cancel:{tid_raw}")]
        ])
        await q.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception as e:
        await q.answer(f"שגיאה: {e}", show_alert=True)


async def cancel_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מבטל/מוחק Torrent, Usenet או WebDL, כולל queued."""
    q = update.callback_query
    tid_raw = q.data.split(":")[1]

    queued_type = None
    if tid_raw.startswith("qt_"):
        queued_type, tid = "torrent", tid_raw[3:]
    elif tid_raw.startswith("qu_"):
        queued_type, tid = "usenet", tid_raw[3:]
    elif tid_raw.startswith("qw_"):
        queued_type, tid = "webdl", tid_raw[3:]
    elif tid_raw.startswith("u_"):
        item_type, tid = "usenet", tid_raw[2:]
    elif tid_raw.startswith("w_"):
        item_type, tid = "webdl", tid_raw[2:]
    else:
        item_type, tid = "torrent", tid_raw

    try:
        if queued_type:
            await torbox_api.delete_queued(tid, queued_type)
        elif item_type == "usenet":
            await torbox_api.delete_usenet(tid)
            await db.disable_public_links_for_item("usenet", tid)
        elif item_type == "webdl":
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
    """מוחק את כל ההורדות שהושלמו מכל שלושת הסוגים."""
    import asyncio

    q = update.callback_query
    await q.answer("🗑️ מוחק היסטוריה...")

    try:
        torrents, usenet, webdls = await asyncio.gather(
            torbox_api.my_list(),
            torbox_api.usenet_list(),
            torbox_api.webdl_list(),
        )
    except Exception as e:
        await q.answer(f"שגיאה בקבלת ההורדות: {e}", show_alert=True)
        await show_status(update, context)
        return

    def _as_list(value):
        if isinstance(value, dict):
            return [value]
        return value or []

    delete_tasks = []
    deleted_items = []

    for item_type, items in (
        ("torrent", _as_list(torrents)),
        ("usenet", _as_list(usenet)),
        ("webdl", _as_list(webdls)),
    ):
        for item in items:
            item_id = (
                item.get("id")
                or item.get("torrent_id")
                or item.get("usenet_id")
                or item.get("usenetdownload_id")
                or item.get("webdl_id")
                or item.get("webdownload_id")
            )
            progress = item.get("progress", 0) or 0
            pct = round(progress * 100) if progress <= 1 else round(progress)
            finished = (
                item.get("download_finished")
                or item.get("download_present")
                or item.get("download_state") == "completed"
                or pct >= 100
            )
            if not finished or not item_id:
                continue

            if item_type == "torrent":
                delete_tasks.append(torbox_api.delete_torrent(int(item_id)))
            elif item_type == "usenet":
                delete_tasks.append(torbox_api.delete_usenet(item_id))
            else:
                delete_tasks.append(torbox_api.delete_webdl(str(item_id)))
            deleted_items.append((item_type, item_id))

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

