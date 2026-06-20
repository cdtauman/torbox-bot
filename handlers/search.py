"""
handlers/search.py — חיפוש, תצוגת תוצאות, ניווט, פרטי פריט.
שומר את תוצאות החיפוש ב-context.user_data כדי לאפשר עימוד וסינון מהיר.
"""
from telegram import Update
from telegram.ext import ContextTypes
import asyncio
import logging

import config
import database as db
from handlers.auth import require_role
from services import torbox_api, prowlarr_api, rlsbb_api, parser, keyboards as kb, formatter as fmt

logger = logging.getLogger(__name__)
_SEARCH_SEMAPHORE = asyncio.Semaphore(max(1, config.SEARCH_CONCURRENCY))


# ───────────────────────── בקשת חיפוש ─────────────────────────
@require_role(config.ROLE_USER)
async def prompt_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """לחיצה על 'חיפוש' — מבקש מהמשתמש להקליד."""
    context.user_data["awaiting_broadcast"] = False
    search_task = context.user_data.get("search_task")
    if search_task and not search_task.done():
        try:
            search_task.cancel()
        except Exception:
            pass
    context.user_data["search_task"] = None

    context.user_data["awaiting_search"] = True
    q = update.callback_query
    text = (
        "🔍 <b>מה לחפש?</b>\n\n"
        "שלח שם של סרט, סדרה, משחק או תוכנה.\n"
        "טיפ: אפשר להוסיף איכות, למשל <code>Dune 2160p</code>"
    )
    markup = kb.back_home()
    if q:
        await q.answer()
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)

@require_role(config.ROLE_USER)
async def prompt_debrid_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.menu import clear_user_states
    clear_user_states(context)
    context.user_data["awaiting_debrid_search"] = True
    q = update.callback_query
    text = (
        "🔍 <b>חיפוש הורדות ישירות (RLSBB)</b>\n\n"
        "שלח שם של סרט או סדרה כדי לחפש קישורי פרימיום (כמו Rapidgator)."
    )
    markup = kb.back_home()
    if q:
        await q.answer()
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)

@require_role(config.ROLE_USER)
async def prompt_debrid_convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.menu import clear_user_states
    clear_user_states(context)
    context.user_data["awaiting_debrid_convert"] = True
    q = update.callback_query
    text = (
        "🔗 <b>המרת קישור פרימיום</b>\n\n"
        "הדבק כאן קישור (למשל של Rapidgator או שרת נתמך אחר) והוא יומר להורדה ישירה דרך TorBox."
    )
    markup = kb.back_home()
    if q:
        await q.answer()
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


# ───────────────────────── ביצוע חיפוש ─────────────────────────
@require_role(config.ROLE_USER)
async def do_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מקבל טקסט חופשי ומבצע חיפוש ב-TorBox."""
    query = update.message.text.strip()
    user = update.effective_user
    context.user_data["awaiting_search"] = False
    
    # ביטול משימת חיפוש קודמת אם קיימת
    search_task = context.user_data.get("search_task")
    if search_task and not search_task.done():
        try:
            search_task.cancel()
        except Exception:
            pass

    context.user_data["search_task"] = asyncio.current_task()
    logger.info(f"[SEARCH] START | user={user.id} | query={query!r}")

    status_msg = await update.message.reply_text("🔍 מחפש בכל המקורות...", reply_markup=kb.cancel_search_keyboard())

    try:
        async with _SEARCH_SEMAPHORE:
            raw_results = await _search_provider(query)
    except asyncio.CancelledError:
        logger.info(f"[SEARCH] CANCELLED | user={user.id} | query={query!r}")
        return
    except prowlarr_api.ProwlarrError as e:
        logger.error(f"[SEARCH] ProwlarrError | user={user.id} | query={query!r} | error={e}")
        await status_msg.edit_text(f"⚠️ שגיאה בחיפוש:\n{e}")
        return
    except torbox_api.TorBoxError as e:
        logger.error(f"[SEARCH] TorBoxError | user={user.id} | query={query!r} | error={e}")
        await status_msg.edit_text(f"⚠️ שגיאה בחיפוש:\n{e}")
        return
    except Exception as e:
        logger.exception(f"[SEARCH] Unexpected error | user={user.id} | query={query!r}")
        await status_msg.edit_text(f"⚠️ שגיאה לא צפויה: {e}")
        return
    finally:
        if context.user_data.get("search_task") == asyncio.current_task():
            context.user_data["search_task"] = None

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

@require_role(config.ROLE_USER)
async def do_debrid_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user = update.effective_user
    context.user_data["awaiting_debrid_search"] = False
    
    logger.info(f"[DEBRID SEARCH] START | user={user.id} | query={query!r}")
    status_msg = await update.message.reply_text("🔍 מחפש קישורים ישירים ב-RLSBB...", reply_markup=kb.cancel_search_keyboard())

    try:
        raw_results = await rlsbb_api.search(query)
    except Exception as e:
        logger.exception(f"[DEBRID SEARCH] Unexpected error | user={user.id} | query={query!r}")
        await status_msg.edit_text(f"⚠️ שגיאה בחיפוש ב-RLSBB: {e}")
        return

    logger.info(f"[DEBRID SEARCH] DONE | user={user.id} | query={query!r} | total={len(raw_results)}")
    await db.log_search(update.effective_user.id, query + " [RLSBB]", len(raw_results))

    if not raw_results:
        await status_msg.edit_text(
            f"😕 לא נמצאו תוצאות ב-RLSBB עבור <b>{fmt.escape(query)}</b> או שלא נמצאו קישורים נתמכים (Rapidgator).\n"
            "נסה ניסוח אחר.",
            parse_mode="HTML", reply_markup=kb.back_home())
        return

    context.user_data["query"] = query + " [RLSBB]"
    context.user_data["all_results"] = raw_results
    context.user_data["temp_filter"] = {}
    user_db = await db.get_user(update.effective_user.id)
    context.user_data["settings"] = user_db["settings"]

    await _render_results(status_msg, context, page=0)


async def _search_provider(query: str):
    provider = config.SEARCH_PROVIDER
    if provider == "prowlarr":
        return await prowlarr_api.search(query)
    if provider == "auto":
        try:
            return await prowlarr_api.search(query)
        except prowlarr_api.ProwlarrError as exc:
            logger.warning("[SEARCH] Prowlarr failed in auto mode, falling back to TorBox: %s", exc)
            return await torbox_api.search(query)
    return await torbox_api.search(query)


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
