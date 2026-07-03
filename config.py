"""
config.py — הגדרות גלובליות לבוט TorBox
כל הערכים נטענים מקובץ .env
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# ───────────────────────── טוקנים ─────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TORBOX_API_KEY = os.getenv("TORBOX_API_KEY", "")

# מזהה המשתמש של הבעלים (סופר-אדמין). מקבל את כל ההרשאות אוטומטית.
# למצוא את ה-ID שלך: שלח הודעה לבוט @userinfobot
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# ───────────────────────── TorBox API ─────────────────────────
TORBOX_BASE_URL = "https://api.torbox.app"
TORBOX_API_VERSION = "v1"

# מנוע החיפוש הרשמי של TorBox (Orion, ~109M לינקים, תוצאות cached).
# חינמי לחשבונות מנוי; מחזיר 429 "0 per minute" לחשבון ניסיון/בלי מנוי.
TORBOX_SEARCH_URL = "https://search-api.torbox.app"

# כמה תוצאות "מספיק" כדי להפסיק להרחיב את השאילתה, וכמה לשמור בסוף.
SEARCH_ENOUGH = 15
SEARCH_LIMIT = 60
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "torbox").strip().lower()
SEARCH_CONCURRENCY = int(os.getenv("SEARCH_CONCURRENCY", "2"))

# Prowlarr — מומלץ להריץ באותו Docker network כמו הבוט:
# PROWLARR_URL=http://prowlarr:9696
PROWLARR_URL = os.getenv("PROWLARR_URL", "").rstrip("/")
PROWLARR_API_KEY = os.getenv("PROWLARR_API_KEY", "")
PROWLARR_TIMEOUT = int(os.getenv("PROWLARR_TIMEOUT", "25"))
PROWLARR_LIMIT = int(os.getenv("PROWLARR_LIMIT", str(SEARCH_LIMIT)))

# ───────────────────────── בסיס נתונים ─────────────────────────
DB_PATH = os.getenv("DB_PATH", "torbox_bot.db")

# ───────────────────────── קישורי הורדה קבועים ─────────────────────────
# PUBLIC_BASE_URL should point to this bot's public HTTP endpoint, for example:
# https://downloads.example.com
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
PUBLIC_LINKS_ENABLED = _env_bool("PUBLIC_LINKS_ENABLED", bool(PUBLIC_BASE_URL)) and bool(PUBLIC_BASE_URL)
PUBLIC_LINK_HOST = os.getenv("PUBLIC_LINK_HOST", "0.0.0.0")
PUBLIC_LINK_PORT = int(os.getenv("PUBLIC_LINK_PORT", "8080"))
PUBLIC_LINK_PATH_PREFIX = os.getenv("PUBLIC_LINK_PATH_PREFIX", "d").strip("/")
PUBLIC_LINK_RATE_LIMIT_PER_MINUTE = int(os.getenv("PUBLIC_LINK_RATE_LIMIT_PER_MINUTE", "30"))

# When permanent public links are enabled, completed downloads must stay in
# TorBox/AirLock. Set AUTO_DELETE_COMPLETED_AFTER_MINUTES to a positive value if
# you prefer automatic cleanup over long-lived links.
AUTO_DELETE_COMPLETED_AFTER_MINUTES = int(
    os.getenv("AUTO_DELETE_COMPLETED_AFTER_MINUTES", "0" if PUBLIC_LINKS_ENABLED else "120")
)
QUEUE_ROTATE_ACTIVE_AFTER_MINUTES = int(os.getenv("QUEUE_ROTATE_ACTIVE_AFTER_MINUTES", "30"))

# ───────────────────────── רמות הרשאה ─────────────────────────
ROLE_BANNED = 0   # חסום — אין גישה
ROLE_PENDING = 1  # ממתין לאישור
ROLE_USER = 2     # משתמש מאושר — חיפוש + הורדה
ROLE_ADMIN = 3    # מנהל — הכל + ניהול משתמשים
ROLE_OWNER = 4    # בעלים — הכל

ROLE_NAMES = {
    ROLE_BANNED: "🚫 חסום",
    ROLE_PENDING: "⏳ ממתין",
    ROLE_USER: "👤 משתמש",
    ROLE_ADMIN: "👑 מנהל",
    ROLE_OWNER: "⭐ בעלים",
}

# ───────────────────────── הגדרות ברירת מחדל למשתמש ─────────────────────────
DEFAULT_SETTINGS = {
    "quality": "all",      # all / 480p / 720p / 1080p / 2160p
    "max_size_gb": 0,      # 0 = ללא הגבלה
    "cached_only": 0,      # 0 = כבוי, 1 = רק תוצאות בקאש
    "sort_by": "seeders",  # seeders / size / age / cached
    "sort_desc": 1,        # 1 = יורד, 0 = עולה
    "category": "all",     # all / movies / series / games / software / anime / music / books
    "per_page": 5,         # תוצאות בעמוד
    "notify": 1,           # התראות על השלמת הורדה
    "lang": "all",         # סינון שפה
}

# ───────────────────────── אפשרויות תפריט ─────────────────────────
QUALITY_OPTIONS = ["all", "480p", "720p", "1080p", "2160p"]
QUALITY_LABELS = {
    "all": "הכל", "480p": "480p", "720p": "720p",
    "1080p": "1080p", "2160p": "4K",
}

SIZE_OPTIONS_GB = [0, 1, 2, 5, 10, 30, 50]  # 0 = ללא הגבלה

SORT_OPTIONS = ["seeders", "size", "age", "cached"]
SORT_LABELS = {
    "seeders": "🌱 זרעים", "size": "📦 גודל",
    "age": "📅 תאריך", "cached": "⚡ קאש קודם",
}

CATEGORY_OPTIONS = ["all", "movies", "series", "games", "software", "anime", "music", "books"]
CATEGORY_LABELS = {
    "all": "🌐 הכל", "movies": "🎬 סרטים", "series": "📺 סדרות",
    "games": "🎮 משחקים", "software": "💿 תוכנות", "anime": "🎌 אנימה",
    "music": "🎵 מוזיקה", "books": "📚 ספרים",
}

# מילות מפתח לזיהוי קטגוריה אוטומטי מתוך שם הטורנט
CATEGORY_KEYWORDS = {
    "series": ["s01", "s02", "s03", "season", "episode", "e01", "complete series", "hdtv"],
    "anime": ["anime", "[subsplease]", "[erai", "nyaa", "1080p].mkv", "ova", "[horriblesubs]"],
    "games": ["game", "repack", "fitgirl", "codex", "skidrow", "razor1911", "-tenoke", "plaza"],
    "software": ["software", "windows", "macos", "x64", "crack", "activator", "portable", "v1.", "v2."],
    "music": ["mp3", "flac", "320kbps", "album", "discography", "ost", "soundtrack"],
    "books": ["epub", "pdf", "mobi", "azw3", "ebook", "audiobook", "m4b"],
    "movies": ["1080p", "720p", "2160p", "bluray", "webrip", "web-dl", "x265", "x264", "hdr"],
}

# רזולוציות לזיהוי איכות מתוך השם
QUALITY_PATTERNS = {
    "2160p": ["2160p", "4k", "uhd"],
    "1080p": ["1080p", "1080i", "fullhd"],
    "720p": ["720p", "hd"],
    "480p": ["480p", "sd", "dvdrip"],
}
