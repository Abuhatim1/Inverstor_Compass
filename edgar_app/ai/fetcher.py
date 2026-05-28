"""
ai/fetcher.py
-------------
Fetches and cleans the text content of a SEC filing from its URL.
Used by analyzer.py before sending to OpenAI.

Size protections
----------------
MAX_RAW_BYTES  — hard cap on the raw download (before decompression).
MAX_CHARS      — how many plain-text chars are forwarded to OpenAI for the
                 primary (current) filing.
PREV_MAX_CHARS — smaller cap used for the previous filing text in comparison
                 mode, to keep the combined prompt within a reasonable token budget.
"""

import gzip
import re
import urllib.error
import urllib.request

MAX_RAW_BYTES  = 10_000_000   # 10 MB — reject before wasting bandwidth
MAX_CHARS      = 15_000       # ~4 000 tokens — current filing sent to OpenAI
PREV_MAX_CHARS =  7_500       # ~2 000 tokens — previous filing for comparison

HEADERS = {
    "User-Agent": "edgar-app contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}


class FetchError(Exception):
    """Raised when the filing text cannot be retrieved."""


class FilingTooLargeError(FetchError):
    """Raised when the filing exceeds the raw byte limit."""


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace to plain text."""
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def fetch_filing_text(url: str, max_chars: int = MAX_CHARS) -> str:
    """
    Download a filing from SEC.gov and return cleaned plain text,
    truncated to `max_chars`.

    Pass max_chars=PREV_MAX_CHARS when fetching a previous filing for
    comparison to reduce token usage.

    Raises FilingTooLargeError if the raw download exceeds MAX_RAW_BYTES.
    Raises FetchError on network or HTTP problems.
    """
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            # ── Size gate: check Content-Length header first ──────────────────
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_RAW_BYTES:
                size_mb = int(content_length) / 1_000_000
                raise FilingTooLargeError(
                    f"Filing is {size_mb:.1f} MB — exceeds the "
                    f"{MAX_RAW_BYTES // 1_000_000} MB limit. "
                    "Try a different filing."
                )
            raw = resp.read()
    except FilingTooLargeError:
        raise
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} fetching filing: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"Network error fetching filing: {exc.reason}") from exc

    # ── Size gate: check actual bytes received ────────────────────────────────
    if len(raw) > MAX_RAW_BYTES:
        size_mb = len(raw) / 1_000_000
        raise FilingTooLargeError(
            f"Filing is {size_mb:.1f} MB — exceeds the "
            f"{MAX_RAW_BYTES // 1_000_000} MB limit. "
            "Try a different filing."
        )

    # ── Decompress if needed ──────────────────────────────────────────────────
    try:
        raw = gzip.decompress(raw)
    except (gzip.BadGzipFile, OSError):
        pass

    # ── Decode ────────────────────────────────────────────────────────────────
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    text = _strip_html(text)

    # ── Truncate for OpenAI ───────────────────────────────────────────────────
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... filing truncated for analysis ...]"

    return text
