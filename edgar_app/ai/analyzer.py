"""
ai/analyzer.py
--------------
AI analysis of SEC filings using OpenAI.

Two modes:
  - Live mode:  calls OpenAI with the real filing text
  - Demo mode:  returns a realistic sample result instantly (no API key needed)

If OpenAI returns an insufficient_quota / billing error, the function
automatically falls back to demo mode instead of crashing.
"""

import json
import os
from dataclasses import dataclass

from .fetcher import FetchError, fetch_filing_text


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    what_changed: str
    key_catalysts: list[str]
    key_risks: list[str]
    thesis_impact: str        # "Strong" | "Stable" | "Weak" | "Broken"
    suggested_action: str     # "Buy" | "Hold" | "Reduce" | "Exit"
    confidence_score: int     # 0–100
    error: str | None = None  # set only when analysis fully failed
    is_demo: bool = False     # True when result came from demo data


# ── Sample demo result (realistic, filing-agnostic) ──────────────────────────

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
    Return the OpenAI API key, checking two sources in order:
      1. os.environ  (Replit Secrets → env vars)
      2. st.secrets  (Streamlit secrets.toml, if provided)

    Always evaluated fresh — never cached at module level.
    Does NOT log or expose the key value.
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


# Legacy module-level flag — use get_api_key() for reliable runtime checks.
OPENAI_AVAILABLE: bool = bool(os.environ.get("OPENAI_API_KEY", "").strip())


# ── Quota / billing error detection ──────────────────────────────────────────

def _is_quota_error(exc: Exception) -> bool:
    """Return True if the exception is an OpenAI quota / billing error."""
    msg = str(exc).lower()
    quota_keywords = (
        "insufficient_quota",
        "exceeded your current quota",
        "billing",
        "rate limit",
        "429",
    )
    return any(k in msg for k in quota_keywords)


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


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze_filing(
    filing_url: str,
    form_type: str,
    company_name: str,
    st_secrets=None,
    demo_mode: bool = False,
) -> AnalysisResult:
    """
    Analyse a filing and return a structured AnalysisResult.

    Behaviour by priority:
      1. demo_mode=True  → return demo result immediately (no network call)
      2. No API key      → return error result
      3. Live call OK    → return real result
      4. Quota/billing error from OpenAI → auto-fallback to demo result
      5. Any other error → return error result

    Never raises — all failures are captured in result.error.
    """

    # ── 1. Demo mode: return sample data right away ───────────────────────────
    if demo_mode:
        return _DEMO_RESULT

    # ── 2. No API key ─────────────────────────────────────────────────────────
    api_key = get_api_key(st_secrets)
    if not api_key:
        return AnalysisResult(
            what_changed="",
            key_catalysts=[],
            key_risks=[],
            thesis_impact="Stable",
            suggested_action="Hold",
            confidence_score=0,
            error=(
                "OPENAI_API_KEY not found. "
                "Add it in Replit Secrets (key name must be exactly OPENAI_API_KEY), "
                "then restart the app. Or enable Demo Mode to test the UI."
            ),
        )

    # ── 3. Fetch filing text ──────────────────────────────────────────────────
    try:
        filing_text = fetch_filing_text(filing_url)
    except FetchError as exc:
        return AnalysisResult(
            what_changed="",
            key_catalysts=[],
            key_risks=[],
            thesis_impact="Stable",
            suggested_action="Hold",
            confidence_score=0,
            error=f"Could not fetch filing text: {exc}",
        )

    # ── 4. Call OpenAI ────────────────────────────────────────────────────────
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
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
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=800,
        )

        raw_json = response.choices[0].message.content or "{}"
        data = json.loads(raw_json)

        return AnalysisResult(
            what_changed=data.get("what_changed", "No summary returned."),
            key_catalysts=data.get("key_catalysts", []),
            key_risks=data.get("key_risks", []),
            thesis_impact=data.get("thesis_impact", "Stable"),
            suggested_action=data.get("suggested_action", "Hold"),
            confidence_score=int(data.get("confidence_score", 0)),
        )

    except Exception as exc:
        # ── 4a. Quota / billing error → auto-fallback to demo ─────────────────
        if _is_quota_error(exc):
            demo = _DEMO_RESULT
            # Return a copy with a note attached via the error field
            return AnalysisResult(
                what_changed=demo.what_changed,
                key_catalysts=demo.key_catalysts,
                key_risks=demo.key_risks,
                thesis_impact=demo.thesis_impact,
                suggested_action=demo.suggested_action,
                confidence_score=demo.confidence_score,
                is_demo=True,
                error=(
                    "OpenAI quota exceeded — showing demo analysis instead. "
                    "Check your billing at platform.openai.com."
                ),
            )

        # ── 4b. Any other OpenAI error ────────────────────────────────────────
        return AnalysisResult(
            what_changed="",
            key_catalysts=[],
            key_risks=[],
            thesis_impact="Stable",
            suggested_action="Hold",
            confidence_score=0,
            error=f"OpenAI error: {exc}",
        )
