"""
ai/analyzer.py
--------------
AI analysis of SEC filings using OpenAI.

Protection layers (in order):
  1. Demo mode           — sample data, no API call
  2. Cache hit           — stored result, no API call
  3. Daily limit         — blocks when today's count hits DAILY_LIMIT
  4. Filing too large    — FilingTooLargeError surfaced as error result
  5. No API key          — error result
  6. Live OpenAI call    — result cached on success, usage incremented
     → If previous_filing_url provided: extended comparison prompt,
       FilingComparison populated on the result
  7. Quota/billing error — auto-fallback to demo result
  8. Any other error     — error result (never raises)
"""

import json
import os
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from .cache import (
    DAILY_LIMIT,
    get_cached,
    get_today_count,
    increment_usage,
    is_limit_reached,
    save_to_cache,
)
from .comparator import FilingComparison, comparison_from_dict
from .fetcher import (
    FetchError,
    FilingTooLargeError,
    PREV_MAX_CHARS,
    fetch_filing_text,
)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    what_changed:     str
    key_catalysts:    list[str]
    key_risks:        list[str]
    thesis_impact:    str               # "Strong" | "Stable" | "Weak" | "Broken"
    suggested_action: str               # "Buy" | "Hold" | "Reduce" | "Exit"
    confidence_score: int               # 0–100 (base AI score, before comparison adj.)
    error:            str | None = None
    is_demo:          bool = False
    is_cached:        bool = False
    comparison:       FilingComparison | None = None  # populated when prev filing available


# ── Demo result ───────────────────────────────────────────────────────────────

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
    comparison=FilingComparison(
        what_improved=[
            "Revenue growth accelerated to 14% from 9% prior year",
            "Operating margins expanded 200 bps to 28%",
            "Management raised full-year guidance by 5%",
        ],
        what_weakened=["International growth slightly below domestic"],
        new_concerns=["FX headwind on ~35% of revenues"],
        new_catalysts=["Enterprise contract wins", "Expanded buyback program"],
        revenue_growth_trend="improving",
        margin_trend="improving",
        cash_trend="stable",
        debt_trend="stable",
        management_tone="positive",
        guidance_trend="raised",
        conviction_adjustment=12,
    ),
)


# ── API key helpers ───────────────────────────────────────────────────────────

def get_api_key(st_secrets=None) -> str:
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


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in (
        "insufficient_quota", "exceeded your current quota",
        "billing", "rate limit", "429",
    ))


# ── System prompts ────────────────────────────────────────────────────────────

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
  Strong = meaningfully improved, Stable = unchanged, Weak = deteriorated, Broken = invalidated
- suggested_action: portfolio recommendation based solely on this filing
- confidence_score: 0 = complete uncertainty, 100 = very high conviction
"""

_COMPARISON_SYSTEM_PROMPT = """\
You are a senior equity research analyst. You are given TWO consecutive filings
of the same type for the same company: the CURRENT filing and the PREVIOUS filing.

Compare them carefully and respond ONLY with a valid JSON object — no markdown, no explanation.

Required JSON structure:
{
  "what_changed": "1-3 sentence summary of the most important new information in the CURRENT filing",
  "key_catalysts": ["catalyst 1", "catalyst 2", "catalyst 3"],
  "key_risks": ["risk 1", "risk 2", "risk 3"],
  "thesis_impact": "Strong | Stable | Weak | Broken",
  "suggested_action": "Buy | Hold | Reduce | Exit",
  "confidence_score": 0-100,
  "comparison": {
    "what_improved": ["specific improvement 1", "specific improvement 2"],
    "what_weakened": ["specific deterioration 1", "specific deterioration 2"],
    "new_concerns": ["new risk not present in previous filing"],
    "new_catalysts": ["new positive catalyst not present in previous filing"],
    "revenue_growth_trend": "improving | stable | declining",
    "margin_trend": "improving | stable | declining",
    "cash_trend": "improving | stable | declining",
    "debt_trend": "improving | stable | declining",
    "management_tone": "positive | neutral | cautious | negative",
    "guidance_trend": "raised | maintained | lowered | withdrawn | not_mentioned"
  }
}

Definitions:
- thesis_impact, suggested_action, confidence_score: based on the CURRENT filing
- debt_trend: improving = debt reduced or balance sheet strengthened
- management_tone: overall tone of the language in the current filing vs previous
- what_improved / what_weakened: specific, concrete observations with numbers where possible
- new_concerns / new_catalysts: items present in CURRENT filing but NOT in PREVIOUS filing
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _error_result(msg: str) -> AnalysisResult:
    return AnalysisResult(
        what_changed="", key_catalysts=[], key_risks=[],
        thesis_impact="Stable", suggested_action="Hold",
        confidence_score=0, error=msg,
    )


def _result_to_dict(r: AnalysisResult) -> dict:
    """Serialise for the cache — drop transient / non-serialisable fields."""
    d = asdict(r)
    for key in ("is_cached", "error", "comparison"):
        d.pop(key, None)
    return d


def _dict_to_cached_result(d: dict) -> AnalysisResult:
    """Re-hydrate a cached dict into an AnalysisResult (no comparison data)."""
    _skip = {"is_cached", "error", "cached_at", "comparison"}
    d = {
        k: v for k, v in d.items()
        if k in AnalysisResult.__dataclass_fields__ and k not in _skip
    }
    return AnalysisResult(**d, is_cached=True, error=None)


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze_filing(
    filing_url:           str,
    form_type:            str,
    company_name:         str,
    st_secrets=None,
    demo_mode:            bool = False,
    cache_key:            str | None = None,
    previous_filing_url:  str | None = None,   # URL of the prior same-type filing
    previous_cache_key:   str | None = None,   # accession of prior filing (optional)
) -> AnalysisResult:
    """
    Analyse a filing and return a structured AnalysisResult.

    When previous_filing_url is supplied, uses an extended prompt that
    compares both filings and populates result.comparison.

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
            "(key name: OPENAI_API_KEY), then restart. "
            "Or enable Demo Mode to test the UI."
        )

    # ── 5. Fetch current filing text ──────────────────────────────────────────
    try:
        filing_text = fetch_filing_text(filing_url)
    except FilingTooLargeError as exc:
        return _error_result(str(exc))
    except FetchError as exc:
        return _error_result(f"Could not fetch filing text: {exc}")

    # ── 5b. Optionally fetch previous filing for comparison ───────────────────
    prev_text: str | None = None
    if previous_filing_url:
        try:
            prev_text = fetch_filing_text(
                previous_filing_url,
                max_chars=PREV_MAX_CHARS,
            )
        except (FetchError, FilingTooLargeError):
            # Comparison not available — fall back to standard single-filing analysis
            prev_text = None

    # ── 6. Call OpenAI ────────────────────────────────────────────────────────
    use_comparison = prev_text is not None
    system_prompt  = _COMPARISON_SYSTEM_PROMPT if use_comparison else _SYSTEM_PROMPT

    if use_comparison:
        user_prompt = (
            f"Company: {company_name}\n"
            f"Filing type: {form_type}\n\n"
            f"--- CURRENT {form_type} EXCERPT ---\n{filing_text}\n\n"
            f"--- PREVIOUS {form_type} EXCERPT ---\n{prev_text}"
        )
    else:
        user_prompt = (
            f"Company: {company_name}\n"
            f"Filing type: {form_type}\n\n"
            f"--- FILING EXCERPT ---\n{filing_text}"
        )

    try:
        from openai import OpenAI

        client   = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=1200,   # slightly more room for the comparison object
        )

        raw_json = response.choices[0].message.content or "{}"
        data     = json.loads(raw_json)

        # Parse optional comparison block
        comparison: FilingComparison | None = None
        if use_comparison and "comparison" in data:
            try:
                comparison = comparison_from_dict(data["comparison"])
            except Exception:
                comparison = None

        result = AnalysisResult(
            what_changed=data.get("what_changed", "No summary returned."),
            key_catalysts=data.get("key_catalysts", []),
            key_risks=data.get("key_risks", []),
            thesis_impact=data.get("thesis_impact", "Stable"),
            suggested_action=data.get("suggested_action", "Hold"),
            confidence_score=int(data.get("confidence_score", 0)),
            comparison=comparison,
        )

        # Cache and count (only successful live results)
        if cache_key:
            save_to_cache(cache_key, _result_to_dict(result))
        increment_usage()

        return result

    except Exception as exc:
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
                comparison=demo.comparison,
                error=(
                    "OpenAI quota exceeded — showing demo analysis. "
                    "Check billing at platform.openai.com."
                ),
            )
        return _error_result(f"OpenAI error: {exc}")
