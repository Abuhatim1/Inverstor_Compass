"""
ai/analyzer.py
--------------
Real AI analysis of SEC filings using the OpenAI API.

Reads OPENAI_API_KEY dynamically on every call (not at import time),
so secrets added after startup are picked up without a restart.
"""

import json
import os
from dataclasses import dataclass, field

from .fetcher import FetchError, fetch_filing_text


@dataclass
class AnalysisResult:
    what_changed: str
    key_catalysts: list[str]
    key_risks: list[str]
    thesis_impact: str        # "Strong" | "Stable" | "Weak" | "Broken"
    suggested_action: str     # "Buy" | "Hold" | "Reduce" | "Exit"
    confidence_score: int     # 0–100
    error: str | None = None  # set if analysis failed


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


# Legacy module-level flag kept for backward compat — reads env at import time.
# Use get_api_key() instead for reliable runtime checks.
OPENAI_AVAILABLE: bool = bool(os.environ.get("OPENAI_API_KEY", "").strip())


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


def analyze_filing(
    filing_url: str,
    form_type: str,
    company_name: str,
    st_secrets=None,
) -> AnalysisResult:
    """
    Fetch a filing from SEC.gov and return a structured AI analysis.

    Pass st_secrets=st.secrets from the Streamlit app as a fallback key source.
    Returns an AnalysisResult with `error` set if anything fails — never raises.
    """
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
                "then restart the app."
            ),
        )

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

    except Exception as exc:
        return AnalysisResult(
            what_changed="",
            key_catalysts=[],
            key_risks=[],
            thesis_impact="Stable",
            suggested_action="Hold",
            confidence_score=0,
            error=f"OpenAI error: {exc}",
        )

    return AnalysisResult(
        what_changed=data.get("what_changed", "No summary returned."),
        key_catalysts=data.get("key_catalysts", []),
        key_risks=data.get("key_risks", []),
        thesis_impact=data.get("thesis_impact", "Stable"),
        suggested_action=data.get("suggested_action", "Hold"),
        confidence_score=int(data.get("confidence_score", 0)),
    )
