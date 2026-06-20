"""
handlers/menu.py — תפריט ראשי, /start, עזרה, ניתוב כפתורי תפריט.
"""
from telegram import Update
from telegram.ext import ContextTypes

import config
import database as db
from handlers.auth import get_role, is_admin, require_role
from services import keyboards as kb

WELCOME = (
    "🎬 <b>ברוך הבא ל-TorBox Bot!</b>\n\n"
    "חיפוש והורדת טורנטים ישירות דרך TorBox —\n"
    "פשוט, מהיר, והכל בלחיצת כפתור.\n\n"
    "מה תרצה לעשות?"
)

HELP = (
    "ℹ️ <b>איך משתמשים בבוט?</b>\n\n"
    "🔍 <b>חיפוש:</b>\n"
    "פשוט שלח שם של סרט / סדרה / משחק / תוכנה,\n"
    "ואני אחפש בכל המקורות של TorBox.\n\n"
    "אפשר גם לשלוח ישירות:\n"
    "• קישור <b>magnet</b>\n"
    "• קובץ <b>.torrent</b>\n\n"
    "🔽 <b>סינון:</b> לפי איכות, גודל, קטגוריה, זמינות בקאש\n"
    "🔃 <b>מיון:</b> לפי זרעים, גודל, תאריך\n"
    "⚡ <b>קאש:</b> תוצאות עם ⚡ זמינות להורדה מיידית\n\n"
    "📡 <b>ההורדות שלי:</b> מעקב בזמן אמת + קישורי הורדה\n"
    "⚙️ <b>הגדרות:</b> התאמה אישית של ברירות המחדל\n"
)


def clear_user_states(context):
    context.user_data["awaiting_broadcast"] = False
    context.user_data["awaiting_search"] = False
    context.user_data["awaiting_debrid_search"] = False
    context.user_data["awaiting_debrid_convert"] = False
    search_task = context.user_data.get("search_task")
    if search_task and not search_task.done():
        try:
            search_task.cancel()
        except Exception:
            pass
    context.user_data["search_task"] = None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_user_states(context)
    user = update.effective_user
    existing = await db.get_user(user.id)
    if not existing:
        await db.register_user(user.id, user.username or "", user.first_name or "")
        role = config.ROLE_OWNER if user.id == config.OWNER_ID else config.ROLE_PENDING
        if role == config.ROLE_PENDING:
            await update.message.reply_text(
                "👋 שלום! בקשתך נשלחה למנהל לאישור.\n"
                "⏳ תקבל הודעה ברגע שחשבונך יאושר.")
            await _notify_admins_new_user(context, user)
            return
    else:
        role = existing["role"]

    if role == config.ROLE_PENDING:
        await update.message.reply_text(
            "⏳ חשבונך עדיין ממתין לאישור מנהל.")
        return
    if role == config.ROLE_BANNED:
        await update.message.reply_text("🚫 חשבונך הושהה.")
        return

    # Send persistent bottom keyboard
    await update.message.reply_text(
        WELCOME, parse_mode="HTML", reply_markup=kb.persistent_menu())
    
    # If admin, inform they have admin panel in commands
    if is_admin(role):
        await update.message.reply_text(
            "👑 פאנל הניהול זמין עבורך בתפריט הפקודות בצד או בפקודה /admin"
        )


async def _notify_admins_new_user(context, user):
    """שולח התראה לכל המנהלים על בקשת הצטרפות חדשה."""
    admins = await db.list_users(config.ROLE_ADMIN)
    owners = await db.list_users(config.ROLE_OWNER)
    name = user.username or user.first_name or str(user.id)
    text = (f"🔔 בקשת הצטרפות חדשה:\n"
            f"👤 {name}\n🆔 <code>{user.id}</code>")
    from services import keyboards
    markup = keyboards.user_admin_keyboard(user.id, config.ROLE_PENDING)
    for admin in admins + owners:
        try:
            await context.bot.send_message(admin["user_id"], text,
                                           parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass


@require_role(config.ROLE_USER)
async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מציג את התפריט הראשי."""
    clear_user_states(context)
    q = update.callback_query
    if q:
        await q.answer()
        role = await get_role(q.from_user.id)
        await q.edit_message_text(
            WELCOME, parse_mode="HTML", reply_markup=kb.main_menu(is_admin(role)))
    else:
        role = await get_role(update.effective_user.id)
        await update.message.reply_text(
            WELCOME, parse_mode="HTML", reply_markup=kb.persistent_menu())
        if is_admin(role):
            await update.message.reply_text(
                "👑 פאנל הניהול זמין עבורך בתפריט הפקודות בצד או בפקודה /admin"
            )


@require_role(config.ROLE_USER)
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_user_states(context)
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text(HELP, parse_mode="HTML", reply_markup=kb.back_home())
    else:
        await update.message.reply_text(HELP, parse_mode="HTML", reply_markup=kb.back_home())

@require_role(config.ROLE_USER)
async def show_debrid_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_user_states(context)
    text = (
        "📥 <b>חיפוש והורדה ישירה (Debrid)</b>\n\n"
        "בחר אפשרות:\n"
        "• <b>חיפוש לפי שם (נסיוני):</b> יחפש הורדות ישירות ל-Rapidgator באתר RLSBB.\n"
        "• <b>המרת קישור:</b> שלח קישור פרימיום שיש לך (למשל Rapidgator) כדי להמיר אותו מיד דרך TorBox."
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb.debrid_menu())
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb.debrid_menu())
