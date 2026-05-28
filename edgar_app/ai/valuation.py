"""
ai/valuation.py
---------------
Damodaran-Informed Value Driver Engine.

Every filing analysis now includes an assessment of the 8 core intrinsic-
value drivers identified by Aswath Damodaran, plus a composite priority
score. The engine is deliberately rule-based and lightweight — no DCF is
built. Every conclusion must be grounded in evidence from the filing.

Value Drivers
-------------
1. Cash Flow Impact          — Are operating cash flows improving?
2. Growth Quality            — Is growth accelerating and fundamentals-backed?
3. Reinvestment Efficiency   — Is capex / R&D producing better growth?
4. Margin Trajectory         — Are margins structurally improving?
5. Cost of Capital / Risk    — Does the event raise the discount rate?
6. Competitive Advantage     — Is the moat strengthening or weakening?
7. Narrative vs Numbers      — Does management language match the numbers?
8. Repricing Risk            — Will market expectations need to be reset?

Priority Score Formula
----------------------
    Priority = Thesis × Valuation × Risk × Confidence × Portfolio Weight

Scaled to 0–100. High = event likely to move intrinsic value meaningfully.
"""

from dataclasses import dataclass, field


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class ValueDrivers:
    """The 8 Damodaran value drivers, each with a rating and 1-sentence note."""
    cash_flow_impact:          str  # "Positive" | "Neutral" | "Negative"
    cash_flow_notes:           str
    growth_quality:            str  # "Improving" | "Stable" | "Weakening"
    growth_quality_notes:      str
    reinvestment_efficiency:   str  # "Improving" | "Stable" | "Weakening" | "Unknown"
    reinvestment_notes:        str
    margin_trajectory:         str  # "Improving" | "Stable" | "Weakening"
    margin_notes:              str
    cost_of_capital_pressure:  str  # "Low" | "Medium" | "High"
    capital_pressure_notes:    str
    moat_direction:            str  # "Strengthening" | "Stable" | "Weakening"
    moat_notes:                str
    narrative_vs_numbers:      str  # "Aligned" | "Mixed" | "Diverging"
    narrative_notes:           str
    repricing_risk:            str  # "Low" | "Medium" | "High"
    repricing_notes:           str


@dataclass
class ValuationResult:
    drivers:             ValueDrivers
    valuation_impact:    str           # "Value Accretive" | "Neutral" | "Value Destructive" | "Unclear / Low Confidence"
    valuation_reasoning: list[str]     # 3-5 evidence-grounded reasons
    priority_score:      int           # 0–100 composite priority score


# ── Display helpers ───────────────────────────────────────────────────────────

# Value driver display: (field_attr, rating_attr, label, icon_map)
DRIVER_DISPLAY = [
    ("cash_flow_impact",         "cash_flow_notes",         "Cash Flow Impact",       {
        "Positive":  "✅", "Neutral": "⚪", "Negative": "🔴",
    }),
    ("growth_quality",           "growth_quality_notes",    "Growth Quality",         {
        "Improving": "📈", "Stable":  "➡️", "Weakening": "📉",
    }),
    ("reinvestment_efficiency",  "reinvestment_notes",      "Reinvestment",           {
        "Improving": "✅", "Stable":  "⚪", "Weakening": "🔴", "Unknown": "❓",
    }),
    ("margin_trajectory",        "margin_notes",            "Margin Trajectory",      {
        "Improving": "📈", "Stable":  "➡️", "Weakening": "📉",
    }),
    ("cost_of_capital_pressure", "capital_pressure_notes",  "Capital Risk",           {
        "Low":    "🟢", "Medium": "🟡", "High": "🔴",
    }),
    ("moat_direction",           "moat_notes",              "Competitive Moat",       {
        "Strengthening": "🏰", "Stable": "⚪", "Weakening": "🧱",
    }),
    ("narrative_vs_numbers",     "narrative_notes",         "Narrative vs Numbers",   {
        "Aligned": "✅", "Mixed": "🟡", "Diverging": "⚠️",
    }),
    ("repricing_risk",           "repricing_notes",         "Repricing Risk",         {
        "Low": "🟢", "Medium": "🟡", "High": "🔴",
    }),
]

VALUATION_IMPACT_BADGE = {
    "Value Accretive":            ("🟢", "Value Accretive"),
    "Neutral":                    ("⚪", "Neutral"),
    "Value Destructive":          ("🔴", "Value Destructive"),
    "Unclear / Low Confidence":   ("❓", "Unclear / Low Confidence"),
}


# ── Priority score ────────────────────────────────────────────────────────────

_THESIS_SCORE = {"Strong": 4, "Stable": 2, "Weak": 1, "Broken": 0}
_VALUATION_SCORE = {
    "Value Accretive":           3.0,
    "Neutral":                   1.0,
    "Value Destructive":         0.5,
    "Unclear / Low Confidence":  0.5,
}
_RISK_FACTOR = {"Low": 1.0, "Medium": 0.8, "High": 0.6}


def compute_priority_score(
    thesis_impact:           str,
    valuation_impact:        str,
    cost_of_capital_pressure: str,
    confidence_score:        int,
    portfolio_weight:        float = 1.0,
) -> int:
    """
    Priority = Thesis × Valuation × RiskFactor × Confidence × PortfolioWeight

    Scaled to 0–100. Maximum raw value = 4 × 3 × 1.0 × 1.0 × 1.0 = 12.0.
    """
    t = _THESIS_SCORE.get(thesis_impact, 2)
    v = _VALUATION_SCORE.get(valuation_impact, 0.5)
    r = _RISK_FACTOR.get(cost_of_capital_pressure, 0.8)
    c = max(0, min(100, confidence_score)) / 100.0
    w = max(0.0, min(2.0, portfolio_weight))
    raw = t * v * r * c * w
    return max(0, min(100, int((raw / 12.0) * 100)))


# ── Parser ────────────────────────────────────────────────────────────────────

def valuation_from_dict(d: dict | None) -> "ValuationResult | None":
    """
    Parse the raw 'value_drivers' JSON block from the AI response into a
    ValuationResult. Returns None silently on any malformed input.
    """
    if not isinstance(d, dict):
        return None
    try:
        drivers = ValueDrivers(
            cash_flow_impact=d.get("cash_flow_impact", "Neutral"),
            cash_flow_notes=d.get("cash_flow_notes", ""),
            growth_quality=d.get("growth_quality", "Stable"),
            growth_quality_notes=d.get("growth_quality_notes", ""),
            reinvestment_efficiency=d.get("reinvestment_efficiency", "Unknown"),
            reinvestment_notes=d.get("reinvestment_notes", ""),
            margin_trajectory=d.get("margin_trajectory", "Stable"),
            margin_notes=d.get("margin_notes", ""),
            cost_of_capital_pressure=d.get("cost_of_capital_pressure", "Medium"),
            capital_pressure_notes=d.get("capital_pressure_notes", ""),
            moat_direction=d.get("moat_direction", "Stable"),
            moat_notes=d.get("moat_notes", ""),
            narrative_vs_numbers=d.get("narrative_vs_numbers", "Mixed"),
            narrative_notes=d.get("narrative_notes", ""),
            repricing_risk=d.get("repricing_risk", "Medium"),
            repricing_notes=d.get("repricing_notes", ""),
        )
        return ValuationResult(
            drivers=drivers,
            valuation_impact=d.get("valuation_impact", "Unclear / Low Confidence"),
            valuation_reasoning=d.get("valuation_reasoning", []),
            priority_score=0,  # computed by caller after AnalysisResult is assembled
        )
    except Exception:
        return None


def valuation_from_cached(d: dict | None) -> "ValuationResult | None":
    """
    Reconstruct a ValuationResult from a cached dict (produced by asdict()).
    The nested 'drivers' key holds the ValueDrivers dict.
    """
    if not isinstance(d, dict):
        return None
    try:
        drivers_raw = d.get("drivers", {})
        drivers = ValueDrivers(**drivers_raw) if drivers_raw else None
        if drivers is None:
            return None
        return ValuationResult(
            drivers=drivers,
            valuation_impact=d.get("valuation_impact", "Unclear / Low Confidence"),
            valuation_reasoning=d.get("valuation_reasoning", []),
            priority_score=d.get("priority_score", 0),
        )
    except Exception:
        return None


# ── JSON schema string (injected into AI prompts) ─────────────────────────────

VALUATION_SCHEMA = """\
  "value_drivers": {
    "cash_flow_impact": "Positive | Neutral | Negative",
    "cash_flow_notes": "1-sentence evidence-grounded explanation",
    "growth_quality": "Improving | Stable | Weakening",
    "growth_quality_notes": "1-sentence explanation",
    "reinvestment_efficiency": "Improving | Stable | Weakening | Unknown",
    "reinvestment_notes": "1-sentence explanation",
    "margin_trajectory": "Improving | Stable | Weakening",
    "margin_notes": "1-sentence explanation",
    "cost_of_capital_pressure": "Low | Medium | High",
    "capital_pressure_notes": "1-sentence explanation",
    "moat_direction": "Strengthening | Stable | Weakening",
    "moat_notes": "1-sentence explanation",
    "narrative_vs_numbers": "Aligned | Mixed | Diverging",
    "narrative_notes": "1-sentence explanation comparing language and numbers",
    "repricing_risk": "Low | Medium | High",
    "repricing_notes": "1-sentence explanation of market expectation impact",
    "valuation_impact": "Value Accretive | Neutral | Value Destructive | Unclear / Low Confidence",
    "valuation_reasoning": [
      "Reason 1 — grounded in a specific metric or quote",
      "Reason 2 — grounded in a specific metric or quote",
      "Reason 3 — grounded in a specific metric or quote"
    ]
  }

VALUE DRIVER RULES — follow precisely:
- Base every driver rating on evidence present in the filing excerpt.
- If a driver cannot be assessed from the available text, use the most
  conservative rating and note 'Insufficient data in excerpt'.
- narrative_vs_numbers: compare the tone of management language against
  the direction of the actual reported numbers. Diverging = language is
  more positive than the numbers justify (or vice versa).
- repricing_risk: High = event will likely force market to revise
  expectations materially. Low = accounting noise, no thesis change.
- valuation_impact: aggregate all 8 drivers into one classification.
  Use 'Unclear / Low Confidence' when the excerpt provides too little data.
- valuation_reasoning: exactly 3 concise reasons, each citing a metric
  or quote from the filing. No invented numbers.
"""
