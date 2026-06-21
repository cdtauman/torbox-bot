"""
bot.py — נקודת הכניסה הראשית.
מאתחל את הבוט, רושם את כל ה-handlers, ומנתב לחיצות כפתורים.
הרצה:  python bot.py
"""
import logging

from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

import config
import database as db
from handlers import menu, search, filters as filt, download, status, settings, admin
from handlers.auth import require_role
from services import keyboards as kb

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO)
# לוגים מפורטים על מודולי הבוט שלנו
logging.getLogger("__main__").setLevel(logging.DEBUG)
logging.getLogger("handlers").setLevel(logging.DEBUG)
logging.getLogger("services").setLevel(logging.DEBUG)
# שתוק את הספריות הפנימיות
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ───────────────────────── Middleware — לוג כל update ─────────────────────────
async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מתועד כל update שמגיע מטלגרם — הודעות, כפתורים, כל דבר."""
    user = update.effective_user
    uid = user.id if user else "?"
    uname = f"@{user.username}" if (user and user.username) else (user.first_name if user else "unknown")

    if update.message:
        msg = update.message
        if msg.text:
            logger.info(f"[MSG] user={uid} ({uname}) | text={msg.text!r}")
        elif msg.document:
            logger.info(f"[DOC] user={uid} ({uname}) | file={msg.document.file_name!r} size={msg.document.file_size}")
        elif msg.photo:
            logger.info(f"[PHOTO] user={uid} ({uname}) | photo received")
        elif msg.sticker:
            logger.info(f"[STICKER] user={uid} ({uname})")
        else:
            logger.info(f"[MSG-OTHER] user={uid} ({uname}) | update_id={update.update_id}")

    elif update.callback_query:
        cq = update.callback_query
        logger.info(f"[BTN] user={uid} ({uname}) | callback_data={cq.data!r}")

    elif update.inline_query:
        logger.info(f"[INLINE] user={uid} ({uname}) | query={update.inline_query.query!r}")

    else:
        logger.info(f"[UPDATE] user={uid} ({uname}) | type={list(update.parse_mode_entities() if hasattr(update,'parse_mode_entities') else [])} update_id={update.update_id}")


def clear_user_states(user_data: dict):
    user_data["awaiting_broadcast"] = False
    user_data["awaiting_search"] = False
    user_data["awaiting_debrid_search"] = False
    user_data["awaiting_debrid_convert"] = False
    search_task = user_data.get("search_task")
    if search_task and not search_task.done():
        try:
            search_task.cancel()
            logger.info("Active search task cancelled.")
        except Exception as e:
            logger.warning(f"Error cancelling search task: {e}")
    user_data["search_task"] = None


# ───────────────────────── ראוטר טקסט חופשי ─────────────────────────
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    מנתב הודעות טקסט:
    - magnet link  → הורדה
    - מצב שידור    → שידור (אדמין)
    - אחרת         → חיפוש
    """
    text = (update.message.text or "").strip()
    user = update.effective_user
    logger.debug(f"[ROUTER] text_router: user={user.id} text={text[:80]!r}")

    # שידור ממתין?
    if context.user_data.get("awaiting_broadcast"):
        logger.debug(f"[ROUTER] → do_broadcast (user={user.id})")
        await admin.do_broadcast(update, context)
        return

    # הורדות ישירות
    if context.user_data.get("awaiting_debrid_search"):
        await search.do_debrid_search(update, context)
        return
    if context.user_data.get("awaiting_debrid_convert"):
        await download.handle_debrid_convert(update, context)
        return

    # בדיקת כפתורי מקלדת קבועה
    if text == "🔍 חיפוש":
        await search.prompt_search(update, context)
        return
    elif text == "📥 חיפוש והורדה ישירה (Debrid)":
        await menu.show_debrid_menu(update, context)
        return
    elif text == "📡 ההורדות שלי":
        await status.show_status(update, context)
        return
    elif text == "⚙️ הגדרות":
        await settings.show_settings(update, context)
        return
    elif text == "ℹ️ עזרה":
        await menu.show_help(update, context)
        return
    elif text in ("❌ ביטול", "ביטול"):
        await cmd_cancel(update, context)
        return

    # magnet?
    if text.lower().startswith("magnet:?"):
        logger.debug(f"[ROUTER] → handle_magnet (user={user.id})")
        await download.handle_magnet(update, context)
        return

    # אחרת — חיפוש
    logger.debug(f"[ROUTER] → do_search (user={user.id}) query={text[:80]!r}")
    await search.do_search(update, context)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_user_states(context.user_data)
    await update.message.reply_text(
        "❌ הפעולה בוטלה. הוחזרת לתפריט הראשי.",
        reply_markup=kb.persistent_menu()
    )


# ───────────────────────── ראוטר כפתורים ─────────────────────────
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מנתב את כל לחיצות הכפתורים לפי תחילית ה-callback_data."""
    q = update.callback_query
    data = q.data or ""
    user = q.from_user
    logger.debug(f"[CALLBACK] user={user.id} (@{user.username}) | data={data!r}")

    # noop — כפתורי כותרת
    if data == "noop":
        await q.answer()
        return

    try:
        # ─── ביטול חיפוש ───
        if data == "search:cancel":
            clear_user_states(context.user_data)
            await q.answer("❌ החיפוש בוטל")
            try:
                await q.edit_message_text("❌ החיפוש בוטל. שלח חיפוש חדש או השתמש בתפריט.")
            except Exception:
                pass
            return

        # ─── תפריטים ───
        if data == "menu:home":
            return await menu.show_home(update, context)
        if data == "menu:help":
            return await menu.show_help(update, context)
        if data == "menu:search":
            return await search.prompt_search(update, context)
        if data == "menu:status":
            return await status.show_status(update, context)
        if data == "menu:settings":
            return await settings.show_settings(update, context)
        if data == "menu:admin":
            return await admin.show_admin(update, context)

        # ─── תוצאות / חיפוש ───
        if data.startswith("page:"):
            return await search.page_nav(update, context)
        if data.startswith("item:"):
            return await search.show_item(update, context)
        if data == "results:back":
            return await search.back_to_results(update, context)
            
        # ─── Debrid ───
        if data == "debrid:search":
            return await search.prompt_debrid_search(update, context)
        if data == "debrid:convert":
            return await search.prompt_debrid_convert(update, context)

        # ─── הורדה ───
        if data.startswith("dl:"):
            return await download.download_item(update, context)

        # ─── סינון ───
        if data == "filter:open":
            return await filt.open_filter(update, context)
        if data.startswith("setf:"):
            return await filt.set_filter(update, context)
        if data == "filter:apply":
            return await filt.apply_filter(update, context)
        if data == "filter:reset":
            return await filt.reset_filter(update, context)

        # ─── מיון ───
        if data == "sort:open":
            return await filt.open_sort(update, context)
        if data.startswith("sets:"):
            return await filt.set_sort(update, context)
        if data == "sort:apply":
            return await filt.apply_sort(update, context)

        # ─── הגדרות ───
        if data.startswith("setmenu:"):
            return await settings.open_option(update, context)
        if data.startswith("setval:"):
            return await settings.set_value(update, context)
        if data.startswith("settoggle:"):
            return await settings.toggle_value(update, context)

        # ─── סטטוס ───
        if data.startswith("link:"):
            return await status.get_link(update, context)
        if data.startswith("cancel:"):
            return await status.cancel_download(update, context)
        if data == "status:clear_confirm":
            return await status.confirm_clear_history(update, context)
        if data == "status:clear_confirmed":
            return await status.clear_history(update, context)
        if data.startswith("dlpage:"):
            return await status.show_status(update, context)

        # ─── אדמין ───
        if data == "admin:users":
            return await admin.list_users_view(update, context)
        if data == "admin:pending":
            return await admin.pending_view(update, context)
        if data == "admin:stats":
            return await admin.show_stats(update, context)
        if data == "admin:broadcast":
            return await admin.start_broadcast(update, context)
        if data.startswith("uview:"):
            return await admin.view_user(update, context)
        if data.startswith("uadm:"):
            return await admin.user_action(update, context)

        # לא מזוהה
        logger.warning(f"[CALLBACK] unrecognized callback_data={data!r} from user={q.from_user.id}")
        await q.answer("פעולה לא מזוהה")
    except Exception as e:
        logger.exception(f"[CALLBACK] Exception handling data={data!r} from user={q.from_user.id}")
        try:
            await q.answer(f"שגיאה: {e}", show_alert=True)
        except Exception:
            pass


# ───────────────────────── אתחול ─────────────────────────
async def post_init(application: Application):
    await db.init_db()
    logger.info("Database initialized.")
    
    # רישום תפריט הפקודות בטלגרם
    commands = [
        BotCommand("start", "תפריט ראשי"),
        BotCommand("search", "חיפוש טורנטים"),
        BotCommand("downloads", "ההורדות שלי"),
        BotCommand("settings", "הגדרות"),
        BotCommand("help", "עזרה"),
        BotCommand("admin", "פאנל ניהול"),
        BotCommand("cancel", "ביטול פעולה")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered.")

    # הפעלת משימת הניטור ברקע
    import asyncio
    from services.monitor import start_monitoring
    asyncio.create_task(start_monitoring(application))


def main():
    if not config.BOT_TOKEN:
        raise SystemExit("❌ חסר BOT_TOKEN בקובץ .env")
    if not config.TORBOX_API_KEY:
        raise SystemExit("❌ חסר TORBOX_API_KEY בקובץ .env")

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )

    # Middleware — לוג כל update לפני כל handler
    app.add_handler(MessageHandler(filters.ALL, log_all_updates), group=-1)
    app.add_handler(CallbackQueryHandler(log_all_updates), group=-1)

    # פקודות
    app.add_handler(CommandHandler("start", menu.cmd_start))
    app.add_handler(CommandHandler("search", search.prompt_search))
    app.add_handler(CommandHandler("downloads", status.show_status))
    app.add_handler(CommandHandler("settings", settings.show_settings))
    app.add_handler(CommandHandler("help", menu.show_help))
    app.add_handler(CommandHandler("admin", admin.show_admin))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # קבצי torrent
    app.add_handler(MessageHandler(filters.Document.FileExtension("torrent"),
                                   download.handle_torrent_file))

    # כפתורים
    app.add_handler(CallbackQueryHandler(callback_router))

    # טקסט חופשי (חייב להיות אחרון)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    logger.info("🤖 TorBox Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
