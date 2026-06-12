"""
handlers/search.py — חיפוש, תצוגת תוצאות, ניווט, פרטי פריט.
שומר את תוצאות החיפוש ב-context.user_data כדי לאפשר עימוד וסינון מהיר.
"""
from telegram import Update
from telegram.ext import ContextTypes
import logging

import config
import database as db
from handlers.auth import require_role
from services import torbox_api, parser, keyboards as kb, formatter as fmt

logger = logging.getLogger(__name__)


# ───────────────────────── בקשת חיפוש ─────────────────────────
async def prompt_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """לחיצה על 'חיפוש' — מבקש מהמשתמש להקליד."""
    q = update.callback_query
    await q.answer()
    context.user_data["awaiting_search"] = True
    await q.edit_message_text(
        "🔍 <b>מה לחפש?</b>\n\n"
        "שלח שם של סרט, סדרה, משחק או תוכנה.\n"
        "טיפ: אפשר להוסיף איכות, למשל <code>Dune 2160p</code>",
        parse_mode="HTML", reply_markup=kb.back_home())


# ───────────────────────── ביצוע חיפוש ─────────────────────────
@require_role(config.ROLE_USER)
async def do_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מקבל טקסט חופשי ומבצע חיפוש ב-TorBox."""
    query = update.message.text.strip()
    user = update.effective_user
    context.user_data["awaiting_search"] = False
    logger.info(f"[SEARCH] START | user={user.id} | query={query!r}")

    status_msg = await update.message.reply_text("🔍 מחפש בכל המקורות...")

    try:
        raw_results = await torbox_api.search(query)
    except torbox_api.TorBoxError as e:
        logger.error(f"[SEARCH] TorBoxError | user={user.id} | query={query!r} | error={e}")
        await status_msg.edit_text(f"⚠️ שגיאה בחיפוש:\n{e}")
        return
    except Exception as e:
        logger.exception(f"[SEARCH] Unexpected error | user={user.id} | query={query!r}")
        await status_msg.edit_text(f"⚠️ שגיאה לא צפויה: {e}")
        return

    # נרמול
    results = [parser.normalize(r) for r in raw_results]
    cached_count = sum(1 for r in results if r.get("cached"))
    logger.info(f"[SEARCH] DONE | user={user.id} | query={query!r} | total={len(results)} | cached={cached_count}")
    await db.log_search(update.effective_user.id, query, len(results))

    if not results:
        logger.info(f"[SEARCH] NO RESULTS | user={user.id} | query={query!r}")
        await status_msg.edit_text(
            f"😕 לא נמצאו תוצאות עבור <b>{fmt.escape(query)}</b>.\n"
            "נסה ניסוח אחר.",
            parse_mode="HTML", reply_markup=kb.back_home())
        return

    # שמירת state
    context.user_data["query"] = query
    context.user_data["all_results"] = results
    context.user_data["temp_filter"] = {}
    user_db = await db.get_user(update.effective_user.id)
    context.user_data["settings"] = user_db["settings"]

    await _render_results(status_msg, context, page=0)


# ───────────────────────── רינדור תוצאות ─────────────────────────
async def _render_results(message, context, page=0):
    """מסנן, ממיין, ומציג עמוד תוצאות. message = אובייקט הודעה לעריכה."""
    settings = context.user_data.get("settings", dict(config.DEFAULT_SETTINGS))
    temp = context.user_data.get("temp_filter", {})
    all_results = context.user_data.get("all_results", [])

    filtered = parser.apply_filters(all_results, settings, temp)

    # רשת ביטחון: אם הסינון מחק הכל אבל יש תוצאות גולמיות — מציגים את כולן
    # (עדיף תוצאות עם הערה מאשר מסך ריק). זה ה"דינמי, לא נוקשה" שביקשת.
    filters_dropped_all = bool(all_results) and not filtered
    if filters_dropped_all:
        filtered = list(all_results)

    filtered = parser.apply_sort(
        filtered,
        sort_by=temp.get("sort_by", settings.get("sort_by", "seeders")),
        desc=bool(temp.get("sort_desc", settings.get("sort_desc", 1))),
    )
    context.user_data["filtered"] = filtered
    logger.debug(f"[RENDER] query={context.user_data.get('query')!r} | all={len(all_results)} | filtered={len(filtered)} | page={page} | fallback={filters_dropped_all}")

    if not filtered:
        await message.edit_text(
            "😕 לא נמצאו תוצאות.",
            parse_mode="HTML", reply_markup=kb.results_keyboard([], 0, 1, 0))
        return

    per_page = settings.get("per_page", 5)
    total_pages = max(1, (len(filtered) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    context.user_data["page"] = page

    start = page * per_page
    page_items = [(start + i, r) for i, r in enumerate(filtered[start:start + per_page])]

    text = fmt.results_page(
        context.user_data.get("query", ""),
        page_items, page, total_pages, len(filtered),
        active_filters=bool(temp))
    markup = kb.results_keyboard(page_items, page, total_pages, len(filtered))
    await message.edit_text(text, parse_mode="HTML", reply_markup=markup,
                            disable_web_page_preview=True)


# ───────────────────────── ניווט עמודים ─────────────────────────
async def page_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    page = int(q.data.split(":")[1])
    await _render_results(q.message, context, page=page)


async def back_to_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await _render_results(q.message, context, page=context.user_data.get("page", 0))


# ───────────────────────── פרטי פריט ─────────────────────────
async def show_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gidx = int(q.data.split(":")[1])
    filtered = context.user_data.get("filtered", [])
    if gidx >= len(filtered):
        await q.answer("התוצאה כבר לא זמינה", show_alert=True)
        return
    r = filtered[gidx]
    context.user_data["current_item"] = gidx
    await q.edit_message_text(
        fmt.item_detail(r), parse_mode="HTML",
        reply_markup=kb.item_keyboard(gidx, cached=r["cached"]),
        disable_web_page_preview=True)
