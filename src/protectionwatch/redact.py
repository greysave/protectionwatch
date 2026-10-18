"""Redaction of secret-looking material from log output.

The rules are applied in a fixed order so that a later rule never sees material an earlier
one already consumed:

1. credentials embedded in URLs (``scheme://user:password@host``),
2. ``Authorization`` / ``Proxy-Authorization`` headers (any scheme, e.g. ``Basic``),
3. ``Cookie`` / ``Set-Cookie`` headers (the whole header line),
4. ``key=value`` / ``key: value`` / JSON ``"key": "value"`` pairs whose key looks sensitive;
   quoted values (including values containing spaces and JSON-escaped quotes) are masked in
   full, unquoted values are masked up to the next whitespace, comma, semicolon or ampersand,
5. stray ``Bearer <token>`` and base64-looking ``Basic <token>`` strings.

Redaction is pattern matching, not a guarantee: an unquoted secret that itself contains
spaces cannot be delimited reliably, so keep secrets out of exception text.
"""

from __future__ import annotations

import logging
import re

REDACTED = "[REDACTED]"

_WORD = r"(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|credential|private[_-]?key)"

_URL_USERINFO = re.compile(r"(?P<scheme>\b[a-z][a-z0-9+.-]*://)[^\s/?#@]+@", re.IGNORECASE)

# A value is: a JSON-escaped quoted string, a double or single quoted string, or a bare run.
_QUOTED = r"\\\"(?:(?!\\\").)*\\\"|\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'"
_AUTH_HEADER = re.compile(
    r"(?P<name>\b(?:proxy-)?authorization\b)(?P<sep>\\?[\"']?\s*[=:]\s*)"
    rf"(?P<val>{_QUOTED}|(?:[A-Za-z][A-Za-z0-9_-]*\s+)?[^\s,;&\"']+)",
    re.IGNORECASE,
)
_COOKIE_HEADER = re.compile(
    r"(?P<name>\b(?:set-)?cookie\b)(?P<sep>\\?[\"']?\s*[=:]\s*)"
    rf"(?P<val>{_QUOTED}|[^\r\n]+)",
    re.IGNORECASE,
)
_KEY_VALUE = re.compile(
    rf"(?P<name>[\w-]*{_WORD}[\w-]*)(?P<sep>\\?[\"']?\s*[=:]\s*)"
    rf"(?P<val>{_QUOTED}|(?:(?:bearer|basic)\s+)?[^\s,;&\"']+)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
# "Basic" is also an English word, so require a base64-ish token with a digit, symbol or capital.
_BASIC = re.compile(r"\b[Bb]asic\s+(?=[A-Za-z0-9+/._~-]*[A-Z0-9+/=])[A-Za-z0-9+/._~=-]{8,}")


def _mask_value(match: re.Match[str]) -> str:
    """Replace the value, keeping its quote style so JSON-ish text stays well formed."""
    val = match["val"]
    if val.startswith('\\"'):
        masked = f'\\"{REDACTED}\\"'
    elif val[:1] in {'"', "'"}:
        masked = f"{val[0]}{REDACTED}{val[0]}"
    else:
        masked = REDACTED
    return f"{match['name']}{match['sep']}{masked}"


def redact(text: str) -> str:
    """Mask credentials, tokens, cookies and URL userinfo inside free text."""
    text = _URL_USERINFO.sub(lambda m: f"{m['scheme']}{REDACTED}@", text)
    text = _AUTH_HEADER.sub(_mask_value, text)
    text = _COOKIE_HEADER.sub(_mask_value, text)
    text = _KEY_VALUE.sub(_mask_value, text)
    text = _BEARER.sub(f"Bearer {REDACTED}", text)
    return _BASIC.sub(f"Basic {REDACTED}", text)


class RedactingFilter(logging.Filter):
    """Logging filter that masks secrets in messages and tracebacks."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Install a stderr handler whose records always pass through redaction."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger("protectionwatch")
    root.handlers = [handler]
    root.setLevel(level)
    root.propagate = False
