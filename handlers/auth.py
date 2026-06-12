"""
handlers/auth.py — בדיקות הרשאה ועטיפות (decorators).
"""
from functools import wraps

import config
import database as db


async def get_role(user_id: int) -> int:
    user = await db.get_user(user_id)
    return user["role"] if user else config.ROLE_PENDING


def require_role(min_role):
    """
    Decorator שמוודא שלמשתמש יש לפחות את התפקיד הנדרש.
    עובד גם על הודעות וגם על callback queries.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user = update.effective_user
            if not user:
                return
            role = await get_role(user.id)
            await db.touch_user(user.id)

            if role >= min_role:
                return await func(update, context, *args, **kwargs)

            # אין הרשאה — הודעה מתאימה
            if role == config.ROLE_BANNED:
                msg = "🚫 חשבונך הושהה. פנה למנהל."
            elif role == config.ROLE_PENDING:
                msg = ("⏳ חשבונך ממתין לאישור מנהל.\n"
                       "תקבל הודעה ברגע שתאושר.")
            else:
                msg = "⛔ אין לך הרשאה לפעולה זו."

            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            elif update.message:
                await update.message.reply_text(msg)
            return
        return wrapper
    return decorator


def is_admin(role: int) -> bool:
    return role >= config.ROLE_ADMIN
