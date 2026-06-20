"""
handlers/admin.py — פאנל ניהול: אישור/השהיה/מחיקה/קידום משתמשים,
סטטיסטיקות, ושידור הודעות.
"""
from telegram import Update
from telegram.ext import ContextTypes

import config
import database as db
from handlers.auth import require_role
from services import keyboards as kb, formatter as fmt


# ───────────────────────── פאנל ראשי ─────────────────────────
@require_role(config.ROLE_ADMIN)
async def show_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        edit = q.edit_message_text
    else:
        edit = update.message.reply_text

    pending = await db.list_users(config.ROLE_PENDING)
    await edit(
        "👑 <b>פאנל ניהול</b>\n\nבחר פעולה:",
        parse_mode="HTML", reply_markup=kb.admin_menu(len(pending)))


# ───────────────────────── רשימת משתמשים ─────────────────────────
@require_role(config.ROLE_ADMIN)
async def list_users_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    users = await db.list_users()
    await q.edit_message_text(
        f"👥 <b>משתמשים ({len(users)}):</b>\n\nבחר משתמש לניהול:",
        parse_mode="HTML", reply_markup=kb.users_list_keyboard(users))


@require_role(config.ROLE_ADMIN)
async def pending_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pending = await db.list_users(config.ROLE_PENDING)
    if not pending:
        await q.edit_message_text("✅ אין בקשות הצטרפות ממתינות.",
                                  reply_markup=kb.admin_menu(0))
        return
    await q.edit_message_text(
        f"⏳ <b>ממתינים לאישור ({len(pending)}):</b>",
        parse_mode="HTML", reply_markup=kb.pending_keyboard(pending))


@require_role(config.ROLE_ADMIN)
async def view_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """uview:<user_id>"""
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split(":")[1])
    user = await db.get_user(target_id)
    if not user:
        await q.answer("המשתמש לא נמצא", show_alert=True)
        return
    await q.edit_message_text(
        fmt.user_detail(user), parse_mode="HTML",
        reply_markup=kb.user_admin_keyboard(target_id, user["role"]))


# ───────────────────────── פעולות על משתמש ─────────────────────────
@require_role(config.ROLE_ADMIN)
async def user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """uadm:<action>:<user_id>"""
    q = update.callback_query
    _, action, target_id = q.data.split(":", 2)
    target_id = int(target_id)

    actor = await db.get_user(q.from_user.id)
    target = await db.get_user(target_id)
    if not target:
        await q.answer("המשתמש לא נמצא", show_alert=True)
        return

    # הגנה: רק בעלים יכול לגעת במנהלים
    if target["role"] >= config.ROLE_ADMIN and actor["role"] < config.ROLE_OWNER:
        await q.answer("⛔ רק הבעלים יכול לנהל מנהלים", show_alert=True)
        return

    notify_text = None
    if action == "approve":
        await db.set_role(target_id, config.ROLE_USER)
        notify_text = "🎉 חשבונך אושר! שלח /start כדי להתחיל."
        await q.answer("✅ המשתמש אושר")
    elif action == "ban":
        await db.set_role(target_id, config.ROLE_BANNED)
        notify_text = "🚫 חשבונך הושהה על ידי מנהל."
        await q.answer("🚫 המשתמש הושהה")
    elif action == "unban":
        await db.set_role(target_id, config.ROLE_USER)
        notify_text = "♻️ ההשהיה בוטלה. שלח /start."
        await q.answer("♻️ ההשהיה בוטלה")
    elif action == "promote":
        await db.set_role(target_id, config.ROLE_ADMIN)
        notify_text = "👑 קודמת לדרגת מנהל!"
        await q.answer("👑 קודם למנהל")
    elif action == "demote":
        await db.set_role(target_id, config.ROLE_USER)
        await q.answer("⬇️ הורד למשתמש")
    elif action == "delete":
        await db.delete_user(target_id)
        await q.answer("🗑️ המשתמש נמחק")
        users = await db.list_users()
        await q.edit_message_text(
            f"🗑️ המשתמש נמחק.\n\n👥 משתמשים ({len(users)}):",
            parse_mode="HTML", reply_markup=kb.users_list_keyboard(users))
        return

    # התראה למשתמש
    if notify_text:
        try:
            await context.bot.send_message(target_id, notify_text)
        except Exception:
            pass

    # רענון תצוגה
    updated = await db.get_user(target_id)
    if updated:
        await q.edit_message_text(
            fmt.user_detail(updated), parse_mode="HTML",
            reply_markup=kb.user_admin_keyboard(target_id, updated["role"]))


# ───────────────────────── סטטיסטיקות ─────────────────────────
@require_role(config.ROLE_ADMIN)
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    stats = await db.get_stats()
    counts = await db.count_users_by_role()
    await q.edit_message_text(
        fmt.stats_view(stats, counts), parse_mode="HTML",
        reply_markup=kb.admin_menu(counts.get(config.ROLE_PENDING, 0)))


# ───────────────────────── שידור ─────────────────────────
@require_role(config.ROLE_ADMIN)
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["awaiting_broadcast"] = True
    await q.edit_message_text(
        "📢 <b>שידור הודעה</b>\n\n"
        "שלח עכשיו את ההודעה שתישלח לכל המשתמשים המאושרים.\n"
        "לביטול — שלח /cancel",
        parse_mode="HTML", reply_markup=kb.back_home())


async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """נקרא מתוך הראוטר כשממתינים לטקסט שידור."""
    context.user_data["awaiting_broadcast"] = False
    text = update.message.text
    users = (await db.list_users(config.ROLE_USER) +
             await db.list_users(config.ROLE_ADMIN) +
             await db.list_users(config.ROLE_OWNER))
    sent = failed = 0
    status = await update.message.reply_text(f"📢 שולח ל-{len(users)} משתמשים...")
    for u in users:
        try:
            await context.bot.send_message(u["user_id"], f"📢 הודעה מהנהלה:\n\n{text}")
            sent += 1
        except Exception:
            failed += 1
    await status.edit_text(f"✅ נשלח ל-{sent} משתמשים.\n❌ נכשל: {failed}")
