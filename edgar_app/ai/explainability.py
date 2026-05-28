"""
ai/explainability.py
--------------------
Explainability & Uncertainty Layer.

Every major AI conclusion is annotated with:
  · Why the system believes it (reasoning)
  · What assumptions were used
  · What evidence is strongest
  · What evidence is weak or missing
  · An uncertainty level: High Confidence / Medium Confidence / Low Confidence / Speculative

The top-level UncertaintyAnalysis also surfaces:
  · Detected causes of uncertainty (from a fixed taxonomy)
  · "What Could Break This Thesis?" — 2-3 scenarios that would invalidate it
  · "What Would Change Our View?" — 2-3 data triggers for upgrade or downgrade
  · An overconfidence flag — set when narrative is more positive than numbers justify

Four topic-level ExplainabilityCard objects are always requested:
  valuation_impact, growth_quality, moat_direction, capital_risk
These map directly to the Damodaran Value Driver section.
"""

from dataclasses import dataclass, field


# ── Taxonomy ──────────────────────────────────────────────────────────────────

# Four topics always covered by explainability cards
EXPLAINABILITY_TOPICS: dict[str, str] = {
    "valuation_impact": "Valuation Impact",
    "growth_quality":   "Growth Quality",
    "moat_direction":   "Competitive Moat",
    "capital_risk":     "Capital Risk",
}

# Allowed uncertainty-cause strings (AI must pick from this list)
UNCERTAINTY_CAUSES = [
    "Incomplete filing data",
    "Weak or limited evidence",
    "Management narrative mismatch",
    "One-time accounting effects",
    "Macro-sensitive assumptions",
    "Non-recurring gains or losses",
]

# Cause → (icon, short display label)
CAUSE_DISPLAY: dict[str, tuple[str, str]] = {
    "Incomplete filing data":        ("📄", "Incomplete data"),
    "Weak or limited evidence":      ("⚠️", "Weak evidence"),
    "Management narrative mismatch": ("🗣️", "Narrative mismatch"),
    "One-time accounting effects":   ("📊", "Accounting effects"),
    "Macro-sensitive assumptions":   ("🌍", "Macro assumptions"),
    "Non-recurring gains or losses": ("📈", "Non-recurring items"),
}

# Uncertainty badge: level → (icon, label)
UNCERTAINTY_BADGE: dict[str, tuple[str, str]] = {
    "High Confidence":   ("🟢", "High Confidence"),
    "Medium Confidence": ("🟡", "Medium Confidence"),
    "Low Confidence":    ("🟠", "Low Confidence"),
    "Speculative":       ("🔴", "Speculative"),
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class ExplainabilityCard:
    """Explainability annotation for one specific topic/conclusion."""
    topic:             str         # one of EXPLAINABILITY_TOPICS keys
    reasoning:         str         # why the system reached this conclusion
    assumptions:       list[str]   # key assumptions underlying the conclusion
    strongest_evidence: str        # most compelling piece of supporting evidence
    weak_evidence:     str         # missing or weakest evidence
    uncertainty:       str         # "High Confidence" | "Medium Confidence" | "Low Confidence" | "Speculative"


@dataclass
class UncertaintyAnalysis:
    """Top-level explainability + uncertainty for the whole analysis."""
    overall_uncertainty:    str         # same four-level scale
    uncertainty_causes:     list[str]   # subset of UNCERTAINTY_CAUSES
    what_could_break:       list[str]   # 2-3 thesis-invalidating scenarios
    what_would_change_view: list[str]   # 2-3 upgrade/downgrade triggers
    overconfidence_flag:    bool        # True when narrative > numbers
    cards:                  list[ExplainabilityCard] = field(default_factory=list)


# ── Display helpers ───────────────────────────────────────────────────────────

def uncertainty_badge(level: str) -> tuple[str, str]:
    """Return (icon, label) for a given uncertainty level."""
    return UNCERTAINTY_BADGE.get(level, ("❓", level))


# ── Parsers ───────────────────────────────────────────────────────────────────

def _card_from_dict(d: dict) -> ExplainabilityCard | None:
    if not isinstance(d, dict):
        return None
    try:
        return ExplainabilityCard(
            topic=d.get("topic", ""),
            reasoning=d.get("reasoning", ""),
            assumptions=d.get("assumptions") or [],
            strongest_evidence=d.get("strongest_evidence", ""),
            weak_evidence=d.get("weak_evidence", ""),
            uncertainty=d.get("uncertainty", "Low Confidence"),
        )
    except Exception:
        return None


def explainability_from_dict(d: dict | None) -> "UncertaintyAnalysis | None":
    """
    Parse the 'explainability' JSON block from the AI response.
    Returns None silently on malformed input.
    """
    if not isinstance(d, dict):
        return None
    try:
        raw_cards = d.get("cards") or []
        cards = [c for raw in raw_cards if (c := _card_from_dict(raw)) is not None]
        return UncertaintyAnalysis(
            overall_uncertainty=d.get("overall_uncertainty", "Low Confidence"),
            uncertainty_causes=[
                c for c in (d.get("uncertainty_causes") or [])
                if c in UNCERTAINTY_CAUSES
            ],
            what_could_break=d.get("what_could_break") or [],
            what_would_change_view=d.get("what_would_change_view") or [],
            overconfidence_flag=bool(d.get("overconfidence_flag", False)),
            cards=cards,
        )
    except Exception:
        return None


def explainability_from_cached(d: dict | None) -> "UncertaintyAnalysis | None":
    """Reconstruct an UncertaintyAnalysis from a cached asdict() dict."""
    if not isinstance(d, dict):
        return None
    try:
        raw_cards = d.get("cards") or []
        cards = []
        for raw in raw_cards:
            if isinstance(raw, dict):
                c = _card_from_dict(raw)
                if c:
                    cards.append(c)
        return UncertaintyAnalysis(
            overall_uncertainty=d.get("overall_uncertainty", "Low Confidence"),
            uncertainty_causes=d.get("uncertainty_causes") or [],
            what_could_break=d.get("what_could_break") or [],
            what_would_change_view=d.get("what_would_change_view") or [],
            overconfidence_flag=bool(d.get("overconfidence_flag", False)),
            cards=cards,
        )
    except Exception:
        return None


# ── JSON schema string (injected into AI prompts) ─────────────────────────────

EXPLAINABILITY_SCHEMA = """\
  "explainability": {
    "overall_uncertainty": "High Confidence | Medium Confidence | Low Confidence | Speculative",
    "uncertainty_causes": [
      "Zero or more of: Incomplete filing data | Weak or limited evidence | \
Management narrative mismatch | One-time accounting effects | \
Macro-sensitive assumptions | Non-recurring gains or losses"
    ],
    "what_could_break": [
      "Concrete scenario 1 that would invalidate the main thesis",
      "Concrete scenario 2"
    ],
    "what_would_change_view": [
      "Specific data release or event that would upgrade the analysis",
      "Specific trigger that would downgrade the analysis"
    ],
    "overconfidence_flag": false,
    "cards": [
      {
        "topic": "valuation_impact",
        "reasoning": "Why we reached this valuation conclusion",
        "assumptions": ["Key assumption 1", "Key assumption 2"],
        "strongest_evidence": "The single most compelling evidence sentence",
        "weak_evidence": "What data is absent or weak that limits confidence",
        "uncertainty": "High Confidence | Medium Confidence | Low Confidence | Speculative"
      },
      { "topic": "growth_quality", "reasoning": "...", "assumptions": [], \
"strongest_evidence": "...", "weak_evidence": "...", "uncertainty": "..." },
      { "topic": "moat_direction", "reasoning": "...", "assumptions": [], \
"strongest_evidence": "...", "weak_evidence": "...", "uncertainty": "..." },
      { "topic": "capital_risk",   "reasoning": "...", "assumptions": [], \
"strongest_evidence": "...", "weak_evidence": "...", "uncertainty": "..." }
    ]
  }

EXPLAINABILITY RULES:
- Always include exactly 4 cards in the order: valuation_impact, growth_quality, moat_direction, capital_risk.
- overconfidence_flag = true when (a) narrative_vs_numbers is Diverging OR (b) more than 2 evidence
  items have confidence='low'. Never suppress a flag to appear more authoritative.
- what_could_break: must be SPECIFIC and FALSIFIABLE — not generic risks, but scenarios
  that would directly contradict the evidence used to support the current conclusion.
- what_would_change_view: must name concrete future data points (e.g. 'next quarter revenue
  guidance', 'credit rating change', 'competitor product launch') not vague statements.
- uncertainty levels: High Confidence = numbers confirm narrative, strong evidence found;
  Medium = gaps exist but direction is clear; Low = heavy inference from management language;
  Speculative = little to no supporting data in the excerpt.
"""
