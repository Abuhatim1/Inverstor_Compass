"""
ai/analyzer.py
--------------
Real AI analysis of SEC filings using the OpenAI API.

Reads OPENAI_API_KEY from environment (set it in Replit Secrets).
Returns a structured AnalysisResult dataclass with investment-relevant fields.
"""

import json
import os
from dataclasses import dataclass

from .fetcher import FetchError, fetch_filing_text

# ── Check for API key at import time (soft check — no crash) ─────────────────
_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_AVAILABLE = bool(_API_KEY)


@dataclass
class AnalysisResult:
    what_changed: str
    key_catalysts: list[str]
    key_risks: list[str]
    thesis_impact: str        # "Strong" | "Stable" | "Weak" | "Broken"
    suggested_action: str     # "Buy" | "Hold" | "Reduce" | "Exit"
    confidence_score: int     # 0–100
    error: str | None = None  # set if analysis failed


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
) -> AnalysisResult:
    """
    Fetch a filing from SEC.gov and return a structured AI analysis.

    Returns an AnalysisResult with `error` set (and other fields as empty
    defaults) if the API key is missing or any step fails — never raises.
    """
    # ── Guard: no API key ─────────────────────────────────────────────────────
    if not OPENAI_AVAILABLE:
        return AnalysisResult(
            what_changed="",
            key_catalysts=[],
            key_risks=[],
            thesis_impact="Stable",
            suggested_action="Hold",
            confidence_score=0,
            error=(
                "OPENAI_API_KEY is not set. "
                "Add it to Replit Secrets to enable AI analysis."
            ),
        )

    # ── Step 1: Fetch filing text ─────────────────────────────────────────────
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

    # ── Step 2: Call OpenAI ───────────────────────────────────────────────────
    try:
        from openai import OpenAI  # imported here so missing package doesn't break the whole module

        client = OpenAI(api_key=_API_KEY)
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

    except Exception as exc:  # noqa: BLE001
        return AnalysisResult(
            what_changed="",
            key_catalysts=[],
            key_risks=[],
            thesis_impact="Stable",
            suggested_action="Hold",
            confidence_score=0,
            error=f"OpenAI error: {exc}",
        )

    # ── Step 3: Parse response into dataclass ─────────────────────────────────
    return AnalysisResult(
        what_changed=data.get("what_changed", "No summary returned."),
        key_catalysts=data.get("key_catalysts", []),
        key_risks=data.get("key_risks", []),
        thesis_impact=data.get("thesis_impact", "Stable"),
        suggested_action=data.get("suggested_action", "Hold"),
        confidence_score=int(data.get("confidence_score", 0)),
    )
