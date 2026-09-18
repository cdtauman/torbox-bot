"""סיווג קלט חופשי של המשתמש בלי תלות ב-Telegram."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

_HEX_HASH = re.compile(r"^[A-Fa-f0-9]{40}$")
_BASE32_HASH = re.compile(r"^[A-Za-z2-7]{32}$")


@dataclass(frozen=True)
class InputIntent:
    kind: str
    value: str


def _http_url(value: str) -> str:
    """מחזיר URL HTTP(S) תקין או מחרוזת ריקה."""
    if not value or any(ch.isspace() for ch in value):
        return ""

    candidate = value
    if candidate.lower().startswith("www."):
        candidate = "https://" + candidate

    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""

    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return ""
    return candidate


def classify_text(text: str) -> InputIntent:
    """מסווג טקסט ל-search / magnet / torrent_hash / url / nzb_url."""
    value = (text or "").strip()
    if not value:
        return InputIntent("empty", "")

    if value.lower().startswith("magnet:?"):
        return InputIntent("magnet", value)

    if _HEX_HASH.fullmatch(value) or _BASE32_HASH.fullmatch(value):
        return InputIntent("torrent_hash", value.lower())

    url = _http_url(value)
    if url:
        path = urlsplit(url).path.lower()
        if path.endswith(".nzb"):
            return InputIntent("nzb_url", url)
        return InputIntent("url", url)

    return InputIntent("search", value)


def safe_log_summary(text: str) -> str:
    """תיאור קלט ללוג בלי לשמור את תוכן הקלט או היעד."""
    intent = classify_text(text)
    return f"kind={intent.kind} len={len(intent.value)}"
