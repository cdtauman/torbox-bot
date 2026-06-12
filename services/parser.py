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
    magnet = raw.get("magnet") or raw.get("magnet_link") or ""
    if not magnet and thash:
        magnet = f"magnet:?xt=urn:btih:{thash}"

    cached = bool(raw.get("cached") or raw.get("is_cached") or raw.get("nzb"))
    owned = bool(raw.get("owned") or raw.get("is_owned"))

    age = raw.get("age") or raw.get("pubDate") or raw.get("published") or ""
    tracker = raw.get("tracker") or raw.get("indexer") or raw.get("source") or ""

    return {
        "name": name,
        "size": size,
        "seeders": seeders,
        "leechers": leechers,
        "hash": thash,
        "magnet": magnet,
        "cached": cached,
        "owned": owned,
        "age": str(age),
        "tracker": tracker,
        "quality": detect_quality(name),
        "category": detect_category(name),
        "language": detect_language(name),
    }


# ───────────────────────── זיהוי תכונות ─────────────────────────
def detect_quality(name: str) -> str:
    low = name.lower()
    for quality, patterns in config.QUALITY_PATTERNS.items():
        for p in patterns:
            if p in low:
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
    langs = {
        "he": ["hebrew", "heb", "עברית", "hebdub", "il"],
        "en": ["english", "eng"],
        "fr": ["french", "vff", "truefrench"],
        "es": ["spanish", "castellano", "latino"],
        "ru": ["russian", "rus"],
    }
    for code, kws in langs.items():
        for kw in kws:
            if kw in low:
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
        # איכות
        if f.get("quality", "all") != "all" and r["quality"] != f["quality"]:
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
