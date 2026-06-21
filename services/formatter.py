"""
services/formatter.py — עיצוב טקסט ההודעות בעברית.
"""
import config
from services import parser


def escape(text: str) -> str:
    """בריחה ל-HTML parse mode."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ───────────────────────── תוצאות ─────────────────────────
def results_page(query, page_items, page, total_pages, total_results, active_filters=None):
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = [f"🔍 תוצאות עבור <b>{escape(query)}</b>:\n"]

    for pos, (_gidx, r) in enumerate(page_items):
        e = emojis[pos] if pos < len(emojis) else f"{pos+1}."
        badges = []
        q = parser.quality_badge(r.get("quality", "unknown"))
        if q:
            badges.append(q)
        if r.get("is_webdl"):
            badges.append("📥 ישיר Debrid")
        elif r.get("cached"):
            badges.append("⚡ בקאש")
        if r.get("owned"):
            badges.append("✓ ברשותך")
        badge_str = "  •  ".join(badges)

        lines.append(f"{e} <b>{escape(r['name'][:70])}</b>")
        if r.get("is_webdl"):
            meta = f"   📦 {parser.human_size(r['size'])}"
        else:
            meta = f"   📦 {parser.human_size(r['size'])}  🌱 {r['seeders']}  🔴 {r['leechers']}"
        if badge_str:
            meta += f"  •  {badge_str}"
        lines.append(meta)
        lines.append("")

    footer = f"━━━━━━━━━━\n📊 {total_results} תוצאות"
    if active_filters:
        footer += f"  •  🔽 מסונן"
    lines.append(footer)
    lines.append("בחר מספר לפרטים והורדה ⬇️")
    return "\n".join(lines)


# ───────────────────────── פרטי פריט ─────────────────────────
def item_detail(r):
    lines = [f"📋 <b>{escape(r['name'])}</b>\n"]
    lines.append(f"📦 גודל:    {parser.human_size(r['size'])}")
    if not r.get("is_webdl"):
        lines.append(f"🌱 זרעים:   {r['seeders']}")
        lines.append(f"🔴 מדיחים:  {r['leechers']}")
    q = config.QUALITY_LABELS.get(r.get("quality", "unknown"))
    if q and r.get("quality", "unknown") != "unknown":
        lines.append(f"🎬 איכות:   {q}")
    cat = config.CATEGORY_LABELS.get(r.get("category", "all"), "")
    if cat and r.get("category", "all") != "all":
        lines.append(f"📂 קטגוריה: {cat}")
    if r.get("age"):
        lines.append(f"📅 תאריך:   {escape(r['age'][:16])}")
    if r.get("tracker"):
        lines.append(f"🔎 מקור:    {escape(r['tracker'])}")
    
    if r.get("is_webdl"):
        status = "📥 הורדה ישירה דרך TorBox (Debrid)"
    else:
        status = "⚡ כבר בקאש — הורדה מיידית!" if r.get("cached") else "📥 יורד לשרת TorBox בעת הוספה"
    lines.append(f"\n{status}")
    return "\n".join(lines)


# ───────────────────────── סטטוס ─────────────────────────
def _progress_bar(pct, width=10):
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


def status_list(items, page=0, total_pages=1, total_items=0, start_index=1):
    if not items:
        return "📭 אין הורדות פעילות.\n\nחפש משהו כדי להתחיל!"
    lines = ["📡 <b>ההורדות שלך:</b>\n"]
    for i, it in enumerate(items, start_index):
        name = escape(it.get("name", "?")[:50])
        progress = it.get("progress", 0) or 0
        pct = round(progress * 100) if progress <= 1 else round(progress)
        finished = it.get("download_finished") or it.get("download_present") or pct >= 100
        size = parser.human_size(it.get("size", 0))

        lines.append(f"<b>{i}. {name}</b>")
        if finished:
            lines.append(f"   ✅ הושלם  •  📦 {size}")
        else:
            speed = it.get("download_speed", 0) or 0
            bar = _progress_bar(pct)
            speed_str = parser.human_size(speed) + "/s" if speed else "—"
            lines.append(f"   {bar}  {pct}%  •  ⬇ {speed_str}")
            eta = it.get("eta", 0) or 0
            if eta:
                lines.append(f"   📦 {size}  •  ⏱ {_human_eta(eta)}")
        lines.append("")

    if total_items > len(items):
        lines.append(f"━━━━━━━━━━\n📄 עמוד {page+1} מתוך {total_pages} (סה\"כ {total_items} הורדות)")

    return "\n".join(lines)


def _human_eta(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} שניות"
    if seconds < 3600:
        return f"{seconds // 60} דקות"
    return f"{seconds // 3600} שעות {(seconds % 3600) // 60} דק'"


# ───────────────────────── הגדרות ─────────────────────────
def settings_view(s):
    q = config.QUALITY_LABELS.get(s.get("quality", "all"), "הכל")
    size = "ללא הגבלה" if not s.get("max_size_gb") else f"{s['max_size_gb']} GB"
    cat = config.CATEGORY_LABELS.get(s.get("category", "all"), "הכל")
    sort = config.SORT_LABELS.get(s.get("sort_by", "seeders"), "זרעים")
    cached = "מופעל ✅" if s.get("cached_only") else "כבוי"
    notify = "מופעל 🔔" if s.get("notify", 1) else "כבוי 🔕"
    return (
        "⚙️ <b>ההגדרות שלך:</b>\n\n"
        f"🎬 איכות מועדפת:  {q}\n"
        f"📦 גודל מקסימלי:  {size}\n"
        f"📂 קטגוריה:       {cat}\n"
        f"🔃 מיון:          {sort}\n"
        f"⚡ קאש בלבד:      {cached}\n"
        f"🔔 התראות:        {notify}\n"
        f"📄 תוצאות בעמוד:  {s.get('per_page', 5)}\n\n"
        "בחר מה לשנות ⬇️"
    )


# ───────────────────────── אדמין ─────────────────────────
def stats_view(stats, counts):
    active = counts.get(config.ROLE_USER, 0) + counts.get(config.ROLE_ADMIN, 0) + counts.get(config.ROLE_OWNER, 0)
    pending = counts.get(config.ROLE_PENDING, 0)
    banned = counts.get(config.ROLE_BANNED, 0)
    return (
        "📊 <b>סטטיסטיקות הבוט:</b>\n\n"
        f"👥 משתמשים פעילים:  {active}\n"
        f"⏳ ממתינים לאישור:  {pending}\n"
        f"🚫 חסומים:          {banned}\n\n"
        f"🔍 חיפושים (24ש'):  {stats['searches_today']}\n"
        f"⬇️ הורדות (24ש'):   {stats['downloads_today']}\n"
        f"📈 סה\"כ הורדות:     {stats['total_downloads']}\n"
        f"💾 נפח כולל:        {parser.human_size(stats['total_volume'])}\n"
    )


def user_detail(u):
    import datetime
    joined = datetime.datetime.fromtimestamp(u.get("joined_at", 0)).strftime("%d/%m/%Y") if u.get("joined_at") else "?"
    name = u.get("username") or u.get("first_name") or "—"
    return (
        f"👤 <b>{escape(name)}</b>\n"
        f"🆔 ID: <code>{u['user_id']}</code>\n"
        f"📅 הצטרף: {joined}\n"
        f"🎖️ תפקיד: {config.ROLE_NAMES.get(u['role'], '?')}\n"
    )
