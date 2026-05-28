"""
portfolio/core_thesis.py
------------------------
Thesis Memory Layer.

The **Core Thesis** is the *original investment thesis* captured by the
portfolio manager at (or near) the time the position was opened.
It is **not** rewritten on every new filing — it is a stable reference
point against which all subsequent filings, comparisons, and market
intelligence are evaluated.

Stored per ticker in `portfolio/core_theses.json`.

The companion `evaluate_thesis_against_analysis()` updates the live
status fields (`thesis_status`, `cio_commentary`, `drift_detected`,
`drift_summary`) after every filing analysis, without touching the
manually authored intent fields.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime


# ── Storage ───────────────────────────────────────────────────────────────────

_DIR              = os.path.dirname(__file__)
_THESES_FILE      = os.path.join(_DIR, "core_theses.json")


# ── Taxonomy ──────────────────────────────────────────────────────────────────

# Core thesis statuses — distinct from the per-filing thesis_impact vocabulary.
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


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class CoreThesis:
    """Original purchase-time investment thesis + live tracking state."""
    # Identity
    ticker:                  str
    company_name:            str

    # ── Manually authored intent ─────────────────────────────────────────────
    rationale:               str   = ""    # why this position exists
    thesis_drivers:          list[str] = field(default_factory=list)
    expected_catalysts:      list[str] = field(default_factory=list)
    key_risks:               list[str] = field(default_factory=list)
    expected_moat:           str   = ""
    expected_management:     str   = ""    # how mgmt should behave
    expected_margin_profile: str   = ""    # e.g. "expanding to 30%+ operating margin"
    expected_growth_profile: str   = ""    # e.g. "15-20% revenue CAGR"
    time_horizon:            str   = "1-3 years"
    valuation_thesis:        str   = ""    # one-liner expected valuation case

    created_at:              str   = ""
    updated_at:              str   = ""

    # ── Live tracking (auto-updated by evaluator) ────────────────────────────
    thesis_status:           str   = THESIS_STATUS_STABLE
    last_status_change:      str   = ""    # ISO date when status last flipped
    cio_commentary:          str   = ""    # short narrative — why current status
    drift_detected:          bool  = False
    drift_summary:           str   = ""    # one-line description of drift
    last_evaluated:          str   = ""    # ISO timestamp of last evaluation
    evaluations_count:       int   = 0


# ── Persistence ───────────────────────────────────────────────────────────────

def load_all_core_theses() -> dict[str, CoreThesis]:
    """Load every core thesis from disk. Returns {} on missing/corrupt file."""
    if not os.path.exists(_THESES_FILE):
        return {}
    try:
        with open(_THESES_FILE, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    import dataclasses
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
    ticker:                  str,
    company_name:            str,
    *,
    rationale:               str = "",
    thesis_drivers:          list[str] | None = None,
    expected_catalysts:      list[str] | None = None,
    key_risks:               list[str] | None = None,
    expected_moat:           str = "",
    expected_management:     str = "",
    expected_margin_profile: str = "",
    expected_growth_profile: str = "",
    time_horizon:            str = "1-3 years",
    valuation_thesis:        str = "",
) -> CoreThesis:
    """Create or update the manually-authored fields of a CoreThesis.

    Live tracking fields (status, commentary, drift) are preserved when
    updating an existing thesis.
    """
    existing = load_core_thesis(ticker)
    if existing is None:
        c = CoreThesis(ticker=ticker.upper(), company_name=company_name)
    else:
        c = existing
        c.company_name = company_name or c.company_name

    c.rationale               = rationale
    c.thesis_drivers          = list(thesis_drivers or [])
    c.expected_catalysts      = list(expected_catalysts or [])
    c.key_risks               = list(key_risks or [])
    c.expected_moat           = expected_moat
    c.expected_management     = expected_management
    c.expected_margin_profile = expected_margin_profile
    c.expected_growth_profile = expected_growth_profile
    c.time_horizon            = time_horizon
    c.valuation_thesis        = valuation_thesis
    save_core_thesis(c)
    return c


# ── Evaluator ─────────────────────────────────────────────────────────────────

_STOPWORDS = {
    "with", "that", "this", "from", "into", "have", "will", "they",
    "their", "them", "than", "what", "when", "which", "more", "over",
    "should", "would", "could", "company", "business", "expected",
    "growth", "strong", "stable", "weak", "broken", "high", "higher",
    "lower", "good", "bad", "next", "year", "quarter", "report",
    "filing", "analysis", "result", "results", "term", "long", "short",
    "near", "based", "above", "below", "between", "through", "during",
    # Generic business / financial nouns that would otherwise produce
    # false-positive drift signals on virtually every filing
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
    """Distinct tokens from `core_text` that appear in any of `target_texts`."""
    core_tokens = _tokenize(core_text)
    if not core_tokens:
        return 0, []
    matched: set[str] = set()
    for t in target_texts:
        matched |= core_tokens & _tokenize(t)
    return len(matched), sorted(matched)


def evaluate_thesis_against_analysis(
    core,                    # CoreThesis
    analysis,                # AnalysisResult
    comparison=None,         # FilingComparison | None
) -> tuple[str, str, bool, str, list[str]]:
    """
    Compare the latest filing analysis against the original core thesis.

    Returns: (new_status, cio_commentary, drift_detected, drift_summary, reasons)
    """
    # Pull comparison signals (defensive)
    weakened     = list(getattr(comparison, "what_weakened", []) or []) if comparison else []
    improved     = list(getattr(comparison, "what_improved", []) or []) if comparison else []
    new_concerns = list(getattr(comparison, "new_concerns",  []) or []) if comparison else []
    new_catalysts = list(getattr(comparison, "new_catalysts", []) or []) if comparison else []
    margin_trend = (getattr(comparison, "margin_trend", "") or "") if comparison else ""
    rev_trend    = (getattr(comparison, "revenue_growth_trend", "") or "") if comparison else ""
    guidance     = (getattr(comparison, "guidance_trend", "") or "") if comparison else ""
    tone         = (getattr(comparison, "management_tone", "") or "") if comparison else ""

    # Pull filing-level signals
    thesis_impact     = getattr(analysis, "thesis_impact", "Stable")
    filing_risks      = list(getattr(analysis, "key_risks",     []) or [])
    filing_catalysts  = list(getattr(analysis, "key_catalysts", []) or [])

    # Pre-build core-thesis pool — drivers + moat are the *intent* we defend
    core_pool_text = " ".join(
        core.thesis_drivers + [core.expected_moat, core.expected_management]
    )

    # How many core-thesis terms now appear in WEAKENING / RISK contexts?
    attacks_count, attacked = _overlap(
        core_pool_text, weakened + new_concerns + filing_risks
    )
    # How many appear in SUPPORTING contexts?
    support_count, _supported = _overlap(
        core_pool_text, improved + new_catalysts + filing_catalysts
    )

    # Build score (positive = strengthening, negative = weakening)
    score = 0
    reasons: list[str] = []

    if thesis_impact == "Strong":
        score += 2; reasons.append("Latest filing: thesis Strong")
    elif thesis_impact == "Broken":
        score -= 4; reasons.append("Latest filing: thesis Broken")
    elif thesis_impact == "Weak":
        score -= 2; reasons.append("Latest filing: thesis Weak")
    # "Stable" → 0

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

    # Expected-profile contradictions
    expand_keywords = ("expand", "grow", "rising", "increase", "improv", "high")
    if margin_trend == "declining" and any(
        k in core.expected_margin_profile.lower() for k in expand_keywords
    ):
        score -= 1
        reasons.append("Margins declining vs expected margin profile")
    if rev_trend == "declining" and any(
        k in core.expected_growth_profile.lower() for k in expand_keywords
    ):
        score -= 1
        reasons.append("Revenue growth declining vs expected growth profile")
    if guidance in ("lowered", "withdrawn"):
        score -= 1
        reasons.append(f"Guidance {guidance} this filing")
    if tone == "negative":
        score -= 1
        reasons.append("Management tone turned negative")
    elif tone == "positive" and thesis_impact in ("Strong", "Stable"):
        score += 1
        reasons.append("Management tone positive")

    # Map score → status.
    # A single "Broken" filing alone (score = -4) is NOT enough to break
    # a long-term thesis — that would let a one-quarter outlier permanently
    # mark a multi-year position as Broken. Require either deeper corroboration
    # (score ≤ -6: Broken filing + ≥2 additional negative signals) OR an
    # already-Weakening thesis confirming with another Broken filing.
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

    # Drift detection — narrative is materially diverging from original intent
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

    # CIO commentary — short, structured
    prev_status = core.thesis_status or THESIS_STATUS_STABLE
    top_reasons = reasons[:3] if reasons else ["No material signals from this filing"]
    if new_status == prev_status:
        cio = f"Status held at **{new_status}**. " + " · ".join(top_reasons[:2])
    else:
        cio = (
            f"Status changed from **{prev_status}** → **{new_status}**. "
            + " · ".join(top_reasons)
        )

    return new_status, cio, drift, drift_summary, reasons


def apply_evaluation(core, analysis, comparison=None) -> "CoreThesis":
    """Run the evaluator and persist the updated live-tracking fields."""
    new_status, cio, drift, drift_summary, _reasons = evaluate_thesis_against_analysis(
        core, analysis, comparison
    )
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
