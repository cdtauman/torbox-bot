"""
handlers/filters.py — תפריטי סינון ומיון אינטראקטיביים.
משתמש ב-context.user_data['temp_filter'] לסינון זמני על תוצאות החיפוש הנוכחי.
"""
from telegram import Update
from telegram.ext import ContextTypes

import config
from services import keyboards as kb
from handlers.search import _render_results


# ───────────────────────── סינון ─────────────────────────
async def open_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    temp = context.user_data.setdefault("temp_filter", {})
    await q.edit_message_text("🔽 <b>סינון תוצאות:</b>", parse_mode="HTML",
                              reply_markup=kb.filter_menu(temp))


async def set_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """setf:field:value"""
    q = update.callback_query
    await q.answer()
    _, field, value = q.data.split(":", 2)
    temp = context.user_data.setdefault("temp_filter", {})
    # המרת ערכים מספריים
    if field in ("max_size_gb", "cached_only"):
        temp[field] = int(value)
    else:
        temp[field] = value
    await q.edit_message_reply_markup(reply_markup=kb.filter_menu(temp))


async def apply_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("✅ הסינון הוחל")
    await _render_results(q.message, context, page=0)


async def reset_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("↩️ הסינון אופס")
    context.user_data["temp_filter"] = {}
    await q.edit_message_text("🔽 <b>סינון תוצאות:</b>", parse_mode="HTML",
                              reply_markup=kb.filter_menu({}))


# ───────────────────────── מיון ─────────────────────────
async def open_sort(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    temp = context.user_data.setdefault("temp_filter", {})
    settings = context.user_data.get("settings", dict(config.DEFAULT_SETTINGS))
    sort_by = temp.get("sort_by", settings.get("sort_by", "seeders"))
    desc = bool(temp.get("sort_desc", settings.get("sort_desc", 1)))
    await q.edit_message_text("🔃 <b>מיון תוצאות:</b>", parse_mode="HTML",
                              reply_markup=kb.sort_menu(sort_by, desc))


async def set_sort(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """sets:by:field  או  sets:dir:0/1"""
    q = update.callback_query
    await q.answer()
    _, kind, value = q.data.split(":", 2)
    temp = context.user_data.setdefault("temp_filter", {})
    if kind == "by":
        temp["sort_by"] = value
    else:
        temp["sort_desc"] = int(value)
    settings = context.user_data.get("settings", dict(config.DEFAULT_SETTINGS))
    sort_by = temp.get("sort_by", settings.get("sort_by", "seeders"))
    desc = bool(temp.get("sort_desc", settings.get("sort_desc", 1)))
    await q.edit_message_reply_markup(reply_markup=kb.sort_menu(sort_by, desc))


async def apply_sort(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("✅ המיון הוחל")
    await _render_results(q.message, context, page=0)
