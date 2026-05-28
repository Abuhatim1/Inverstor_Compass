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
     · Evidence Grounding Layer always requested in both prompts
     · If previous_filing_url provided: comparison block also requested
  7. Quota/billing error — auto-fallback to demo result
  8. Any other error     — error result (never raises)
"""

import json
import os
from dataclasses import asdict, dataclass, field

from .cache import (
    DAILY_LIMIT,
    get_cached,
    increment_usage,
    is_limit_reached,
    save_to_cache,
)
from .comparator import FilingComparison, comparison_from_dict
from .evidence import EvidenceItem, evidence_from_list
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
    thesis_impact:    str                    # "Strong" | "Stable" | "Weak" | "Broken"
    suggested_action: str                    # "Buy" | "Hold" | "Reduce" | "Exit"
    confidence_score: int                    # 0–100 (base, before comparison adj.)
    error:            str | None = None
    is_demo:          bool = False
    is_cached:        bool = False
    comparison:       FilingComparison | None = None
    evidence:         list[EvidenceItem] = field(default_factory=list)
    source_label:     str = "SEC"            # e.g. "SEC Filing", "Tadawul Announcement"


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
        what_weakened=["International growth slightly below domestic pace"],
        new_concerns=["FX headwind on ~35% of international revenues"],
        new_catalysts=["New enterprise contract wins", "Expanded $500M buyback"],
        revenue_growth_trend="improving",
        margin_trend="improving",
        cash_trend="stable",
        debt_trend="stable",
        management_tone="positive",
        guidance_trend="raised",
        conviction_adjustment=12,
    ),
    evidence=[
        EvidenceItem(
            field="revenue_growth",
            section="Results of Operations",
            current_value="$4.7B, +14% YoY",
            previous_value="$4.1B",
            delta="+$600M / +14.6%",
            quote="Net revenues increased 14% year-over-year to $4.7 billion, "
                  "driven by strong software segment performance.",
            interpretation="Growth is accelerating vs. the prior 9% pace — a bullish signal.",
            confidence="high",
        ),
        EvidenceItem(
            field="margins",
            section="Results of Operations",
            current_value="28% operating margin",
            previous_value="26%",
            delta="+200 bps",
            quote="Operating income margin expanded to 28.0% from 26.0% in the "
                  "prior-year period.",
            interpretation="Margin expansion alongside revenue growth is a strong positive.",
            confidence="high",
        ),
        EvidenceItem(
            field="cash_position",
            section="Balance Sheet",
            current_value="$1.2B cash & equivalents",
            previous_value="$1.1B",
            delta="+$100M",
            quote="Cash and cash equivalents were $1.2 billion as of quarter end.",
            interpretation="Cash position is stable with modest improvement.",
            confidence="medium",
        ),
        EvidenceItem(
            field="debt",
            section="Balance Sheet",
            current_value="$800M long-term debt",
            previous_value="$850M",
            delta="-$50M",
            quote="Long-term debt decreased to $800 million following scheduled repayments.",
            interpretation="Modest debt reduction; leverage remains manageable.",
            confidence="high",
        ),
        EvidenceItem(
            field="guidance",
            section="Outlook",
            current_value="Full-year revenue raised to $18.5B–$18.8B",
            previous_value="$17.5B–$17.8B",
            delta="+~$1B at midpoint",
            quote="We are raising our full-year 2026 revenue outlook to $18.5 to "
                  "$18.8 billion, reflecting strong demand visibility.",
            interpretation="Guidance raise is material and signals management confidence.",
            confidence="high",
        ),
        EvidenceItem(
            field="management_tone",
            section="CEO Commentary",
            current_value="Positive — confident, forward-looking language",
            previous_value="Neutral",
            delta="Tone improved",
            quote="We are very pleased with our execution and remain highly confident "
                  "in our ability to deliver long-term value for shareholders.",
            interpretation="Tone shift from neutral to positive aligns with raised guidance.",
            confidence="medium",
        ),
    ],
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


# ── Evidence schema (shared by both prompts) ──────────────────────────────────

_EVIDENCE_SCHEMA = """\
  "evidence": [
    {
      "field": "revenue_growth | margins | cash_position | debt | guidance | management_tone",
      "section": "exact section name (e.g. 'Results of Operations') or 'not_mentioned'",
      "current_value": "metric with unit and period, e.g. '$4.7B, +14% YoY' or 'not mentioned'",
      "previous_value": "comparable prior-period metric, or '' if no comparison filing",
      "delta": "change vs prior period with sign, or '' if no comparison filing",
      "quote": "verbatim sentence from the filing (max 150 chars), or '' if not found",
      "interpretation": "one sentence: what this means for the investment thesis",
      "confidence": "high (explicit number/quote found) | medium (inferred) | low (not mentioned)"
    }
  ]

EVIDENCE RULES — you MUST follow these:
- Include exactly one entry per field (all six fields must be present).
- Set confidence='low' and current_value='not mentioned' when no data exists in the excerpt.
- NEVER invent numbers. Only use values that appear verbatim or can be directly calculated
  from the excerpt. If uncertain, lower the confidence level.
- A 'low' confidence entry is NOT a failure — it tells the reader the filing does not
  address this topic.
"""


# ── System prompts ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a senior equity research analyst. Analyze the provided SEC filing excerpt\n"
    "and respond ONLY with a valid JSON object — no markdown, no explanation.\n\n"
    "Required JSON structure:\n"
    "{\n"
    '  "what_changed": "1-3 sentence summary of the most important new information",\n'
    '  "key_catalysts": ["catalyst 1", "catalyst 2", "catalyst 3"],\n'
    '  "key_risks": ["risk 1", "risk 2", "risk 3"],\n'
    '  "thesis_impact": "Strong | Stable | Weak | Broken",\n'
    '  "suggested_action": "Buy | Hold | Reduce | Exit",\n'
    '  "confidence_score": 0-100,\n'
    + _EVIDENCE_SCHEMA +
    "}\n\n"
    "Definitions:\n"
    "- thesis_impact: effect on a long investment thesis\n"
    "  Strong=improved, Stable=unchanged, Weak=deteriorated, Broken=invalidated\n"
    "- suggested_action: recommendation based solely on this filing\n"
    "- confidence_score: 0=complete uncertainty, 100=very high conviction\n"
)

_COMPARISON_SYSTEM_PROMPT = (
    "You are a senior equity research analyst. You are given TWO consecutive filings\n"
    "of the same type for the same company: the CURRENT filing and the PREVIOUS filing.\n\n"
    "Compare them carefully and respond ONLY with a valid JSON object — no markdown, no explanation.\n\n"
    "Required JSON structure:\n"
    "{\n"
    '  "what_changed": "1-3 sentence summary of the most important new information in the CURRENT filing",\n'
    '  "key_catalysts": ["catalyst 1", "catalyst 2", "catalyst 3"],\n'
    '  "key_risks": ["risk 1", "risk 2", "risk 3"],\n'
    '  "thesis_impact": "Strong | Stable | Weak | Broken",\n'
    '  "suggested_action": "Buy | Hold | Reduce | Exit",\n'
    '  "confidence_score": 0-100,\n'
    '  "comparison": {\n'
    '    "what_improved": ["specific improvement 1", "specific improvement 2"],\n'
    '    "what_weakened": ["specific deterioration 1", "specific deterioration 2"],\n'
    '    "new_concerns": ["new risk not present in previous filing"],\n'
    '    "new_catalysts": ["new positive catalyst not present in previous filing"],\n'
    '    "revenue_growth_trend": "improving | stable | declining",\n'
    '    "margin_trend": "improving | stable | declining",\n'
    '    "cash_trend": "improving | stable | declining",\n'
    '    "debt_trend": "improving | stable | declining",\n'
    '    "management_tone": "positive | neutral | cautious | negative",\n'
    '    "guidance_trend": "raised | maintained | lowered | withdrawn | not_mentioned"\n'
    "  },\n"
    + _EVIDENCE_SCHEMA +
    "}\n\n"
    "Definitions:\n"
    "- thesis_impact, suggested_action, confidence_score: based on the CURRENT filing\n"
    "- debt_trend: improving = debt reduced or balance sheet strengthened\n"
    "- management_tone: tone of CURRENT filing language vs PREVIOUS filing\n"
    "- what_improved / what_weakened: specific, concrete, with numbers where possible\n"
    "- For evidence: previous_value and delta MUST use PREVIOUS filing data for comparison\n"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _error_result(msg: str) -> AnalysisResult:
    return AnalysisResult(
        what_changed="", key_catalysts=[], key_risks=[],
        thesis_impact="Stable", suggested_action="Hold",
        confidence_score=0, error=msg,
    )


def _result_to_dict(r: AnalysisResult) -> dict:
    """Serialise for the cache — drop transient flags, keep evidence."""
    d = asdict(r)
    for key in ("is_cached", "error", "comparison"):
        d.pop(key, None)
    return d


def _dict_to_cached_result(d: dict) -> AnalysisResult:
    """Re-hydrate a cached dict. Evidence items are reconstructed; no comparison data."""
    _skip = {"is_cached", "error", "cached_at", "comparison", "evidence"}
    # Reconstruct evidence list
    evidence = evidence_from_list(d.get("evidence") or [])
    # Filter remaining fields
    filtered = {
        k: v for k, v in d.items()
        if k in AnalysisResult.__dataclass_fields__ and k not in _skip
    }
    return AnalysisResult(**filtered, is_cached=True, error=None, evidence=evidence)


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze_filing(
    filing_url:            str,
    form_type:             str,
    company_name:          str,
    st_secrets=None,
    demo_mode:             bool = False,
    cache_key:             str | None = None,
    previous_filing_url:   str | None = None,
    previous_cache_key:    str | None = None,
    filing_text_override:  str | None = None,  # pre-extracted text (skips URL fetch)
    source_label:          str = "SEC",         # shown in UI as source badge
) -> AnalysisResult:
    """
    Analyse a filing and return a structured AnalysisResult.

    When filing_text_override is supplied (e.g. for uploaded documents),
    the URL fetch step is skipped and the provided text is used directly.

    Evidence Grounding is always requested — every trend claim is backed
    by a quote, metric, section reference, and confidence level.

    Never raises — all failures captured in result.error.
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

    # ── 5. Obtain filing text ─────────────────────────────────────────────────
    if filing_text_override is not None:
        # Uploaded document — text already extracted by the caller
        filing_text = filing_text_override
    else:
        try:
            filing_text = fetch_filing_text(filing_url)
        except FilingTooLargeError as exc:
            return _error_result(str(exc))
        except FetchError as exc:
            return _error_result(f"Could not fetch filing text: {exc}")

    # ── 5b. Optionally fetch previous filing (EDGAR mode only) ────────────────
    prev_text: str | None = None
    if previous_filing_url and filing_text_override is None:
        try:
            prev_text = fetch_filing_text(previous_filing_url, max_chars=PREV_MAX_CHARS)
        except (FetchError, FilingTooLargeError):
            prev_text = None  # fall back to single-filing analysis

    # ── 6. Build prompt ───────────────────────────────────────────────────────
    use_comparison = prev_text is not None
    system_prompt  = _COMPARISON_SYSTEM_PROMPT if use_comparison else _SYSTEM_PROMPT

    if use_comparison:
        user_prompt = (
            f"Company: {company_name}\nFiling type: {form_type}\n\n"
            f"--- CURRENT {form_type} EXCERPT ---\n{filing_text}\n\n"
            f"--- PREVIOUS {form_type} EXCERPT ---\n{prev_text}"
        )
    else:
        user_prompt = (
            f"Company: {company_name}\nFiling type: {form_type}\n\n"
            f"--- FILING EXCERPT ---\n{filing_text}"
        )

    # ── 7. Call OpenAI ────────────────────────────────────────────────────────
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
            max_tokens=1800,   # room for evidence + comparison + core fields
        )

        raw_json = response.choices[0].message.content or "{}"
        data     = json.loads(raw_json)

        # Parse comparison block (comparison mode only)
        comparison: FilingComparison | None = None
        if use_comparison and "comparison" in data:
            try:
                comparison = comparison_from_dict(data["comparison"])
            except Exception:
                comparison = None

        # Parse evidence block (always requested)
        evidence = evidence_from_list(data.get("evidence") or [])

        result = AnalysisResult(
            what_changed=data.get("what_changed", "No summary returned."),
            key_catalysts=data.get("key_catalysts", []),
            key_risks=data.get("key_risks", []),
            thesis_impact=data.get("thesis_impact", "Stable"),
            suggested_action=data.get("suggested_action", "Hold"),
            confidence_score=int(data.get("confidence_score", 0)),
            comparison=comparison,
            evidence=evidence,
        )

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
                evidence=demo.evidence,
                error="OpenAI quota exceeded — showing demo analysis. "
                      "Check billing at platform.openai.com.",
            )
        return _error_result(f"OpenAI error: {exc}")
