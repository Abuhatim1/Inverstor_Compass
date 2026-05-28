"""
ai/analyzer.py
--------------
AI analysis of SEC filings using OpenAI.

Protection layers (in order):
  1. Demo mode          — returns sample data instantly, no API call
  2. Cache hit          — returns stored result, no API call
  3. Daily limit        — blocks when today's live calls hit DAILY_LIMIT
  4. Filing too large   — FilingTooLargeError from fetcher, returned as error
  5. No API key         — returns error result
  6. Live OpenAI call   — result cached on success, usage incremented
  7. Quota/billing err  — auto-fallback to demo result
  8. Any other error    — error result (never raises)
"""

import json
import os
from dataclasses import asdict, dataclass

from .cache import (
    DAILY_LIMIT,
    get_cached,
    get_today_count,
    increment_usage,
    is_limit_reached,
    save_to_cache,
)
from .fetcher import FetchError, FilingTooLargeError, fetch_filing_text


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    what_changed:     str
    key_catalysts:    list[str]
    key_risks:        list[str]
    thesis_impact:    str       # "Strong" | "Stable" | "Weak" | "Broken"
    suggested_action: str       # "Buy" | "Hold" | "Reduce" | "Exit"
    confidence_score: int       # 0–100
    error:            str | None = None   # set only on failure
    is_demo:          bool = False        # True for sample / quota-fallback data
    is_cached:        bool = False        # True when result came from cache


# ── Sample demo result ────────────────────────────────────────────────────────

_DEMO_RESULT = AnalysisResult(
    what_changed=(
        "Revenue grew 14% year-over-year, driven by strong performance in the "
        "core product segment and international expansion. Operating margins "
        "improved by 200 bps, and the company raised full-year guidance."
    ),
    key_catalysts=[
        "Accelerating revenue growth in high-margin software segment",
        "New multi-year enterprise contract wins announced in the quarter",
        "Share buyback program expanded by $500M",
    ],
    key_risks=[
        "Macroeconomic headwinds could pressure discretionary spending",
        "Increasing competition from well-funded new entrants",
        "Foreign exchange exposure on ~35% of international revenues",
    ],
    thesis_impact="Strong",
    suggested_action="Buy",
    confidence_score=72,
    is_demo=True,
)


# ── API key helpers ───────────────────────────────────────────────────────────

def get_api_key(st_secrets=None) -> str:
    """
    Return the OpenAI API key, checking os.environ then st.secrets.
    Always evaluated fresh — never cached at module level.
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    if st_secrets is not None:
        try:
            key = (st_secrets.get("OPENAI_API_KEY") or "").strip()
        except Exception:
            pass
    return key


OPENAI_AVAILABLE: bool = bool(os.environ.get("OPENAI_API_KEY", "").strip())


# ── Quota / billing error detection ──────────────────────────────────────────

def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in (
        "insufficient_quota", "exceeded your current quota",
        "billing", "rate limit", "429",
    ))


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior equity research analyst. Analyze the provided SEC filing excerpt
and respond ONLY with a valid JSON object — no markdown, no explanation.

Required JSON structure:
{
  "what_changed": "1-3 sentence summary of the most important new information",
  "key_catalysts": ["catalyst 1", "catalyst 2", "catalyst 3"],
  "key_risks": ["risk 1", "risk 2", "risk 3"],
  "thesis_impact": "Strong | Stable | Weak | Broken",
  "suggested_action": "Buy | Hold | Reduce | Exit",
  "confidence_score": 0-100
}

Definitions:
- thesis_impact: effect on a long investment thesis
  Strong = meaningfully improved, Stable = unchanged, Weak = deteriorated, Broken = thesis invalidated
- suggested_action: portfolio recommendation based solely on this filing
- confidence_score: 0 = complete uncertainty, 100 = very high conviction
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _error_result(msg: str) -> AnalysisResult:
    return AnalysisResult(
        what_changed="", key_catalysts=[], key_risks=[],
        thesis_impact="Stable", suggested_action="Hold",
        confidence_score=0, error=msg,
    )


def _result_to_dict(r: AnalysisResult) -> dict:
    """Serialise an AnalysisResult to a plain dict for the cache."""
    d = asdict(r)
    # Don't persist transient flags into the cache
    d.pop("is_cached", None)
    d.pop("error", None)
    return d


def _dict_to_cached_result(d: dict) -> AnalysisResult:
    """Re-hydrate a cached dict into an AnalysisResult."""
    # Exclude transient / meta fields that we set explicitly below
    _skip = {"is_cached", "error", "cached_at"}
    d = {
        k: v for k, v in d.items()
        if k in AnalysisResult.__dataclass_fields__ and k not in _skip
    }
    return AnalysisResult(**d, is_cached=True, error=None)


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze_filing(
    filing_url:  str,
    form_type:   str,
    company_name: str,
    st_secrets=None,
    demo_mode:   bool = False,
    cache_key:   str | None = None,   # typically the filing accession number
) -> AnalysisResult:
    """
    Analyse a filing and return a structured AnalysisResult.

    Never raises — all failures are captured in result.error.
    """

    # ── 1. Demo mode ──────────────────────────────────────────────────────────
    if demo_mode:
        return _DEMO_RESULT

    # ── 2. Cache hit ──────────────────────────────────────────────────────────
    if cache_key:
        cached = get_cached(cache_key)
        if cached:
            return _dict_to_cached_result(cached)

    # ── 3. Daily limit ────────────────────────────────────────────────────────
    if is_limit_reached():
        return _error_result(
            f"Daily analysis limit reached ({DAILY_LIMIT} live calls). "
            "Limit resets at midnight. Enable Demo Mode to continue exploring."
        )

    # ── 4. API key ────────────────────────────────────────────────────────────
    api_key = get_api_key(st_secrets)
    if not api_key:
        return _error_result(
            "OPENAI_API_KEY not found. Add it in Replit Secrets "
            "(key name must be exactly OPENAI_API_KEY), then restart the app. "
            "Or enable Demo Mode to test the UI."
        )

    # ── 5. Fetch filing text ──────────────────────────────────────────────────
    try:
        filing_text = fetch_filing_text(filing_url)
    except FilingTooLargeError as exc:
        return _error_result(str(exc))
    except FetchError as exc:
        return _error_result(f"Could not fetch filing text: {exc}")

    # ── 6. Call OpenAI ────────────────────────────────────────────────────────
    try:
        from openai import OpenAI

        client      = OpenAI(api_key=api_key)
        user_prompt = (
            f"Company: {company_name}\n"
            f"Filing type: {form_type}\n\n"
            f"--- FILING EXCERPT ---\n{filing_text}"
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=800,
        )

        raw_json = response.choices[0].message.content or "{}"
        data     = json.loads(raw_json)

        result = AnalysisResult(
            what_changed=data.get("what_changed", "No summary returned."),
            key_catalysts=data.get("key_catalysts", []),
            key_risks=data.get("key_risks", []),
            thesis_impact=data.get("thesis_impact", "Stable"),
            suggested_action=data.get("suggested_action", "Hold"),
            confidence_score=int(data.get("confidence_score", 0)),
        )

        # ── Save to cache and increment daily counter ─────────────────────────
        if cache_key:
            save_to_cache(cache_key, _result_to_dict(result))
        increment_usage()

        return result

    except Exception as exc:
        # ── 6a. Quota error → demo fallback ───────────────────────────────────
        if _is_quota_error(exc):
            demo = _DEMO_RESULT
            return AnalysisResult(
                what_changed=demo.what_changed,
                key_catalysts=demo.key_catalysts,
                key_risks=demo.key_risks,
                thesis_impact=demo.thesis_impact,
                suggested_action=demo.suggested_action,
                confidence_score=demo.confidence_score,
                is_demo=True,
                error=(
                    "OpenAI quota exceeded — showing demo analysis. "
                    "Check your billing at platform.openai.com."
                ),
            )

        # ── 6b. Any other error ───────────────────────────────────────────────
        return _error_result(f"OpenAI error: {exc}")
