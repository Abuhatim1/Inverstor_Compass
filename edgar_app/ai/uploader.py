"""
ai/uploader.py
--------------
Manual Filing Upload support.

Lets users upload PDF or plain-text documents (earnings presentations,
analyst reports, Tadawul announcements, etc.) and run them through the
same AI analysis engine used for SEC filings.

Public API
----------
  extract_text(uploaded_file)  -> tuple[str, int]   (text, page_count)
  analyze_uploaded(...)        -> AnalysisResult

Source types
------------
  "sec"                   — SEC Filing uploaded manually (not via EDGAR URL)
  "uploaded_report"       — Earnings presentation, IR deck, etc.
  "tadawul"               — Tadawul (Saudi exchange) announcement
  "analyst_report"        — Sell-side or buy-side analyst report
  "earnings_presentation" — Earnings call slide deck

The extracted text is forwarded to analyze_filing() via the
filing_text_override parameter so every existing protection layer
(demo mode, cache, daily limit, API key check) still applies.
"""

import hashlib
import io
from dataclasses import replace as dc_replace

# ── Source metadata ───────────────────────────────────────────────────────────

SOURCE_LABELS: dict[str, str] = {
    "sec":                   "SEC Filing",
    "uploaded_report":       "Uploaded Report",
    "tadawul":               "Tadawul Announcement",
    "analyst_report":        "Analyst Report",
    "earnings_presentation": "Earnings Presentation",
}

SOURCE_ICON: dict[str, str] = {
    "sec":                   "🏛️",
    "uploaded_report":       "📄",
    "tadawul":               "🇸🇦",
    "analyst_report":        "🔬",
    "earnings_presentation": "📊",
}

# Maximum characters forwarded to the AI (matches the EDGAR fetcher ceiling)
_MAX_CHARS = 8_000


# ── Text extraction ───────────────────────────────────────────────────────────

def extract_text(uploaded_file) -> tuple[str, int]:
    """
    Extract plain text from an uploaded Streamlit UploadedFile.

    Supported formats:
      • .pdf  — extracted page-by-page with pdfplumber
      • .txt  — decoded as UTF-8 (falls back to latin-1)

    Returns
    -------
    (text, page_count)
      page_count is 0 for non-PDF files.
    """
    name = (uploaded_file.name or "").lower()
    raw  = uploaded_file.read()

    if name.endswith(".pdf"):
        return _extract_pdf(raw)

    # Plain text / fallback
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    return text.strip(), 0


def _extract_pdf(raw_bytes: bytes) -> tuple[str, int]:
    """Extract text from PDF bytes with pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber is not installed. Run: pip install pdfplumber"
        )

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text)

    return "\n\n".join(pages).strip(), page_count


# ── Helpers ───────────────────────────────────────────────────────────────────

def truncate_for_ai(text: str) -> tuple[str, bool]:
    """
    Truncate extracted text to _MAX_CHARS at a word boundary.
    Returns (text, was_truncated).
    """
    if len(text) <= _MAX_CHARS:
        return text, False
    cut = text[:_MAX_CHARS].rsplit(" ", 1)[0]
    return cut, True


def upload_cache_key(file_bytes: bytes, doc_type: str) -> str:
    """Stable, content-addressed cache key for an uploaded file."""
    digest = hashlib.sha256(file_bytes).hexdigest()[:16]
    safe   = doc_type.replace(" ", "_").replace("/", "_")
    return f"upload_{safe}_{digest}"


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze_uploaded(
    file_bytes:   bytes,
    file_text:    str,
    source_type:  str,
    doc_type:     str,
    company_name: str,
    ticker:       str,
    st_secrets=None,
    demo_mode:    bool = False,
    cache_key:    str | None = None,
):
    """
    Analyse an uploaded document using the same AI + protection stack
    as SEC EDGAR filings.

    Parameters
    ----------
    file_bytes    : raw bytes of the uploaded file (used for cache key)
    file_text     : plain text already extracted by extract_text()
    source_type   : one of SOURCE_LABELS keys (e.g. "tadawul")
    doc_type      : human-readable document type sent to the AI prompt
                    (e.g. "Earnings Presentation", "10-K", "Announcement")
    company_name  : company the document covers
    ticker        : ticker symbol used for portfolio state updates
    """
    from .analyzer import analyze_filing

    source_label = SOURCE_LABELS.get(source_type, "Uploaded Document")

    if cache_key is None:
        cache_key = upload_cache_key(file_bytes, doc_type)

    text_for_ai, was_truncated = truncate_for_ai(file_text)

    result = analyze_filing(
        filing_url="",
        form_type=doc_type,
        company_name=company_name,
        st_secrets=st_secrets,
        demo_mode=demo_mode,
        cache_key=cache_key,
        filing_text_override=text_for_ai,
        source_label=source_label,
    )

    # Attach a non-blocking truncation notice (doesn't replace real errors)
    if was_truncated and result.error is None and not result.is_demo:
        note = (
            f"Document was long — truncated to {_MAX_CHARS:,} characters. "
            "The first ~8 000 characters were analysed."
        )
        result = dc_replace(result, error=note)

    return result
