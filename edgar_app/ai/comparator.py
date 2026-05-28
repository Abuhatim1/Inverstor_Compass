"""
ai/comparator.py
----------------
FilingComparison dataclass + conviction adjustment calculator.

Populated by analyze_filing() when a previous filing is available.
The AI returns seven trend fields plus four narrative lists;
compute_conviction_adjustment() converts those into a -20 … +20 score
that is then applied on top of the base confidence_score.
"""

from dataclasses import dataclass, field


# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class FilingComparison:
    # Four narrative sections (AI-generated bullet points)
    what_improved:   list[str]
    what_weakened:   list[str]
    new_concerns:    list[str]
    new_catalysts:   list[str]

    # Seven trend fields  (AI-assigned labels from fixed option sets)
    revenue_growth_trend: str   # "improving" | "stable" | "declining"
    margin_trend:         str   # "improving" | "stable" | "declining"
    cash_trend:           str   # "improving" | "stable" | "declining"
    debt_trend:           str   # "improving" | "stable" | "declining"
                                #   (improving = debt reduced / position strengthened)
    management_tone:      str   # "positive" | "neutral" | "cautious" | "negative"
    guidance_trend:       str   # "raised" | "maintained" | "lowered"
                                #   | "withdrawn" | "not_mentioned"

    # Calculated by compute_conviction_adjustment() — stored for display
    conviction_adjustment: int  # -20 … +20


# ── Scoring tables ────────────────────────────────────────────────────────────

_TREND = {"improving": +2, "stable": 0, "declining": -2}

_TONE = {"positive": +3, "neutral": 0, "cautious": -2, "negative": -4}

_GUIDANCE = {
    "raised":        +4,
    "maintained":     0,
    "lowered":       -4,
    "withdrawn":     -6,
    "not_mentioned":  0,
}


def compute_conviction_adjustment(comp: FilingComparison) -> int:
    """
    Convert a FilingComparison into a score in the range [-20, +20].

    Positive = filing reinforces the thesis.
    Negative = filing deteriorates the thesis.
    """
    score  = _TREND.get(comp.revenue_growth_trend, 0)
    score += _TREND.get(comp.margin_trend,          0)
    score += _TREND.get(comp.cash_trend,            0)
    score += _TREND.get(comp.debt_trend,            0)
    score += _TONE.get(comp.management_tone,        0)
    score += _GUIDANCE.get(comp.guidance_trend,     0)

    # Narrative: each "improved" item is good, each "weakened" / "concern" is bad
    score += min(len(comp.what_improved),  3) * 2   # max +6
    score -= min(len(comp.what_weakened),  3) * 2   # max -6
    score += min(len(comp.new_catalysts),  2) * 1   # max +2
    score -= min(len(comp.new_concerns),   2) * 2   # max -4

    return max(-20, min(20, score))


def comparison_from_dict(d: dict) -> FilingComparison:
    """
    Build a FilingComparison from the raw dict returned by the AI.
    Unknown / missing keys fall back to safe defaults.
    """
    comp = FilingComparison(
        what_improved=d.get("what_improved", []),
        what_weakened=d.get("what_weakened", []),
        new_concerns=d.get("new_concerns",   []),
        new_catalysts=d.get("new_catalysts", []),
        revenue_growth_trend=d.get("revenue_growth_trend", "stable"),
        margin_trend=d.get("margin_trend",                 "stable"),
        cash_trend=d.get("cash_trend",                     "stable"),
        debt_trend=d.get("debt_trend",                     "stable"),
        management_tone=d.get("management_tone",           "neutral"),
        guidance_trend=d.get("guidance_trend",             "not_mentioned"),
        conviction_adjustment=0,  # filled in below
    )
    comp.conviction_adjustment = compute_conviction_adjustment(comp)
    return comp
