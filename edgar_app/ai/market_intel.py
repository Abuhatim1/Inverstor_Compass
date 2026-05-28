"""
ai/market_intel.py
------------------
External Market Intelligence Layer.

Classifies external reports (InvestingPro, analyst notes, valuation summaries,
technical analysis) into structured intelligence, then reconciles the market
view against the internal filing-based thesis.

DESIGN PRINCIPLE: External intelligence is ADVISORY only. It is classified,
compared, and surfaced — but it NEVER overrides grounded filing evidence.
The reconciliation score measures alignment, not authority.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime


# ── Taxonomy ──────────────────────────────────────────────────────────────────

INTEL_CATEGORIES: dict[str, str] = {
    "analyst_consensus":    "Analyst Consensus",
    "valuation_view":       "Valuation View",
    "technical_positioning":"Technical Positioning",
    "market_sentiment":     "Market Sentiment",
    "macro_concerns":       "Macro Concerns",
}

INTEL_CATEGORY_ICON: dict[str, str] = {
    "analyst_consensus":    "👥",
    "valuation_view":       "💰",
    "technical_positioning":"📉",
    "market_sentiment":     "🎭",
    "macro_concerns":       "🌍",
}

INTEL_VIEW_BADGE: dict[str, tuple[str, str]] = {
    "Bullish": ("🟢", "Bullish"),
    "Neutral": ("⚪", "Neutral"),
    "Bearish": ("🔴", "Bearish"),
    "Mixed":   ("🟡", "Mixed"),
}

ALIGNMENT_BADGE: dict[str, tuple[str, str]] = {
    "Strongly Aligned": ("🟢", "Strongly Aligned"),
    "Broadly Aligned":  ("🔵", "Broadly Aligned"),
    "Mixed":            ("🟡", "Mixed"),
    "Divergent":        ("🟠", "Divergent"),
    "Conflicted":       ("🔴", "Conflicted"),
    "No Baseline":      ("⚪", "No Baseline"),
}

MISPRICING_BADGE: dict[str, tuple[str, str]] = {
    "Overvalued by Market":   ("🔴", "Overvalued by Market"),
    "Undervalued by Market":  ("🟢", "Undervalued by Market"),
    "Fairly Priced":          ("⚪", "Fairly Priced"),
    "Unclear":                ("❓", "Unclear"),
    "No Baseline":            ("⚪", "No Baseline"),
}

DETECTION_TAXONOMY: list[str] = [
    "Market overly optimistic",
    "Market overly pessimistic",
    "Valuation disconnect",
    "Technical/fundamental divergence",
    "Consensus aligns with thesis",
    "Sentiment diverges from fundamentals",
]

DETECTION_ICON: dict[str, str] = {
    "Market overly optimistic":         "📈",
    "Market overly pessimistic":        "📉",
    "Valuation disconnect":             "💰",
    "Technical/fundamental divergence": "📊",
    "Consensus aligns with thesis":     "✅",
    "Sentiment diverges from fundamentals": "🎭",
}

# Source types the user can tag their paste/upload with
INTEL_SOURCE_TYPES: list[str] = [
    "InvestingPro Report",
    "Analyst Report",
    "Valuation Summary",
    "Technical Analysis",
    "News Article",
    "Other",
]


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class ClassifiedIntelligence:
    """One classified block of external intelligence."""
    category:   str         # key from INTEL_CATEGORIES
    summary:    str         # 1-2 sentence distillation
    view:       str         # "Bullish" | "Neutral" | "Bearish" | "Mixed"
    key_points: list[str]   # 2-4 concrete points extracted from the source


@dataclass
class ReconciliationResult:
    """Market view vs internal filing thesis."""
    consensus_alignment_score: int          # 0-100
    alignment_label:           str          # "Strongly Aligned" … "No Baseline"
    detections:                list[str]    # subset of DETECTION_TAXONOMY
    potential_mispricing:      str          # from MISPRICING_BADGE
    mispricing_rationale:      str          # why this signal was detected
    market_view_summary:       str          # 1-2 sentence overall external view
    reconciliation_notes:      list[str]    # 2-4 bullets: where they agree/disagree


@dataclass
class MarketIntelResult:
    """Full result of a market intelligence analysis session."""
    ticker:                  str
    company_name:            str
    source_type:             str                        # from INTEL_SOURCE_TYPES
    source_snippet:          str                        # first 300 chars of source text
    classified:              list[ClassifiedIntelligence]
    reconciliation:          ReconciliationResult
    internal_thesis_impact:  str                        # from portfolio entry
    internal_action:         str                        # from portfolio entry
    internal_confidence:     int                        # from portfolio entry
    has_internal_basis:      bool                       # False = no filing analysis available
    analyzed_at:             str                        # ISO timestamp


# ── Demo result ───────────────────────────────────────────────────────────────

DEMO_MARKET_INTEL = MarketIntelResult(
    ticker="DEMO",
    company_name="Demo Corp",
    source_type="Analyst Report",
    source_snippet=(
        "InvestingPro: DEMO Corp — 12-month target $185 (+18%). "
        "Consensus BUY (14/3/2). DCF implies $172 fair value. "
        "RSI 62, trending above 200-day MA. Sentiment: cautiously bullish…"
    ),
    classified=[
        ClassifiedIntelligence(
            category="analyst_consensus",
            summary="14 Buy, 3 Hold, 2 Sell. Median 12-month target $185, implying ~18% upside.",
            view="Bullish",
            key_points=[
                "Median target $185 (range $155–$210)",
                "Consensus BUY; no analyst currently at Sell in the past 30 days",
                "Earnings estimate revisions trending up over the past 60 days",
            ],
        ),
        ClassifiedIntelligence(
            category="valuation_view",
            summary=(
                "DCF-based fair value $172 on 8% discount rate; EV/EBITDA of 22x "
                "is at a 15% premium to the sector median."
            ),
            view="Mixed",
            key_points=[
                "DCF fair value $172 (8% WACC, 3% terminal growth)",
                "EV/EBITDA 22x vs sector median 19x — modest premium",
                "PEG ratio 1.4 — growth-adjusted, not obviously overvalued",
            ],
        ),
        ClassifiedIntelligence(
            category="technical_positioning",
            summary="Price trending above 200-day MA with RSI at 62 — momentum constructive, not overbought.",
            view="Bullish",
            key_points=[
                "RSI 62 — bullish momentum, below overbought threshold (70)",
                "Price 8% above 200-day moving average",
                "MACD recently crossed above signal line on daily chart",
            ],
        ),
        ClassifiedIntelligence(
            category="market_sentiment",
            summary="Options market shows elevated call volume; short interest declined 12% in the last two weeks.",
            view="Bullish",
            key_points=[
                "Short interest declined from 4.2% to 3.7% of float",
                "Call/put ratio elevated at 1.6x over trailing 30 days",
                "Institutional net buying reported in latest 13F filings",
            ],
        ),
        ClassifiedIntelligence(
            category="macro_concerns",
            summary="Analysts flag rising rate environment and FX headwinds as the primary macro risks to the thesis.",
            view="Bearish",
            key_points=[
                "Federal Reserve policy path may compress multiples if rates stay elevated",
                "35% international revenue exposed to USD strengthening",
                "Discretionary spending risk flagged if macro deteriorates",
            ],
        ),
    ],
    reconciliation=ReconciliationResult(
        consensus_alignment_score=76,
        alignment_label="Broadly Aligned",
        detections=["Consensus aligns with thesis", "Valuation disconnect"],
        potential_mispricing="Undervalued by Market",
        mispricing_rationale=(
            "The internal filing analysis found stronger margin expansion (200 bps) "
            "and enterprise contract momentum than the analyst DCF models appear to reflect. "
            "The $172 DCF may underweight the structural margin improvement."
        ),
        market_view_summary=(
            "External market intelligence is broadly constructive — consensus BUY, "
            "positive technical momentum, and declining short interest. "
            "The primary concern is macro sensitivity (rates, FX)."
        ),
        reconciliation_notes=[
            "ALIGNED: Both internal thesis and analyst consensus are constructive on revenue growth driven by enterprise contracts.",
            "ALIGNED: Technical momentum (RSI 62, above 200-day MA) supports the internal Strong/Buy conclusion.",
            "DIVERGENT: Analyst DCF at $172 implies fair value; internal filing analysis suggests margin expansion is underpriced — potential disconnect.",
            "WATCH: Macro concerns (FX, rates) flagged by analysts match the key risks in the internal analysis — these are the main thesis-breakers.",
        ],
    ),
    internal_thesis_impact="Strong",
    internal_action="Buy",
    internal_confidence=72,
    has_internal_basis=True,
    analyzed_at=datetime.now().isoformat(),
)


# ── AI prompt ─────────────────────────────────────────────────────────────────

_MARKET_INTEL_SYSTEM_PROMPT = """\
You are a senior equity research analyst evaluating external market intelligence.

You will receive:
1. An external report or text (analyst note, InvestingPro summary, valuation, technical analysis, etc.)
2. An internal thesis from primary SEC filing analysis (the grounded baseline)

CRITICAL RULE: External market intelligence is ADVISORY. It NEVER overrides grounded \
filing evidence. Your job is to classify the external view and surface where it aligns \
with or diverges from the filing-based thesis — not to replace it.

Respond ONLY with valid JSON, no markdown, no explanation.

Required JSON structure:
{
  "classified": [
    {
      "category": "analyst_consensus | valuation_view | technical_positioning | market_sentiment | macro_concerns",
      "summary": "1-2 sentence distillation of what this source says for this category",
      "view": "Bullish | Neutral | Bearish | Mixed",
      "key_points": ["concrete extracted point 1", "point 2", "point 3"]
    }
  ],
  "reconciliation": {
    "consensus_alignment_score": 0-100,
    "alignment_label": "Strongly Aligned | Broadly Aligned | Mixed | Divergent | Conflicted | No Baseline",
    "detections": ["zero or more from: Market overly optimistic | Market overly pessimistic | Valuation disconnect | Technical/fundamental divergence | Consensus aligns with thesis | Sentiment diverges from fundamentals"],
    "potential_mispricing": "Overvalued by Market | Undervalued by Market | Fairly Priced | Unclear | No Baseline",
    "mispricing_rationale": "1-2 sentences explaining why this mispricing signal was detected, citing specific evidence",
    "market_view_summary": "1-2 sentence distillation of the overall external market view",
    "reconciliation_notes": [
      "ALIGNED or DIVERGENT: specific note on one dimension where market and thesis agree or differ",
      "second note",
      "third note"
    ]
  }
}

RULES:
- Only include categories actually present in the text (minimum 1, maximum 5 total classified items).
- key_points must be EXTRACTED from the source — do not invent numbers or targets.
- Alignment score: 80-100=Strongly Aligned, 60-79=Broadly Aligned, 40-59=Mixed, 20-39=Divergent, 0-19=Conflicted.
- If no internal thesis provided: alignment_label="No Baseline", score=50, mispricing="No Baseline".
- detections must be from the allowed list; use [] if none apply.
- "Market overly optimistic": set when external sentiment is significantly more bullish than filing evidence supports.
- "Valuation disconnect": set when external price targets or multiples diverge materially from filing-implied intrinsic value trend.
- reconciliation_notes prefix: start each note with "ALIGNED:" or "DIVERGENT:" or "WATCH:" for clarity.
- Do not hedge every conclusion. Be direct about where market and thesis agree or disagree.
"""


def _build_thesis_context(
    internal_thesis: dict | None,
    ticker: str,
    company_name: str,
) -> str:
    if not internal_thesis:
        return f"No internal filing analysis available for {ticker} ({company_name})."
    return (
        f"Internal filing thesis for {ticker} ({company_name}):\n"
        f"- Thesis impact: {internal_thesis.get('thesis_impact', 'Unknown')}\n"
        f"- Suggested action: {internal_thesis.get('suggested_action', 'Unknown')}\n"
        f"- Confidence score: {internal_thesis.get('confidence_score', 0)}/100\n"
        f"- Key catalysts: {'; '.join(internal_thesis.get('key_catalysts', []))}\n"
        f"- Key risks: {'; '.join(internal_thesis.get('key_risks', []))}"
    )


# ── Analysis function ─────────────────────────────────────────────────────────

def analyze_market_intel(
    text:            str,
    ticker:          str,
    company_name:    str,
    source_type:     str,
    internal_thesis: dict | None = None,   # from portfolio entry or AnalysisResult
    st_secrets=None,
    demo_mode:       bool = False,
) -> MarketIntelResult:
    """
    Classify external market intelligence and reconcile against the internal thesis.

    Parameters
    ----------
    text            : Raw pasted or uploaded external text.
    ticker          : Portfolio ticker (for display and context).
    company_name    : Company name.
    source_type     : User-selected source type (from INTEL_SOURCE_TYPES).
    internal_thesis : Dict with keys thesis_impact, suggested_action,
                      confidence_score, key_catalysts, key_risks.
                      None if no prior filing analysis is available.
    st_secrets      : Streamlit secrets object (for OPENAI_API_KEY).
    demo_mode       : If True, return demo result immediately.
    """
    now = datetime.now().isoformat()
    snippet = text[:300].strip()
    has_basis = internal_thesis is not None

    if demo_mode:
        demo = DEMO_MARKET_INTEL
        return MarketIntelResult(
            ticker=ticker or demo.ticker,
            company_name=company_name or demo.company_name,
            source_type=source_type,
            source_snippet=snippet or demo.source_snippet,
            classified=demo.classified,
            reconciliation=demo.reconciliation,
            internal_thesis_impact=internal_thesis.get("thesis_impact", "—") if internal_thesis else "—",
            internal_action=internal_thesis.get("suggested_action", "—") if internal_thesis else "—",
            internal_confidence=internal_thesis.get("confidence_score", 0) if internal_thesis else 0,
            has_internal_basis=has_basis,
            analyzed_at=now,
        )

    # ── API key ───────────────────────────────────────────────────────────────
    # Read key from env first, then from Streamlit secrets (never evaluate secrets as bool)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key and st_secrets is not None:
        try:
            api_key = (st_secrets.get("OPENAI_API_KEY") or "").strip()
        except Exception:
            pass

    if not api_key:
        return _error_result(
            ticker, company_name, source_type, snippet, internal_thesis,
            has_basis, now, "No OpenAI API key found."
        )

    thesis_context = _build_thesis_context(internal_thesis, ticker, company_name)
    truncated_text = text[:6000]  # keep prompt manageable

    user_prompt = (
        f"Source type: {source_type}\n"
        f"Company: {company_name} ({ticker})\n\n"
        f"--- EXTERNAL INTELLIGENCE ---\n{truncated_text}\n\n"
        f"--- INTERNAL THESIS BASELINE ---\n{thesis_context}"
    )

    try:
        from openai import OpenAI

        client   = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _MARKET_INTEL_SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=1500,
        )

        raw_json = response.choices[0].message.content or "{}"
        data     = json.loads(raw_json)

        classified = [
            ClassifiedIntelligence(
                category=c.get("category", "market_sentiment"),
                summary=c.get("summary", ""),
                view=c.get("view", "Mixed"),
                key_points=c.get("key_points") or [],
            )
            for c in (data.get("classified") or [])
            if isinstance(c, dict)
        ]

        rec_data = data.get("reconciliation") or {}
        reconciliation = ReconciliationResult(
            consensus_alignment_score=int(rec_data.get("consensus_alignment_score", 50)),
            alignment_label=rec_data.get("alignment_label", "Mixed"),
            detections=[
                d for d in (rec_data.get("detections") or [])
                if d in DETECTION_TAXONOMY
            ],
            potential_mispricing=rec_data.get("potential_mispricing", "Unclear"),
            mispricing_rationale=rec_data.get("mispricing_rationale", ""),
            market_view_summary=rec_data.get("market_view_summary", ""),
            reconciliation_notes=rec_data.get("reconciliation_notes") or [],
        )

        return MarketIntelResult(
            ticker=ticker,
            company_name=company_name,
            source_type=source_type,
            source_snippet=snippet,
            classified=classified,
            reconciliation=reconciliation,
            internal_thesis_impact=internal_thesis.get("thesis_impact", "—") if internal_thesis else "—",
            internal_action=internal_thesis.get("suggested_action", "—") if internal_thesis else "—",
            internal_confidence=internal_thesis.get("confidence_score", 0) if internal_thesis else 0,
            has_internal_basis=has_basis,
            analyzed_at=now,
        )

    except Exception as exc:
        msg = str(exc)
        if "quota" in msg.lower() or "rate" in msg.lower() or "billing" in msg.lower():
            demo = DEMO_MARKET_INTEL
            return MarketIntelResult(
                ticker=ticker,
                company_name=company_name,
                source_type=source_type,
                source_snippet=snippet or demo.source_snippet,
                classified=demo.classified,
                reconciliation=demo.reconciliation,
                internal_thesis_impact=internal_thesis.get("thesis_impact", "—") if internal_thesis else "—",
                internal_action=internal_thesis.get("suggested_action", "—") if internal_thesis else "—",
                internal_confidence=internal_thesis.get("confidence_score", 0) if internal_thesis else 0,
                has_internal_basis=has_basis,
                analyzed_at=now,
            )
        return _error_result(
            ticker, company_name, source_type, snippet, internal_thesis,
            has_basis, now, f"Analysis failed: {msg}"
        )


def _error_result(
    ticker, company_name, source_type, snippet, internal_thesis,
    has_basis, now, error_msg
) -> MarketIntelResult:
    return MarketIntelResult(
        ticker=ticker,
        company_name=company_name,
        source_type=source_type,
        source_snippet=snippet,
        classified=[
            ClassifiedIntelligence(
                category="market_sentiment",
                summary=f"Error: {error_msg}",
                view="Mixed",
                key_points=[],
            )
        ],
        reconciliation=ReconciliationResult(
            consensus_alignment_score=0,
            alignment_label="No Baseline",
            detections=[],
            potential_mispricing="Unclear",
            mispricing_rationale=error_msg,
            market_view_summary="Analysis could not be completed.",
            reconciliation_notes=[],
        ),
        internal_thesis_impact=internal_thesis.get("thesis_impact", "—") if internal_thesis else "—",
        internal_action=internal_thesis.get("suggested_action", "—") if internal_thesis else "—",
        internal_confidence=internal_thesis.get("confidence_score", 0) if internal_thesis else 0,
        has_internal_basis=has_basis,
        analyzed_at=now,
    )
