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
    "🔎 <b>TorBox Bot</b>\n\n"
    "חיפוש מאוחד ב-Torrent וב-Usenet, הורדה דרך TorBox,\n"
    "ומעקב אחר הכל במקום אחד.\n\n"
    "פשוט לחץ על <b>🔍 חיפוש</b> או שלח שם ישירות."
)

HELP = (
    "ℹ️ <b>איך משתמשים בבוט?</b>\n\n"
    "🔍 <b>חיפוש מאוחד:</b> שלח שם והבוט מחפש ב-Torrent + Usenet.\n"
    "כדאי להוסיף שנה, עונה/פרק או איכות כשצריך.\n\n"
    "📎 <b>אפשר לשלוח ישירות:</b>\n"
    "• קישור <b>magnet</b>\n"
    "• קובץ <b>.torrent</b>\n"
    "• קובץ <b>.nzb</b>\n\n"
    "🔽 <b>סינון:</b> איכות, גודל, קטגוריה, מקור וזמינות בקאש\n"
    "🔃 <b>מיון:</b> זמינות/זרעים, גודל ותאריך\n"
    "📡 <b>ההורדות שלי:</b> Torrent, Usenet ו-WebDL במסך אחד\n"
    "🔗 <b>קישור ישיר:</b> הוספת URL שנתמך על ידי TorBox\n"
    "⚙️ <b>הגדרות:</b> ברירות מחדל אישיות\n"
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
        "🔗 <b>קישור ישיר</b>\n\n"
        "אפשר להדביק קישור שנתמך על ידי TorBox ולהוסיף אותו להורדות.\n"
        "קיים גם חיפוש WebDL ניסיוני כמקור משלים."
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb.debrid_menu())
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb.debrid_menu())
