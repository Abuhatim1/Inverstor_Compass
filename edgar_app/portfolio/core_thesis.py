"""
portfolio/core_thesis.py
------------------------
Dynamic Thesis State Engine.

A `CoreThesis` is not a static note — it is a **continuously monitored
strategic state model** of one investment. It captures:

  • The PM's original investment intent (rationale, drivers, expected moat,
    expected management behaviour, expected margin/growth profile, valuation
    thesis, accepted risks, time horizon)
  • Required management execution assumptions
  • Bull / Base / Bear scenarios with live probabilities
  • A structured Risk/Return Matrix
  • A timeline of Thesis Validation Events (Confirmations / Deteriorations /
    Breaks / New Optionality)
  • A rolling Conviction Score history → Conviction Trend (Rising / Stable / Falling)

Every new filing analysis (and any future market-intel update) flows through
`apply_evaluation()`, which:
  1. Compares the new evidence against the thesis defence pool
  2. Produces validation events
  3. Reweights bull/base/bear scenario probabilities
  4. Updates the conviction history and recomputes the trend
  5. Recomputes the live thesis status + CIO commentary + drift flags

All storage is local JSON: `portfolio/core_theses.json`.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

import streamlit as st


# ── Storage ───────────────────────────────────────────────────────────────────

_DIR              = os.path.dirname(__file__)
_THESES_FILE      = os.path.join(_DIR, "core_theses.json")

_MAX_EVENTS               = 50    # cap validation_events list
_MAX_CONVICTION_HISTORY   = 12    # rolling window for trend


# ── Taxonomy ──────────────────────────────────────────────────────────────────

# Core thesis statuses (distinct from per-filing thesis_impact vocabulary)
THESIS_STATUS_STRENGTHENING = "Strengthening"
THESIS_STATUS_STABLE        = "Stable"
THESIS_STATUS_WEAKENING     = "Weakening"
THESIS_STATUS_BROKEN        = "Broken"

THESIS_STATUSES = (
    THESIS_STATUS_STRENGTHENING,
    THESIS_STATUS_STABLE,
    THESIS_STATUS_WEAKENING,
    THESIS_STATUS_BROKEN,
)

THESIS_STATUS_BADGE: dict[str, tuple[str, str]] = {
    THESIS_STATUS_STRENGTHENING: ("📈", "Strengthening"),
    THESIS_STATUS_STABLE:        ("➖", "Stable"),
    THESIS_STATUS_WEAKENING:     ("📉", "Weakening"),
    THESIS_STATUS_BROKEN:        ("💔", "Broken"),
}

TIME_HORIZONS = ("6-12 months", "1-3 years", "3-5 years", "5+ years")

# Conviction trend vocabulary
CONVICTION_RISING  = "Rising"
CONVICTION_STABLE  = "Stable"
CONVICTION_FALLING = "Falling"
CONVICTION_TRENDS  = (CONVICTION_RISING, CONVICTION_STABLE, CONVICTION_FALLING)
CONVICTION_BADGE: dict[str, tuple[str, str]] = {
    CONVICTION_RISING:  ("↗️", "Rising"),
    CONVICTION_STABLE:  ("➖", "Stable"),
    CONVICTION_FALLING: ("↘️", "Falling"),
}

# Risk Matrix taxonomy
RISK_CATEGORIES = (
    "Regulatory", "Competitive", "Execution", "Macro",
    "Financial", "Technology", "ESG", "Geopolitical", "Other",
)
RISK_STATUSES   = ("Active", "Monitoring", "Realized", "Mitigated", "Closed")
RISK_SEVERITIES = ("Low", "Medium", "High", "Critical")
RISK_KINDS      = ("Risk", "Opportunity")

# Validation Event taxonomy
EVENT_CONFIRMATION = "Confirmation"
EVENT_DETERIORATION = "Deterioration"
EVENT_BREAK         = "Break"
EVENT_OPTIONALITY   = "New Optionality"
EVENT_TYPES = (EVENT_CONFIRMATION, EVENT_DETERIORATION, EVENT_BREAK, EVENT_OPTIONALITY)
EVENT_BADGE: dict[str, tuple[str, str]] = {
    EVENT_CONFIRMATION:  ("✅", "Confirmation"),
    EVENT_DETERIORATION: ("⚠️", "Deterioration"),
    EVENT_BREAK:         ("💔", "Break"),
    EVENT_OPTIONALITY:   ("✨", "New Optionality"),
}


# ── Nested dataclasses ────────────────────────────────────────────────────────

@dataclass
class ScenarioCase:
    """One scenario (Bull / Base / Bear) with live probability."""
    description:        str = ""
    probability:        float = 0.0      # 0–100, three cases must sum to ~100
    valuation_target:   str = ""         # e.g. "$250/share at 25× FCF"
    key_assumptions:    list[str] = field(default_factory=list)


@dataclass
class RiskMatrixItem:
    """One row of the Risk/Return Matrix."""
    id:                          str = ""
    name:                        str = ""
    category:                    str = "Other"
    kind:                        str = "Risk"        # Risk | Opportunity
    severity:                    str = "Medium"      # Low | Medium | High | Critical
    current_status:              str = "Monitoring"  # Active | Monitoring | …
    expected_impact:             str = ""            # narrative
    early_warning_indicators:    list[str] = field(default_factory=list)
    required_action:             str = ""
    possible_hedge:              str = ""
    last_updated:                str = ""

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.last_updated:
            self.last_updated = date.today().isoformat()


@dataclass
class ThesisValidationEvent:
    """A point-in-time event in the thesis lifecycle (immutable history)."""
    timestamp:    str = ""
    event_type:   str = EVENT_CONFIRMATION   # one of EVENT_TYPES
    source:       str = "SEC Filing"         # "10-Q", "Market Intel", "Manual", etc.
    title:        str = ""                   # short headline
    detail:       str = ""                   # longer description
    related_terms: list[str] = field(default_factory=list)
    # How this event reweighted bull/base/bear (deltas applied, before renormalize)
    scenario_deltas: dict[str, float] = field(default_factory=dict)


# ── CoreThesis ────────────────────────────────────────────────────────────────

@dataclass
class CoreThesis:
    """Dynamic strategic state model for one investment."""
    # Identity
    ticker:                  str
    company_name:            str

    # ── Manually authored intent (the "thesis") ──────────────────────────────
    rationale:               str   = ""
    thesis_drivers:          list[str] = field(default_factory=list)
    expected_value_drivers:  list[str] = field(default_factory=list)  # NEW
    expected_catalysts:      list[str] = field(default_factory=list)
    key_risks:               list[str] = field(default_factory=list)
    expected_moat:           str   = ""
    expected_management:     str   = ""
    expected_margin_profile: str   = ""
    expected_growth_profile: str   = ""
    time_horizon:            str   = "1-3 years"
    valuation_thesis:        str   = ""
    # Required management execution assumptions (NEW)
    management_execution_assumptions: list[str] = field(default_factory=list)

    # ── Scenarios (manual seed, live probabilities) ──────────────────────────
    scenario_bull: ScenarioCase = field(default_factory=lambda: ScenarioCase(probability=25.0))
    scenario_base: ScenarioCase = field(default_factory=lambda: ScenarioCase(probability=55.0))
    scenario_bear: ScenarioCase = field(default_factory=lambda: ScenarioCase(probability=20.0))

    # ── Risk / Return Matrix ─────────────────────────────────────────────────
    risk_matrix: list[RiskMatrixItem] = field(default_factory=list)

    # ── Validation event log (newest first, capped) ──────────────────────────
    validation_events: list[ThesisValidationEvent] = field(default_factory=list)

    # ── Conviction tracking ──────────────────────────────────────────────────
    conviction_history: list[int] = field(default_factory=list)  # rolling 0–100 scores
    conviction_trend:   str       = CONVICTION_STABLE            # derived
    last_conviction_score: int    = 50

    # ── Live status / drift ──────────────────────────────────────────────────
    thesis_status:           str   = THESIS_STATUS_STABLE
    last_status_change:      str   = ""
    cio_commentary:          str   = ""
    drift_detected:          bool  = False
    drift_summary:           str   = ""

    # ── Provenance ──────────────────────────────────────────────────────────
    # "Manual" = hand-authored in the UI; "Imported" = extracted from a doc
    source_type:             str   = "Manual"
    imported_from:           str   = ""   # original filename
    imported_at:             str   = ""   # ISO datetime
    import_source_kind:      str   = ""   # "PDF" | "DOCX" | "TXT"

    # ── Audit ────────────────────────────────────────────────────────────────
    created_at:              str   = ""
    updated_at:              str   = ""
    last_evaluated:          str   = ""
    evaluations_count:       int   = 0

    def __post_init__(self):
        # Coerce nested dataclasses when loaded from JSON
        self.scenario_bull = _coerce_scenario(self.scenario_bull)
        self.scenario_base = _coerce_scenario(self.scenario_base)
        self.scenario_bear = _coerce_scenario(self.scenario_bear)
        self.risk_matrix = [
            r for r in (_coerce_risk(x) for x in (self.risk_matrix or []))
            if r is not None
        ]
        self.validation_events = [
            e for e in (_coerce_event(x) for x in (self.validation_events or []))
            if e is not None
        ]


# ── Nested-dataclass coercion helpers ────────────────────────────────────────

def _coerce_scenario(x) -> ScenarioCase:
    if isinstance(x, ScenarioCase):
        return x
    if not isinstance(x, dict):
        return ScenarioCase()
    valid = {f.name for f in dataclasses.fields(ScenarioCase)}
    return ScenarioCase(**{k: v for k, v in x.items() if k in valid})


def _coerce_risk(x) -> RiskMatrixItem | None:
    if isinstance(x, RiskMatrixItem):
        return x
    if not isinstance(x, dict):
        return None
    valid = {f.name for f in dataclasses.fields(RiskMatrixItem)}
    try:
        return RiskMatrixItem(**{k: v for k, v in x.items() if k in valid})
    except Exception:
        return None


def _coerce_event(x) -> ThesisValidationEvent | None:
    if isinstance(x, ThesisValidationEvent):
        return x
    if not isinstance(x, dict):
        return None
    valid = {f.name for f in dataclasses.fields(ThesisValidationEvent)}
    try:
        return ThesisValidationEvent(**{k: v for k, v in x.items() if k in valid})
    except Exception:
        return None


# ── Persistence ───────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_all_core_theses() -> dict[str, CoreThesis]:
    """Load every core thesis from disk. Returns {} on missing/corrupt file."""
    if not os.path.exists(_THESES_FILE):
        return {}
    try:
        with open(_THESES_FILE, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    valid = {f.name for f in dataclasses.fields(CoreThesis)}
    out: dict[str, CoreThesis] = {}
    for ticker, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            filtered = {k: v for k, v in entry.items() if k in valid}
            out[ticker.upper()] = CoreThesis(**filtered)
        except Exception:
            continue
    return out


def save_all_core_theses(theses: dict[str, CoreThesis]) -> None:
    os.makedirs(_DIR, exist_ok=True)
    payload = {t.upper(): asdict(c) for t, c in theses.items()}
    with open(_THESES_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    load_all_core_theses.clear()


def load_core_thesis(ticker: str) -> CoreThesis | None:
    return load_all_core_theses().get(ticker.upper())


def save_core_thesis(thesis: CoreThesis) -> None:
    """Upsert a single CoreThesis to disk."""
    all_theses = load_all_core_theses()
    if not thesis.created_at:
        thesis.created_at = date.today().isoformat()
    thesis.updated_at = datetime.now().isoformat()
    all_theses[thesis.ticker.upper()] = thesis
    save_all_core_theses(all_theses)


def delete_core_thesis(ticker: str) -> bool:
    all_theses = load_all_core_theses()
    key = ticker.upper()
    if key in all_theses:
        del all_theses[key]
        save_all_core_theses(all_theses)
        return True
    return False


def upsert_core_thesis_fields(
    ticker:                            str,
    company_name:                      str,
    *,
    rationale:                         str = "",
    thesis_drivers:                    list[str] | None = None,
    expected_value_drivers:            list[str] | None = None,
    expected_catalysts:                list[str] | None = None,
    key_risks:                         list[str] | None = None,
    expected_moat:                     str = "",
    expected_management:               str = "",
    expected_margin_profile:           str = "",
    expected_growth_profile:           str = "",
    time_horizon:                      str = "1-3 years",
    valuation_thesis:                  str = "",
    management_execution_assumptions:  list[str] | None = None,
    # Scenario seed (optional — defaults preserved if existing)
    bull_description:                  str | None = None,
    bull_probability:                  float | None = None,
    bull_valuation_target:             str | None = None,
    bull_key_assumptions:              list[str] | None = None,
    base_description:                  str | None = None,
    base_probability:                  float | None = None,
    base_valuation_target:             str | None = None,
    base_key_assumptions:              list[str] | None = None,
    bear_description:                  str | None = None,
    bear_probability:                  float | None = None,
    bear_valuation_target:             str | None = None,
    bear_key_assumptions:              list[str] | None = None,
) -> CoreThesis:
    """Create or update the manually-authored fields of a CoreThesis.

    Live state (status, scenario probabilities once auto-adjusted, events,
    conviction history, risk matrix) is preserved when updating.
    """
    existing = load_core_thesis(ticker)
    if existing is None:
        c = CoreThesis(ticker=ticker.upper(), company_name=company_name)
    else:
        c = existing
        c.company_name = company_name or c.company_name

    c.rationale               = rationale
    c.thesis_drivers          = list(thesis_drivers or [])
    c.expected_value_drivers  = list(expected_value_drivers or [])
    c.expected_catalysts      = list(expected_catalysts or [])
    c.key_risks               = list(key_risks or [])
    c.expected_moat           = expected_moat
    c.expected_management     = expected_management
    c.expected_margin_profile = expected_margin_profile
    c.expected_growth_profile = expected_growth_profile
    c.time_horizon            = time_horizon
    c.valuation_thesis        = valuation_thesis
    c.management_execution_assumptions = list(management_execution_assumptions or [])

    # Scenarios — update only the fields provided; preserve probabilities
    # that the engine has been auto-adjusting unless caller explicitly sets them
    def _apply(scn: ScenarioCase, desc, prob, tgt, kas):
        if desc is not None:  scn.description = desc
        if prob is not None:  scn.probability = float(prob)
        if tgt is not None:   scn.valuation_target = tgt
        if kas is not None:   scn.key_assumptions = list(kas)
    _apply(c.scenario_bull, bull_description, bull_probability,
           bull_valuation_target, bull_key_assumptions)
    _apply(c.scenario_base, base_description, base_probability,
           base_valuation_target, base_key_assumptions)
    _apply(c.scenario_bear, bear_description, bear_probability,
           bear_valuation_target, bear_key_assumptions)

    # If the user manually set any probability, renormalize.
    if any(p is not None for p in (bull_probability, base_probability, bear_probability)):
        _renormalize_scenarios(c)

    save_core_thesis(c)
    return c


# ── Risk Matrix CRUD ─────────────────────────────────────────────────────────

def upsert_risk_item(
    ticker:                     str,
    *,
    item_id:                    str = "",
    name:                       str = "",
    category:                   str = "Other",
    kind:                       str = "Risk",
    severity:                   str = "Medium",
    current_status:             str = "Monitoring",
    expected_impact:            str = "",
    early_warning_indicators:   list[str] | None = None,
    required_action:            str = "",
    possible_hedge:             str = "",
) -> RiskMatrixItem | None:
    """Insert (item_id empty) or update an existing risk-matrix row."""
    core = load_core_thesis(ticker)
    if core is None:
        return None

    target = None
    if item_id:
        target = next((r for r in core.risk_matrix if r.id == item_id), None)
    if target is None:
        target = RiskMatrixItem(id=item_id or uuid.uuid4().hex[:12])
        core.risk_matrix.append(target)

    target.name                     = name
    target.category                 = category
    target.kind                     = kind
    target.severity                 = severity
    target.current_status           = current_status
    target.expected_impact          = expected_impact
    target.early_warning_indicators = list(early_warning_indicators or [])
    target.required_action          = required_action
    target.possible_hedge           = possible_hedge
    target.last_updated             = date.today().isoformat()

    save_core_thesis(core)
    return target


def delete_risk_item(ticker: str, item_id: str) -> bool:
    core = load_core_thesis(ticker)
    if core is None:
        return False
    before = len(core.risk_matrix)
    core.risk_matrix = [r for r in core.risk_matrix if r.id != item_id]
    if len(core.risk_matrix) == before:
        return False
    save_core_thesis(core)
    return True


# ── Evaluator helpers ────────────────────────────────────────────────────────

_STOPWORDS = {
    "with", "that", "this", "from", "into", "have", "will", "they",
    "their", "them", "than", "what", "when", "which", "more", "over",
    "should", "would", "could", "company", "business", "expected",
    "growth", "strong", "stable", "weak", "broken", "high", "higher",
    "lower", "good", "bad", "next", "year", "quarter", "report",
    "filing", "analysis", "result", "results", "term", "long", "short",
    "near", "based", "above", "below", "between", "through", "during",
    "market", "markets", "product", "products", "service", "services",
    "customer", "customers", "period", "periods", "increase", "increases",
    "decrease", "decreases", "level", "levels", "value", "values",
    "share", "shares", "share-price", "price", "prices", "rate", "rates",
    "operating", "capital", "industry", "sector", "segment", "segments",
    "demand", "supply", "year-over-year",
}


def _tokenize(text: str) -> set[str]:
    """Lowercase, strip punctuation, return distinctive word set (length ≥ 4)."""
    if not text:
        return set()
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _overlap(core_text: str, target_texts: list[str]) -> tuple[int, list[str]]:
    """Distinct tokens from `core_text` that appear in any target text."""
    core_tokens = _tokenize(core_text)
    if not core_tokens:
        return 0, []
    matched: set[str] = set()
    for t in target_texts:
        matched |= core_tokens & _tokenize(t)
    return len(matched), sorted(matched)


def _renormalize_scenarios(core: CoreThesis, floor: float = 5.0) -> None:
    """Ensure bull/base/bear sum to 100 with each ≥ floor."""
    b = max(floor, float(core.scenario_bull.probability))
    m = max(floor, float(core.scenario_base.probability))
    r = max(floor, float(core.scenario_bear.probability))
    tot = b + m + r
    if tot <= 0:
        b = m = r = 33.33
        tot = 100.0
    core.scenario_bull.probability = round(b / tot * 100.0, 1)
    core.scenario_base.probability = round(m / tot * 100.0, 1)
    core.scenario_bear.probability = round(r / tot * 100.0, 1)


def _normalize_conviction(score: int) -> int:
    """Map raw evaluator score (~-8…+5) → 0-100 conviction."""
    return max(0, min(100, int(round(50 + score * 8))))


def _derive_conviction_trend(history: list[int]) -> str:
    """Compare recent 3 readings against prior 3+ to determine trend direction."""
    if len(history) < 3:
        return CONVICTION_STABLE
    recent = history[-3:]
    prior  = history[:-3]
    if not prior:
        # Fall back: compare first half vs second half
        return CONVICTION_STABLE
    avg_recent = sum(recent) / len(recent)
    avg_prior  = sum(prior)  / len(prior)
    diff = avg_recent - avg_prior
    if diff >= 6:
        return CONVICTION_RISING
    if diff <= -6:
        return CONVICTION_FALLING
    return CONVICTION_STABLE


# ── Evaluator ─────────────────────────────────────────────────────────────────

def evaluate_thesis_against_analysis(
    core,                    # CoreThesis
    analysis,                # AnalysisResult
    comparison=None,         # FilingComparison | None
) -> tuple[str, str, bool, str, list[str], int, dict]:
    """Pure evaluation — produces status + commentary + signals.

    Returns: (new_status, cio_commentary, drift_detected, drift_summary,
              reasons, raw_score, signals_bundle)

    `signals_bundle` carries the structured pieces used by `apply_evaluation`
    to generate validation events and adjust scenario probabilities:
       {
         "attacks_count", "support_count", "attacked_terms", "supported_terms",
         "thesis_impact", "new_catalysts", "expected_catalysts_text",
         "margin_decline", "rev_decline", "guidance", "tone",
       }
    """
    weakened     = list(getattr(comparison, "what_weakened", []) or []) if comparison else []
    improved     = list(getattr(comparison, "what_improved", []) or []) if comparison else []
    new_concerns = list(getattr(comparison, "new_concerns",  []) or []) if comparison else []
    new_catalysts = list(getattr(comparison, "new_catalysts", []) or []) if comparison else []
    margin_trend = (getattr(comparison, "margin_trend", "") or "") if comparison else ""
    rev_trend    = (getattr(comparison, "revenue_growth_trend", "") or "") if comparison else ""
    guidance     = (getattr(comparison, "guidance_trend", "") or "") if comparison else ""
    tone         = (getattr(comparison, "management_tone", "") or "") if comparison else ""

    thesis_impact     = getattr(analysis, "thesis_impact", "Stable")
    filing_risks      = list(getattr(analysis, "key_risks",     []) or [])
    filing_catalysts  = list(getattr(analysis, "key_catalysts", []) or [])

    # Core thesis "defense pool" — drivers + value drivers + moat + mgmt
    core_pool_text = " ".join(
        list(core.thesis_drivers)
        + list(core.expected_value_drivers)
        + [core.expected_moat, core.expected_management]
        + list(core.management_execution_assumptions)
    )

    attacks_count, attacked = _overlap(
        core_pool_text, weakened + new_concerns + filing_risks
    )
    support_count, supported = _overlap(
        core_pool_text, improved + new_catalysts + filing_catalysts
    )

    score = 0
    reasons: list[str] = []

    if thesis_impact == "Strong":
        score += 2; reasons.append("Latest filing: thesis Strong")
    elif thesis_impact == "Broken":
        score -= 4; reasons.append("Latest filing: thesis Broken")
    elif thesis_impact == "Weak":
        score -= 2; reasons.append("Latest filing: thesis Weak")

    if support_count >= 2:
        score += 1
        reasons.append(f"{support_count} core thesis term(s) reinforced by filing")
    if attacks_count >= 2:
        score -= 2
        reasons.append(
            f"{attacks_count} core thesis term(s) under pressure: "
            f"{', '.join(attacked[:3])}"
        )
    elif attacks_count == 1:
        score -= 1
        reasons.append(f"Core thesis term under pressure: {attacked[0]}")

    expand_keywords = ("expand", "grow", "rising", "increase", "improv", "high")
    margin_decline = (margin_trend == "declining" and any(
        k in core.expected_margin_profile.lower() for k in expand_keywords
    ))
    rev_decline = (rev_trend == "declining" and any(
        k in core.expected_growth_profile.lower() for k in expand_keywords
    ))
    if margin_decline:
        score -= 1; reasons.append("Margins declining vs expected margin profile")
    if rev_decline:
        score -= 1; reasons.append("Revenue growth declining vs expected growth profile")
    if guidance in ("lowered", "withdrawn"):
        score -= 1; reasons.append(f"Guidance {guidance} this filing")
    if tone == "negative":
        score -= 1; reasons.append("Management tone turned negative")
    elif tone == "positive" and thesis_impact in ("Strong", "Stable"):
        score += 1; reasons.append("Management tone positive")

    # Map score → status — conservative Broken threshold (see prior layer)
    prev_status_for_break = core.thesis_status or THESIS_STATUS_STABLE
    breaks_now = (
        score <= -6
        or (thesis_impact == "Broken" and prev_status_for_break in
            (THESIS_STATUS_WEAKENING, THESIS_STATUS_BROKEN))
    )
    if breaks_now:
        new_status = THESIS_STATUS_BROKEN
    elif score <= -2:
        new_status = THESIS_STATUS_WEAKENING
    elif score >= 2:
        new_status = THESIS_STATUS_STRENGTHENING
    else:
        new_status = THESIS_STATUS_STABLE

    drift = (attacks_count >= 2) or (new_status == THESIS_STATUS_BROKEN)
    drift_summary = ""
    if drift:
        if attacked:
            drift_summary = (
                f"Narrative shift: original thesis terms "
                f"({', '.join(attacked[:3])}) now appearing in weakening / "
                f"risk sections of the latest filing."
            )
        else:
            drift_summary = (
                "Material thesis deterioration detected — the company narrative "
                "no longer aligns with the original investment case."
            )

    prev_status = core.thesis_status or THESIS_STATUS_STABLE
    top_reasons = reasons[:3] if reasons else ["No material signals from this filing"]
    if new_status == prev_status:
        cio = f"Status held at **{new_status}**. " + " · ".join(top_reasons[:2])
    else:
        cio = (
            f"Status changed from **{prev_status}** → **{new_status}**. "
            + " · ".join(top_reasons)
        )

    signals_bundle = {
        "attacks_count":           attacks_count,
        "support_count":           support_count,
        "attacked_terms":          attacked,
        "supported_terms":         supported,
        "thesis_impact":           thesis_impact,
        "new_catalysts":           new_catalysts,
        "margin_decline":          margin_decline,
        "rev_decline":             rev_decline,
        "guidance":                guidance,
        "tone":                    tone,
        "prev_status":             prev_status,
    }
    return new_status, cio, drift, drift_summary, reasons, score, signals_bundle


# ── Event generation + scenario adjustment ──────────────────────────────────

def _scenario_adjustment_for_event(event_type: str) -> dict[str, float]:
    """Deltas applied to bull/base/bear probability before renormalize."""
    if event_type == EVENT_CONFIRMATION:
        return {"bull": +5, "base": +1, "bear": -6}
    if event_type == EVENT_DETERIORATION:
        return {"bull": -5, "base": +1, "bear": +4}
    if event_type == EVENT_BREAK:
        return {"bull": -15, "base": -5, "bear": +20}
    if event_type == EVENT_OPTIONALITY:
        return {"bull": +4, "base": +1, "bear": -5}
    return {}


def _is_new_optionality(core: CoreThesis, new_catalysts: list[str]) -> tuple[bool, list[str]]:
    """Detect catalysts in the filing that are NOT in the original expected set."""
    if not new_catalysts:
        return False, []
    expected_tokens = _tokenize(" ".join(core.expected_catalysts))
    novel: list[str] = []
    for cat in new_catalysts:
        if not _tokenize(cat) & expected_tokens:
            novel.append(cat)
    return bool(novel), novel[:3]


def _build_validation_events(
    core:           CoreThesis,
    new_status:     str,
    prev_status:    str,
    signals:        dict,
    source:         str = "SEC Filing",
) -> list[ThesisValidationEvent]:
    """Generate Confirmation / Deterioration / Break / Optionality events."""
    events: list[ThesisValidationEvent] = []
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Break — status flipped to Broken
    if new_status == THESIS_STATUS_BROKEN and prev_status != THESIS_STATUS_BROKEN:
        deltas = _scenario_adjustment_for_event(EVENT_BREAK)
        terms = signals.get("attacked_terms", [])[:3]
        events.append(ThesisValidationEvent(
            timestamp=now, event_type=EVENT_BREAK, source=source,
            title=(f"Thesis broke — drivers under attack: {', '.join(terms)}"
                   if terms else "Thesis broken by latest filing"),
            detail=("Latest filing materially contradicts original investment "
                    "case across multiple core drivers."),
            related_terms=terms, scenario_deltas=deltas,
        ))

    # Deterioration — moved into Weakening, or material driver attack
    elif new_status == THESIS_STATUS_WEAKENING and prev_status not in (
        THESIS_STATUS_WEAKENING, THESIS_STATUS_BROKEN
    ):
        deltas = _scenario_adjustment_for_event(EVENT_DETERIORATION)
        terms = signals.get("attacked_terms", [])[:3]
        events.append(ThesisValidationEvent(
            timestamp=now, event_type=EVENT_DETERIORATION, source=source,
            title=(f"Thesis weakening — pressure on: {', '.join(terms)}"
                   if terms else "Thesis weakening from latest filing"),
            detail=("Negative signals outweigh confirmations — see CIO commentary."),
            related_terms=terms, scenario_deltas=deltas,
        ))
    elif (signals.get("attacks_count", 0) >= 2
          and new_status not in (THESIS_STATUS_BROKEN,)):
        # Standalone deterioration (status didn't flip, but drivers attacked)
        deltas = _scenario_adjustment_for_event(EVENT_DETERIORATION)
        terms = signals.get("attacked_terms", [])[:3]
        events.append(ThesisValidationEvent(
            timestamp=now, event_type=EVENT_DETERIORATION, source=source,
            title=f"Multiple thesis terms under pressure: {', '.join(terms)}",
            detail="Filing flagged risks aligned with core thesis defenders.",
            related_terms=terms, scenario_deltas=deltas,
        ))

    # Confirmation — strong filing or driver support
    if (signals.get("thesis_impact") == "Strong"
            and signals.get("support_count", 0) >= 1):
        deltas = _scenario_adjustment_for_event(EVENT_CONFIRMATION)
        terms = signals.get("supported_terms", [])[:3]
        events.append(ThesisValidationEvent(
            timestamp=now, event_type=EVENT_CONFIRMATION, source=source,
            title=(f"Thesis confirmed — reinforced: {', '.join(terms)}"
                   if terms else "Filing confirms thesis"),
            detail=("Latest filing reinforces the original investment case "
                    "across the defended drivers."),
            related_terms=terms, scenario_deltas=deltas,
        ))

    # New Optionality — catalysts in filing that weren't expected
    has_new, novel = _is_new_optionality(core, signals.get("new_catalysts", []))
    if has_new:
        deltas = _scenario_adjustment_for_event(EVENT_OPTIONALITY)
        events.append(ThesisValidationEvent(
            timestamp=now, event_type=EVENT_OPTIONALITY, source=source,
            title="New optionality identified in latest filing",
            detail="; ".join(novel),
            related_terms=novel, scenario_deltas=deltas,
        ))

    return events


def _apply_scenario_deltas(core: CoreThesis, events: list[ThesisValidationEvent]) -> None:
    """Apply each event's scenario_deltas, then renormalize."""
    if not events:
        return
    bull = float(core.scenario_bull.probability)
    base = float(core.scenario_base.probability)
    bear = float(core.scenario_bear.probability)
    for ev in events:
        d = ev.scenario_deltas or {}
        bull += float(d.get("bull", 0))
        base += float(d.get("base", 0))
        bear += float(d.get("bear", 0))
    core.scenario_bull.probability = bull
    core.scenario_base.probability = base
    core.scenario_bear.probability = bear
    _renormalize_scenarios(core)


def apply_evaluation(core, analysis, comparison=None, source: str = "SEC Filing") -> CoreThesis:
    """Full orchestration:
       evaluate → events → scenario reweight → conviction update → persist.
    """
    (new_status, cio, drift, drift_summary, _reasons,
     raw_score, signals) = evaluate_thesis_against_analysis(core, analysis, comparison)

    prev_status = signals.get("prev_status", core.thesis_status)

    # Validation events
    events = _build_validation_events(core, new_status, prev_status, signals, source=source)
    if events:
        # Prepend newest, cap history
        core.validation_events = (events + list(core.validation_events))[:_MAX_EVENTS]

    # Scenario probability adjustment from this round's events
    _apply_scenario_deltas(core, events)

    # Conviction score + trend
    conviction = _normalize_conviction(raw_score)
    core.conviction_history = (list(core.conviction_history) + [conviction])[-_MAX_CONVICTION_HISTORY:]
    core.last_conviction_score = conviction
    core.conviction_trend = _derive_conviction_trend(core.conviction_history)

    # Live status fields
    if new_status != core.thesis_status:
        core.last_status_change = date.today().isoformat()
    core.thesis_status     = new_status
    core.cio_commentary    = cio
    core.drift_detected    = drift
    core.drift_summary     = drift_summary
    core.last_evaluated    = datetime.now().isoformat()
    core.evaluations_count = (core.evaluations_count or 0) + 1

    save_core_thesis(core)
    return core
