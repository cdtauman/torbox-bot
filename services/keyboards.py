"""
services/keyboards.py — כל המקלדות (כפתורים) במקום אחד.
מבנה callback_data:  "פעולה:פרמטר"  (למשל "dl:3", "sort:size", "page:2")
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

import config


# ───────────────────────── תפריט ראשי ─────────────────────────
def main_menu(is_admin=False):
    rows = []
    if is_admin:
        rows.append([InlineKeyboardButton("👑 פאנל ניהול", callback_data="menu:admin")])
    return InlineKeyboardMarkup(rows) if rows else None


def persistent_menu():
    keyboard = [
        [KeyboardButton("🔍 חיפוש"), KeyboardButton("📥 חיפוש והורדות Debrid")],
        [KeyboardButton("📡 ההורדות שלי"), KeyboardButton("⚙️ הגדרות")],
        [KeyboardButton("ℹ️ עזרה")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

def debrid_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 חיפוש לפי שם (נסיוני)", callback_data="debrid:search")],
        [InlineKeyboardButton("🔗 המרת קישור", callback_data="debrid:convert")],
        [InlineKeyboardButton("🏠 ראשי", callback_data="menu:home")]
    ])


def cancel_search_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ ביטול חיפוש", callback_data="search:cancel")]])


def back_home():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 תפריט ראשי", callback_data="menu:home")]])


# ───────────────────────── תוצאות חיפוש ─────────────────────────
def results_keyboard(page_items, page, total_pages, total_results):
    """
    page_items — רשימת tuples (global_index, result)
    הכפתורים הממוספרים מובילים לפרטי הפריט.
    """
    rows = []
    # שורת כפתורים ממוספרים (עד 5 בשורה)
    num_row = []
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for pos, (gidx, _r) in enumerate(page_items):
        label = emojis[pos] if pos < len(emojis) else str(pos + 1)
        num_row.append(InlineKeyboardButton(label, callback_data=f"item:{gidx}"))
        if len(num_row) == 5:
            rows.append(num_row)
            num_row = []
    if num_row:
        rows.append(num_row)

    # ניווט עמודים
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ הקודם", callback_data=f"page:{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("הבא ▶️", callback_data=f"page:{page+1}"))
    if nav:
        rows.append(nav)

    # סינון / מיון / חיפוש חדש
    rows.append([
        InlineKeyboardButton("🔽 סינון", callback_data="filter:open"),
        InlineKeyboardButton("🔃 מיון", callback_data="sort:open"),
    ])
    rows.append([
        InlineKeyboardButton("🔍 חיפוש חדש", callback_data="menu:search"),
        InlineKeyboardButton("🏠 ראשי", callback_data="menu:home"),
    ])
    return InlineKeyboardMarkup(rows)


# ───────────────────────── פרטי פריט ─────────────────────────
def item_keyboard(gidx, cached=False):
    dl_label = "⚡ הורד (בקאש)" if cached else "⬇️ הורד עכשיו"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(dl_label, callback_data=f"dl:{gidx}")],
        [InlineKeyboardButton("◀️ חזרה לתוצאות", callback_data="results:back")],
        [InlineKeyboardButton("🏠 ראשי", callback_data="menu:home")],
    ])


# ───────────────────────── סינון ─────────────────────────
def filter_menu(temp):
    """temp — dict הסינון הזמני הנוכחי."""
    def mark(field, value):
        return " ✅" if temp.get(field) == value else ""

    rows = [[InlineKeyboardButton("— 🎬 איכות —", callback_data="noop")]]
    qrow = []
    for q in config.QUALITY_OPTIONS:
        qrow.append(InlineKeyboardButton(
            config.QUALITY_LABELS[q] + mark("quality", q),
            callback_data=f"setf:quality:{q}"))
        if len(qrow) == 3:
            rows.append(qrow); qrow = []
    if qrow:
        rows.append(qrow)

    rows.append([InlineKeyboardButton("— 📦 גודל מקסימלי —", callback_data="noop")])
    srow = []
    for gb in config.SIZE_OPTIONS_GB:
        label = "ללא הגבלה" if gb == 0 else f"{gb}GB"
        srow.append(InlineKeyboardButton(
            label + mark("max_size_gb", gb),
            callback_data=f"setf:max_size_gb:{gb}"))
        if len(srow) == 4:
            rows.append(srow); srow = []
    if srow:
        rows.append(srow)

    rows.append([InlineKeyboardButton("— 📂 קטגוריה —", callback_data="noop")])
    crow = []
    for c in config.CATEGORY_OPTIONS:
        crow.append(InlineKeyboardButton(
            config.CATEGORY_LABELS[c] + mark("category", c),
            callback_data=f"setf:category:{c}"))
        if len(crow) == 2:
            rows.append(crow); crow = []
    if crow:
        rows.append(crow)

    cached_on = temp.get("cached_only", 0)
    rows.append([InlineKeyboardButton("— ⚡ זמינות —", callback_data="noop")])
    rows.append([
        InlineKeyboardButton("כולם" + (" ✅" if not cached_on else ""), callback_data="setf:cached_only:0"),
        InlineKeyboardButton("רק קאש" + (" ✅" if cached_on else ""), callback_data="setf:cached_only:1"),
    ])

    rows.append([
        InlineKeyboardButton("✅ החל סינון", callback_data="filter:apply"),
        InlineKeyboardButton("↩️ איפוס", callback_data="filter:reset"),
    ])
    rows.append([InlineKeyboardButton("◀️ חזרה לתוצאות", callback_data="results:back")])
    return InlineKeyboardMarkup(rows)


# ───────────────────────── מיון ─────────────────────────
def sort_menu(sort_by, desc):
    def mark(v):
        return " ✅" if sort_by == v else ""
    rows = [[InlineKeyboardButton("— מיין לפי —", callback_data="noop")]]
    srow = []
    for s in config.SORT_OPTIONS:
        srow.append(InlineKeyboardButton(config.SORT_LABELS[s] + mark(s), callback_data=f"sets:by:{s}"))
        if len(srow) == 2:
            rows.append(srow); srow = []
    if srow:
        rows.append(srow)
    rows.append([
        InlineKeyboardButton("⬆️ עולה" + (" ✅" if not desc else ""), callback_data="sets:dir:0"),
        InlineKeyboardButton("⬇️ יורד" + (" ✅" if desc else ""), callback_data="sets:dir:1"),
    ])
    rows.append([
        InlineKeyboardButton("✅ החל", callback_data="sort:apply"),
        InlineKeyboardButton("◀️ חזרה", callback_data="results:back"),
    ])
    return InlineKeyboardMarkup(rows)


# ───────────────────────── הגדרות ─────────────────────────
def settings_menu(settings):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 איכות מועדפת", callback_data="setmenu:quality"),
         InlineKeyboardButton("📦 גודל מקסימלי", callback_data="setmenu:max_size_gb")],
        [InlineKeyboardButton("📂 קטגוריה", callback_data="setmenu:category"),
         InlineKeyboardButton("🔃 מיון ברירת מחדל", callback_data="setmenu:sort_by")],
        [InlineKeyboardButton("⚡ קאש בלבד", callback_data="settoggle:cached_only"),
         InlineKeyboardButton("🔔 התראות", callback_data="settoggle:notify")],
        [InlineKeyboardButton("📄 תוצאות בעמוד", callback_data="setmenu:per_page")],
        [InlineKeyboardButton("🏠 תפריט ראשי", callback_data="menu:home")],
    ])


def settings_option_menu(field):
    """תפריט בחירת ערך עבור שדה הגדרה מסוים."""
    rows = []
    if field == "quality":
        for q in config.QUALITY_OPTIONS:
            rows.append([InlineKeyboardButton(config.QUALITY_LABELS[q], callback_data=f"setval:quality:{q}")])
    elif field == "category":
        for c in config.CATEGORY_OPTIONS:
            rows.append([InlineKeyboardButton(config.CATEGORY_LABELS[c], callback_data=f"setval:category:{c}")])
    elif field == "sort_by":
        for s in config.SORT_OPTIONS:
            rows.append([InlineKeyboardButton(config.SORT_LABELS[s], callback_data=f"setval:sort_by:{s}")])
    elif field == "max_size_gb":
        for gb in config.SIZE_OPTIONS_GB:
            label = "ללא הגבלה" if gb == 0 else f"{gb} GB"
            rows.append([InlineKeyboardButton(label, callback_data=f"setval:max_size_gb:{gb}")])
    elif field == "per_page":
        for n in [3, 5, 8, 10]:
            rows.append([InlineKeyboardButton(f"{n} תוצאות", callback_data=f"setval:per_page:{n}")])
    rows.append([InlineKeyboardButton("◀️ חזרה להגדרות", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


# ───────────────────────── סטטוס הורדות ─────────────────────────
def status_keyboard(items):
    """items — רשימת (torbox_id, name, finished)."""
    rows = []
    for tid, name, finished in items:
        short = (name[:25] + "…") if len(name) > 26 else name
        if finished:
            rows.append([InlineKeyboardButton(f"🔗 קישור: {short}", callback_data=f"link:{tid}")])
        else:
            rows.append([InlineKeyboardButton(f"❌ בטל: {short}", callback_data=f"cancel:{tid}")])
    rows.append([
        InlineKeyboardButton("🔄 רענן", callback_data="menu:status"),
        InlineKeyboardButton("🏠 ראשי", callback_data="menu:home"),
    ])
    return InlineKeyboardMarkup(rows)


# ───────────────────────── אדמין ─────────────────────────
def admin_menu(pending_count=0):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 משתמשים", callback_data="admin:users"),
         InlineKeyboardButton(f"⏳ ממתינים ({pending_count})", callback_data="admin:pending")],
        [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="admin:stats"),
         InlineKeyboardButton("📢 שידור הודעה", callback_data="admin:broadcast")],
        [InlineKeyboardButton("🏠 תפריט ראשי", callback_data="menu:home")],
    ])


def user_admin_keyboard(target_id, role):
    rows = []
    if role == config.ROLE_PENDING:
        rows.append([InlineKeyboardButton("✅ אשר", callback_data=f"uadm:approve:{target_id}")])
    if role == config.ROLE_BANNED:
        rows.append([InlineKeyboardButton("♻️ בטל השהיה", callback_data=f"uadm:unban:{target_id}")])
    else:
        rows.append([InlineKeyboardButton("🚫 השהה", callback_data=f"uadm:ban:{target_id}")])
    if role < config.ROLE_ADMIN:
        rows.append([InlineKeyboardButton("👑 קדם למנהל", callback_data=f"uadm:promote:{target_id}")])
    elif role == config.ROLE_ADMIN:
        rows.append([InlineKeyboardButton("⬇️ הורד למשתמש", callback_data=f"uadm:demote:{target_id}")])
    rows.append([InlineKeyboardButton("🗑️ מחק לצמיתות", callback_data=f"uadm:delete:{target_id}")])
    rows.append([InlineKeyboardButton("◀️ חזרה", callback_data="admin:users")])
    return InlineKeyboardMarkup(rows)


def pending_keyboard(pending_users):
    rows = []
    for u in pending_users:
        name = u.get("username") or u.get("first_name") or str(u["user_id"])
        rows.append([
            InlineKeyboardButton(f"✅ {name}", callback_data=f"uadm:approve:{u['user_id']}"),
            InlineKeyboardButton("🚫", callback_data=f"uadm:ban:{u['user_id']}"),
        ])
    rows.append([InlineKeyboardButton("◀️ חזרה לפאנל", callback_data="menu:admin")])
    return InlineKeyboardMarkup(rows)


def users_list_keyboard(users):
    rows = []
    for u in users[:20]:
        name = u.get("username") or u.get("first_name") or str(u["user_id"])
        role_emoji = config.ROLE_NAMES.get(u["role"], "?").split()[0]
        rows.append([InlineKeyboardButton(f"{role_emoji} {name}", callback_data=f"uview:{u['user_id']}")])
    rows.append([InlineKeyboardButton("◀️ חזרה לפאנל", callback_data="menu:admin")])
    return InlineKeyboardMarkup(rows)
