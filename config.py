"""
config.py — הגדרות גלובליות לבוט TorBox
כל הערכים נטענים מקובץ .env
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ───────────────────────── טוקנים ─────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TORBOX_API_KEY = os.getenv("TORBOX_API_KEY", "")

# מזהה המשתמש של הבעלים (סופר-אדמין). מקבל את כל ההרשאות אוטומטית.
# למצוא את ה-ID שלך: שלח הודעה לבוט @userinfobot
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# ───────────────────────── TorBox API ─────────────────────────
TORBOX_BASE_URL = "https://api.torbox.app"
TORBOX_API_VERSION = "v1"

# ───────────────────────── בסיס נתונים ─────────────────────────
DB_PATH = os.getenv("DB_PATH", "torbox_bot.db")

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
