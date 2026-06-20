"""
services/parser.py — מנוע עיבוד תוצאות
מנרמל תוצאות גולמיות מ-TorBox למבנה אחיד, מזהה איכות/קטגוריה/שפה,
ומיישם סינון ומיון כמו באתרי החיפוש הטובים בעולם.
"""
import re

import config


# ───────────────────────── נרמול ─────────────────────────
def _to_int(v, default=0):
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def normalize(raw: dict) -> dict:
    """ממיר תוצאה גולמית מ-TorBox למבנה אחיד שהבוט מבין."""
    name = raw.get("title") or raw.get("name") or raw.get("raw_title") or "ללא שם"
    size = _to_int(raw.get("size") or raw.get("filesize") or 0)

    seeders = _to_int(raw.get("seeders") or raw.get("seeds") or raw.get("last_known_seeders") or 0)
    leechers = _to_int(raw.get("peers") or raw.get("leechers") or raw.get("last_known_peers") or 0)

    thash = (raw.get("hash") or raw.get("info_hash") or "").lower()
    magnet = raw.get("magnet") or raw.get("magnet_link") or raw.get("magnetUrl") or ""
    torrent_url = raw.get("torrent_url") or raw.get("download_url") or raw.get("downloadUrl") or ""

    if magnet and not magnet.startswith("magnet:"):
        if not torrent_url:
            torrent_url = magnet
        magnet = ""

    generated_magnet = False
    if not thash and magnet:
        m = re.search(r"(?i)urn:btih:([a-z0-9]{32,40})", magnet)
        if m:
            thash = m.group(1).lower()
    if not magnet and thash:
        magnet = f"magnet:?xt=urn:btih:{thash}"
        generated_magnet = True

    cached = bool(raw.get("cached") or raw.get("is_cached") or raw.get("nzb"))
    owned = bool(raw.get("owned") or raw.get("is_owned"))

    age = raw.get("age") or raw.get("pubDate") or raw.get("published") or ""
    tracker = raw.get("tracker") or raw.get("indexer") or raw.get("source") or ""

    return {
        "name": name,
        "source": raw.get("source") or "",
        "size": size,
        "seeders": seeders,
        "leechers": leechers,
        "hash": thash,
        "magnet": magnet,
        "generated_magnet": generated_magnet,
        "torrent_url": raw.get("torrent_url") or raw.get("download_url") or raw.get("downloadUrl") or "",
        "cached": cached,
        "owned": owned,
        "age": str(age),
        "tracker": tracker,
        "quality": detect_quality(name),
        "category": detect_category(name),
        "language": detect_language(name),
        "is_webdl": bool(raw.get("is_webdl")),
    }


# ───────────────────────── זיהוי תכונות ─────────────────────────
# זיהוי איכות לפי טוקנים מדויקים (גבולות-מילה), כדי לא ש-"HD" שב-HDTV/HDR
# יזוהה בטעות כ-720p או "SD" שבתוך מילה אחרת כ-480p.
_QUALITY_TOKENS = [
    ("2160p", r"2160p|\buhd\b|\b4k\b"),
    ("1080p", r"1080[pi]|\bfull\s?hd\b"),
    ("720p", r"720p"),
    ("480p", r"480p|\bdvdrip\b|\bsd\b"),
]


def detect_quality(name: str) -> str:
    low = name.lower()
    for quality, pattern in _QUALITY_TOKENS:
        if re.search(pattern, low):
            return quality
    return "unknown"


def detect_category(name: str) -> str:
    low = name.lower()
    # סדרה לפי תבנית עונה/פרק חזקה
    if re.search(r"s\d{1,2}(e\d{1,3})?", low) or "season" in low:
        return "series"
    for cat, keywords in config.CATEGORY_KEYWORDS.items():
        if cat == "movies":
            continue  # movies הוא ברירת מחדל אחרונה
        for kw in keywords:
            if kw in low:
                return cat
    # אם יש סימני וידאו — סרט
    for kw in config.CATEGORY_KEYWORDS["movies"]:
        if kw in low:
            return "movies"
    return "all"


def detect_language(name: str) -> str:
    low = name.lower()
    # דפוסי גבול-מילה — כדי ש-"il"/"heb"/"eng" לא ייתפסו בתוך מילים אחרות
    # (למשל "film", "while"). עברית קודם.
    langs = [
        ("he", r"hebrew|\bheb\b|עברית|hebdub|\bhebsub\b"),
        ("fr", r"french|\bvff\b|truefrench"),
        ("es", r"spanish|castellano|latino"),
        ("ru", r"russian|\brus\b"),
        ("en", r"english|\beng\b"),
    ]
    for code, pattern in langs:
        if re.search(pattern, low):
            return code
    return "all"


# ───────────────────────── סינון ─────────────────────────
def apply_filters(results, settings, extra=None):
    """
    מסנן רשימת תוצאות לפי הגדרות המשתמש + סינונים זמניים (extra).
    extra יכול לכלול: quality, max_size_gb, cached_only, category, language
    """
    f = dict(settings)
    if extra:
        f.update({k: v for k, v in extra.items() if v is not None})

    out = []
    for r in results:
        # איכות — מסננים רק כשהאיכות *ידועה* ושונה. פריט עם איכות "unknown"
        # לא נזרק, כדי לא לאבד תוצאות תקינות (סינון "מבין כוונה", לא נוקשה).
        if (f.get("quality", "all") != "all"
                and r["quality"] not in ("unknown", f["quality"])):
            continue
        # גודל מקסימלי
        max_gb = f.get("max_size_gb", 0)
        if max_gb and r["size"] > max_gb * (1024 ** 3):
            continue
        # קאש בלבד
        if f.get("cached_only", 0) and not r["cached"]:
            continue
        # קטגוריה
        if f.get("category", "all") != "all" and r["category"] != f["category"]:
            continue
        # שפה
        if f.get("language", "all") != "all" and r["language"] not in (f["language"], "all"):
            continue
        out.append(r)
    return out


# ───────────────────────── מיון ─────────────────────────
def apply_sort(results, sort_by="seeders", desc=True):
    keymap = {
        "seeders": lambda r: r["seeders"],
        "size": lambda r: r["size"],
        "age": lambda r: r["age"],
        "cached": lambda r: (r["cached"], r["seeders"]),
    }
    key = keymap.get(sort_by, keymap["seeders"])
    try:
        return sorted(results, key=key, reverse=desc)
    except TypeError:
        return sorted(results, key=lambda r: r["seeders"], reverse=desc)


# ───────────────────────── עזרי תצוגה ─────────────────────────
def human_size(num_bytes: int) -> str:
    if not num_bytes:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for u in units:
        if size < 1024:
            return f"{size:.1f} {u}".replace(".0 ", " ")
        size /= 1024
    return f"{size:.1f} PB"


def quality_badge(q: str) -> str:
    return config.QUALITY_LABELS.get(q, "") if q != "unknown" else ""
