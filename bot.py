"""
bot.py — נקודת הכניסה הראשית.
מאתחל את הבוט, רושם את כל ה-handlers, ומנתב לחיצות כפתורים.
הרצה:  python bot.py
"""
import logging

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

import config
import database as db
from handlers import menu, search, filters as filt, download, status, settings, admin
from handlers.auth import require_role

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ───────────────────────── ראוטר טקסט חופשי ─────────────────────────
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    מנתב הודעות טקסט:
    - magnet link  → הורדה
    - מצב שידור    → שידור (אדמין)
    - אחרת         → חיפוש
    """
    text = (update.message.text or "").strip()

    # שידור ממתין?
    if context.user_data.get("awaiting_broadcast"):
        await admin.do_broadcast(update, context)
        return

    # magnet?
    if text.lower().startswith("magnet:?"):
        await download.handle_magnet(update, context)
        return

    # אחרת — חיפוש
    await search.do_search(update, context)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_broadcast"] = False
    context.user_data["awaiting_search"] = False
    await update.message.reply_text("בוטל. שלח /start לתפריט הראשי.")


# ───────────────────────── ראוטר כפתורים ─────────────────────────
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מנתב את כל לחיצות הכפתורים לפי תחילית ה-callback_data."""
    q = update.callback_query
    data = q.data or ""

    # noop — כפתורי כותרת
    if data == "noop":
        await q.answer()
        return

    try:
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
        await q.answer("פעולה לא מזוהה")
    except Exception as e:
        logger.exception("Error in callback router")
        try:
            await q.answer(f"שגיאה: {e}", show_alert=True)
        except Exception:
            pass


# ───────────────────────── אתחול ─────────────────────────
async def post_init(application: Application):
    await db.init_db()
    logger.info("Database initialized.")


def main():
    if not config.BOT_TOKEN:
        raise SystemExit("❌ חסר BOT_TOKEN בקובץ .env")
    if not config.TORBOX_API_KEY:
        raise SystemExit("❌ חסר TORBOX_API_KEY בקובץ .env")

    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()

    # פקודות
    app.add_handler(CommandHandler("start", menu.cmd_start))
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
