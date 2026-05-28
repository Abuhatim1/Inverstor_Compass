"""
ai/fetcher.py
-------------
Fetches and cleans the text content of a SEC filing from its URL.
Used by analyzer.py before sending to OpenAI.
"""

import gzip
import re
import urllib.error
import urllib.request

# Max characters sent to OpenAI — keeps costs low and avoids token limits.
# ~15 000 chars ≈ ~4 000 tokens, well within gpt-4o-mini context.
MAX_CHARS = 15_000

HEADERS = {
    "User-Agent": "edgar-app contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}


class FetchError(Exception):
    """Raised when the filing text cannot be retrieved."""


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace to plain text."""
    # Drop <script> and <style> blocks entirely
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.S | re.I)
    # Remove all remaining tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def fetch_filing_text(url: str) -> str:
    """
    Download a filing from SEC.gov and return cleaned plain text,
    truncated to MAX_CHARS.

    Raises FetchError on network or HTTP problems.
    """
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} fetching filing: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"Network error fetching filing: {exc.reason}") from exc

    try:
        raw = gzip.decompress(raw)
    except (gzip.BadGzipFile, OSError):
        pass

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    text = _strip_html(text)

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[... filing truncated for analysis ...]"

    return text
