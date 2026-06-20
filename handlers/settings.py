"""
handlers/settings.py — הגדרות אישיות של המשתמש (ברירות מחדל לחיפוש).
"""
from telegram import Update
from telegram.ext import ContextTypes

import config
import database as db
from handlers.auth import require_role
from services import keyboards as kb, formatter as fmt


@require_role(config.ROLE_USER)
async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        user_id = q.from_user.id
        edit = q.edit_message_text
    else:
        user_id = update.effective_user.id
        edit = update.message.reply_text

    user = await db.get_user(user_id)
    s = user["settings"]
    await edit(fmt.settings_view(s), parse_mode="HTML",
               reply_markup=kb.settings_menu(s))


async def open_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """setmenu:<field> — פותח רשימת ערכים לבחירה."""
    q = update.callback_query
    await q.answer()
    field = q.data.split(":")[1]
    titles = {
        "quality": "🎬 בחר איכות מועדפת:",
        "category": "📂 בחר קטגוריית ברירת מחדל:",
        "sort_by": "🔃 בחר מיון ברירת מחדל:",
        "max_size_gb": "📦 בחר גודל מקסימלי:",
        "per_page": "📄 כמה תוצאות להציג בעמוד?",
    }
    await q.edit_message_text(titles.get(field, "בחר ערך:"),
                              reply_markup=kb.settings_option_menu(field))


async def set_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """setval:<field>:<value> — שומר ערך ומחזיר להגדרות."""
    q = update.callback_query
    await q.answer("✅ נשמר")
    _, field, value = q.data.split(":", 2)
    user = await db.get_user(q.from_user.id)
    s = user["settings"]
    if field in ("max_size_gb", "per_page"):
        s[field] = int(value)
    else:
        s[field] = value
    await db.update_settings(q.from_user.id, s)
    await q.edit_message_text(fmt.settings_view(s), parse_mode="HTML",
                              reply_markup=kb.settings_menu(s))


async def toggle_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """settoggle:<field> — מחליף בין 0/1 (cached_only, notify)."""
    q = update.callback_query
    field = q.data.split(":")[1]
    user = await db.get_user(q.from_user.id)
    s = user["settings"]
    s[field] = 0 if s.get(field) else 1
    await db.update_settings(q.from_user.id, s)
    await q.answer(f"{'✅ הופעל' if s[field] else '⬜ כובה'}")
    await q.edit_message_text(fmt.settings_view(s), parse_mode="HTML",
                              reply_markup=kb.settings_menu(s))
