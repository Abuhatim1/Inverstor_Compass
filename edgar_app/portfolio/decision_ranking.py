"""
portfolio/decision_ranking.py
-----------------------------
Portfolio Decision Ranking Engine.

This is **NOT a trading signal engine**. It is an *attention allocation*
engine for the portfolio manager: which of my holdings should I look at
*today*, and why?

For every Actual Holding, the engine fuses 10 signals into a single
**Priority Score (0-100)**, an **Action Urgency** band, and a
**Suggested Action**:

  · Action Urgency:    Monitor | Review | High Attention | Immediate Review
  · Suggested Action:  Increase | Hold | Reduce | Exit Watch
  · Key Reason:        one-line summary of the top drivers

The 10 attention signals (each scored 0-100 where higher = more attention
needed) are joined from:

   1. Position size / weight              — Holdings (market value share)
   2. Thesis strength                     — Research Watchlist
   3. Damodaran valuation attractiveness  — Research Watchlist
   4. Market-intel alignment / divergence — Market Intel state
   5. Risk deterioration signals          — Delta history (alerts)
   6. Filing deterioration signals        — Comparison history (trends)
   7. Management tone                     — Comparison history
   8. Balance sheet risk                  — Comparison history (debt trend)
   9. Market sentiment extremes           — Market Intel state (dominant view)
  10. Confidence level of analysis        — Research Watchlist (uncertainty)
"""

from dataclasses import dataclass, field
from datetime import datetime

from .delta import (
    ALERT_RISING_RISK,
    ALERT_THESIS_WEAKENED,
    DeltaRecord,
)
from .comparison_store import ComparisonRecord
from .holdings import Holding, portfolio_weights


# ── Taxonomy ──────────────────────────────────────────────────────────────────

URGENCY_BANDS: list[tuple[int, str]] = [
    (75, "Immediate Review"),
    (50, "High Attention"),
    (30, "Review"),
    (0,  "Monitor"),
]

URGENCY_BADGE: dict[str, tuple[str, str]] = {
    "Monitor":          ("🟢", "Monitor"),
    "Review":           ("🟡", "Review"),
    "High Attention":   ("🟠", "High Attention"),
    "Immediate Review": ("🔴", "Immediate Review"),
}

ACTION_BADGE: dict[str, tuple[str, str]] = {
    "Increase":   ("📈", "Increase"),
    "Hold":       ("⏸️", "Hold"),
    "Reduce":     ("📉", "Reduce"),
    "Exit Watch": ("🚪", "Exit Watch"),
}

SIGNAL_NAMES: dict[str, str] = {
    "core_thesis_status":     "Core Thesis Status",
    "position_size":          "Position Size",
    "thesis_strength":        "Filing Thesis Strength",
    "valuation":              "Valuation Attractiveness",
    "market_divergence":      "Market Intel Divergence",
    "risk_deterioration":     "Risk Deterioration",
    "filing_deterioration":   "Filing Deterioration",
    "tone":                   "Management Tone",
    "balance_sheet":          "Balance Sheet Risk",
    "sentiment_extremes":     "Market Sentiment Extremes",
    "confidence":             "Analysis Confidence",
}

# Core thesis status is the heaviest signal — it represents the PM's
# original intent, against which everything else is measured.
_SIGNAL_WEIGHTS: dict[str, float] = {
    "core_thesis_status":     2.0,
    "position_size":          1.5,
    "thesis_strength":        1.5,
    "valuation":              1.0,
    "market_divergence":      1.0,
    "risk_deterioration":     1.5,
    "filing_deterioration":   1.2,
    "tone":                   0.8,
    "balance_sheet":          1.2,
    "sentiment_extremes":     0.7,
    "confidence":             0.8,
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class DecisionSignal:
    key:    str
    name:   str
    score:  int          # 0-100; higher = more attention
    weight: float
    detail: str


@dataclass
class HoldingDecision:
    ticker:           str
    company_name:     str
    weight_pct:       float
    market_value:     float
    priority_score:   int            # 0-100
    urgency:          str            # Monitor | Review | High Attention | Immediate Review
    suggested_action: str            # Increase | Hold | Reduce | Exit Watch
    key_reason:       str            # one-line summary
    signals:          list[DecisionSignal] = field(default_factory=list)
    computed_at:      str = ""


@dataclass
class DecisionQueueResult:
    decisions:           list[HoldingDecision]   # sorted by priority desc
    total_immediate:     int
    total_high_attention: int
    total_review:        int
    total_monitor:       int
    computed_at:         str


# ── Individual signal scorers ─────────────────────────────────────────────────

def _sig_position_size(weight_pct: float) -> tuple[int, str]:
    """Amplifier — a tiny position with problems matters less than a big one."""
    score = min(100, int(weight_pct * 4))   # 25% → 100
    return score, f"Position weight: {weight_pct:.1f}% of portfolio"


def _sig_thesis_strength(entry) -> tuple[int, str]:
    if entry is None:
        return 50, "No research yet — analyse a filing to set thesis"
    t = getattr(entry, "thesis_status", "Unknown")
    mapping = {"Strong": 5, "Solid": 15, "Mixed": 45, "Weak": 80, "Broken": 100}
    score = mapping.get(t, 40)
    conviction = int(getattr(entry, "conviction_score", 0) or 0)
    return score, f"Thesis: {t} · conviction {conviction}/100"


def _sig_valuation(entry) -> tuple[int, str]:
    if entry is None:
        return 30, "No Damodaran valuation"
    p = int(getattr(entry, "priority_score", 0) or 0)
    if p <= 0:
        return 30, "No Damodaran valuation"
    # Extreme in either direction → attention. p=50 is fair value (no attention).
    score = min(100, int(abs(p - 50) * 1.8))
    direction = ("very attractive" if p >= 70
                 else "potentially overvalued" if p <= 30
                 else "near fair value")
    return score, f"Valuation priority {p}/100 ({direction})"


def _sig_market_divergence(mi: dict | None) -> tuple[int, str]:
    if not mi:
        return 30, "No external market intel yet"
    a = int(mi.get("alignment_score", -1))
    if a < 0:
        return 30, "No external market intel yet"
    score = max(0, min(100, 100 - a))
    label = mi.get("alignment_label", "—")
    return score, f"Market alignment {a}/100 ({label})"


def _sig_risk_deterioration(ticker: str, deltas: list[DeltaRecord]) -> tuple[int, str]:
    recent = [d for d in deltas if d.ticker == ticker][-5:]
    if not recent:
        return 20, "No filing-delta history yet"
    bad = 0
    for d in recent:
        alerts = getattr(d, "alerts", []) or []
        if ALERT_RISING_RISK in alerts or ALERT_THESIS_WEAKENED in alerts:
            bad += 1
        if getattr(d, "risk_trend", "") == "more":
            bad += 1
        if getattr(d, "conviction_delta", 0) <= -10:
            bad += 1
    score = min(100, bad * 25)
    return score, (f"{bad} deterioration alert(s) in last {len(recent)} filing(s)"
                   if bad else "No recent deterioration alerts")


def _sig_filing_deterioration(ticker: str, comps: list[ComparisonRecord]) -> tuple[int, str]:
    recent = [c for c in comps if c.ticker == ticker][-3:]
    if not recent:
        return 20, "No filing comparisons yet"
    bad = 0
    fields = []
    for c in recent:
        for fname, fval in (
            ("Revenue",  getattr(c, "revenue_growth_trend", "")),
            ("Margins",  getattr(c, "margin_trend", "")),
            ("Cash",     getattr(c, "cash_trend", "")),
            ("Guidance", getattr(c, "guidance_trend", "")),
        ):
            if fval in ("declining", "lowered", "withdrawn"):
                bad += 1
                fields.append(fname)
    score = min(100, bad * 18)
    if bad:
        uniq = sorted(set(fields))
        return score, f"{bad} declining trend(s) across {len(recent)} filing(s): {', '.join(uniq[:3])}"
    return score, "No fundamental deterioration in recent filings"


def _sig_tone(ticker: str, comps: list[ComparisonRecord]) -> tuple[int, str]:
    recent = [c for c in comps if c.ticker == ticker]
    if not recent:
        return 20, "No management tone history"
    latest = recent[-1]
    tone = getattr(latest, "management_tone", "")
    mapping = {"positive": 10, "neutral": 25, "cautious": 60, "negative": 90}
    score = mapping.get(tone, 30)
    return score, f"Latest management tone: {tone or 'unknown'}"


def _sig_balance_sheet(ticker: str, comps: list[ComparisonRecord]) -> tuple[int, str]:
    recent = [c for c in comps if c.ticker == ticker][-3:]
    if not recent:
        return 20, "No balance sheet history"
    # "declining" debt_trend = balance sheet deteriorating (debt rising)
    bad = sum(1 for c in recent if getattr(c, "debt_trend", "") == "declining")
    score = min(100, bad * 35)
    if bad:
        return score, f"Balance sheet deteriorating in {bad} of {len(recent)} recent filing(s)"
    return score, "Balance sheet stable / improving"


def _sig_sentiment_extremes(mi: dict | None) -> tuple[int, str]:
    if not mi:
        return 25, "No external sentiment data"
    view = mi.get("dominant_view", "") or ""
    mispricing = mi.get("mispricing", "") or ""
    if view in ("Bullish", "Bearish"):
        base = 70
        if mispricing and "overly" in mispricing.lower():
            base = 85   # market overly bullish/bearish vs thesis
        return base, f"Market view: {view}" + (f" · {mispricing}" if mispricing else "")
    if view == "Mixed":
        return 35, "External market view: Mixed (divided opinion)"
    return 25, f"External market view: {view or 'Neutral'}"


def _sig_core_thesis_status(core_thesis) -> tuple[int, str]:
    """Heaviest signal — original PM intent vs current reality."""
    if core_thesis is None:
        return 35, "No core thesis recorded (author one in 📜 Thesis Memory)"
    mapping = {
        "Strengthening": 5,
        "Stable":        30,
        "Weakening":     80,
        "Broken":        100,
    }
    base = mapping.get(getattr(core_thesis, "thesis_status", "Stable"), 35)
    if getattr(core_thesis, "drift_detected", False):
        boosted = min(100, base + 15)
        return boosted, (f"Core thesis: {core_thesis.thesis_status} · "
                         f"⚠️ DRIFT DETECTED")
    return base, f"Core thesis: {core_thesis.thesis_status}"


def _sig_confidence(entry) -> tuple[int, str]:
    if entry is None:
        return 60, "No analysis — confidence unknown"
    u = getattr(entry, "uncertainty_level", "Unknown")
    mapping = {
        "High Confidence":   10,
        "Medium Confidence": 30,
        "Low Confidence":    70,
        "Speculative":       95,
    }
    score = mapping.get(u, 40)
    return score, f"Analysis confidence: {u}"


# ── Suggested action policy ───────────────────────────────────────────────────

def _suggest_action(
    entry,                  # PortfolioEntry | None
    core_thesis,            # CoreThesis | None
    weight_pct: float,
    sigs: dict[str, DecisionSignal],
) -> str:
    thesis = getattr(entry, "thesis_status", "Unknown") if entry else "Unknown"
    val_priority = int(getattr(entry, "priority_score", 0) or 0) if entry else 0
    confidence = sigs["confidence"].score   # lower = more confident
    core_status = getattr(core_thesis, "thesis_status", "") if core_thesis else ""

    # Core thesis overrides — PM intent takes precedence over filing-level reads
    if core_status == "Broken" and weight_pct >= 1.0:
        return "Exit Watch"
    if core_status == "Weakening" and weight_pct >= 5.0:
        return "Reduce"

    # Exit Watch — broken filing thesis on a real position
    if thesis == "Broken" and weight_pct >= 1.0:
        return "Exit Watch"

    # Reduce — weak thesis on a material position OR severe deterioration OR
    # significantly overvalued (Damodaran priority ≤ 25) on a material position
    if thesis == "Weak" and weight_pct >= 3.0:
        return "Reduce"
    if sigs["risk_deterioration"].score >= 70 and weight_pct >= 5.0:
        return "Reduce"
    if sigs["filing_deterioration"].score >= 60 and weight_pct >= 5.0:
        return "Reduce"
    if sigs["balance_sheet"].score >= 70 and weight_pct >= 5.0:
        return "Reduce"
    if 0 < val_priority <= 25 and weight_pct >= 5.0:
        return "Reduce"

    # Increase — strong/solid filing thesis + very attractive valuation +
    # high confidence + undersized position. Never increase when core thesis
    # is degrading (Weakening/Broken handled above; also block on drift).
    drift = bool(getattr(core_thesis, "drift_detected", False))
    if (thesis in ("Strong", "Solid", "Stable")
            and core_status in ("", "Strengthening", "Stable")
            and not drift
            and val_priority >= 75
            and confidence <= 30
            and weight_pct < 10.0
            and sigs["risk_deterioration"].score < 40
            and sigs["filing_deterioration"].score < 40):
        return "Increase"

    return "Hold"


# ── Urgency band ──────────────────────────────────────────────────────────────

def _urgency_band(score: int) -> str:
    for threshold, label in URGENCY_BANDS:
        if score >= threshold:
            return label
    return "Monitor"


# ── Engine ────────────────────────────────────────────────────────────────────

def compute_holding_decision(
    holding:            Holding,
    weight_pct:         float,
    watchlist_entry,                                  # PortfolioEntry | None
    market_intel:       dict | None,
    delta_history:      list[DeltaRecord],
    comparison_history: list[ComparisonRecord],
    core_thesis=None,                                 # CoreThesis | None
) -> HoldingDecision:
    """Score one holding across all 11 signals."""
    ticker = holding.ticker

    raw_signals: dict[str, tuple[int, str]] = {
        "core_thesis_status":   _sig_core_thesis_status(core_thesis),
        "position_size":        _sig_position_size(weight_pct),
        "thesis_strength":      _sig_thesis_strength(watchlist_entry),
        "valuation":            _sig_valuation(watchlist_entry),
        "market_divergence":    _sig_market_divergence(market_intel),
        "risk_deterioration":   _sig_risk_deterioration(ticker, delta_history),
        "filing_deterioration": _sig_filing_deterioration(ticker, comparison_history),
        "tone":                 _sig_tone(ticker, comparison_history),
        "balance_sheet":        _sig_balance_sheet(ticker, comparison_history),
        "sentiment_extremes":   _sig_sentiment_extremes(market_intel),
        "confidence":           _sig_confidence(watchlist_entry),
    }

    signals: list[DecisionSignal] = []
    sigs_by_key: dict[str, DecisionSignal] = {}
    for key, (score, detail) in raw_signals.items():
        sig = DecisionSignal(
            key=key,
            name=SIGNAL_NAMES[key],
            score=int(score),
            weight=_SIGNAL_WEIGHTS[key],
            detail=detail,
        )
        signals.append(sig)
        sigs_by_key[key] = sig

    total_w = sum(s.weight for s in signals)
    priority_score = int(round(sum(s.score * s.weight for s in signals) / total_w))

    urgency = _urgency_band(priority_score)
    suggested = _suggest_action(watchlist_entry, core_thesis, weight_pct, sigs_by_key)

    # Build key-reason from the top 2 contributing signals (signal_score * weight)
    contribs = sorted(signals, key=lambda s: -(s.score * s.weight))
    top = [s for s in contribs if s.score >= 40][:2]
    if not top:
        key_reason = "Stable across all attention signals — routine monitoring."
    else:
        key_reason = " · ".join(s.detail for s in top)

    return HoldingDecision(
        ticker=ticker,
        company_name=holding.company_name,
        weight_pct=weight_pct,
        market_value=holding.market_value,
        priority_score=priority_score,
        urgency=urgency,
        suggested_action=suggested,
        key_reason=key_reason,
        signals=signals,
        computed_at=datetime.now().isoformat(),
    )


def compute_decision_queue(
    holdings:           dict[str, Holding],
    watchlist:          dict,                          # {ticker: PortfolioEntry}
    market_intel_state: dict[str, dict],
    delta_history:      list[DeltaRecord],
    comparison_history: list[ComparisonRecord],
    core_theses:        dict | None = None,            # {ticker: CoreThesis}
) -> DecisionQueueResult:
    """Score every holding and rank them by attention priority (desc)."""
    if not holdings:
        return DecisionQueueResult(
            decisions=[],
            total_immediate=0, total_high_attention=0,
            total_review=0, total_monitor=0,
            computed_at=datetime.now().isoformat(),
        )

    core_theses = core_theses or {}
    weights = portfolio_weights(holdings)
    decisions: list[HoldingDecision] = []
    for ticker, h in holdings.items():
        d = compute_holding_decision(
            holding=h,
            weight_pct=weights.get(ticker, 0.0),
            watchlist_entry=watchlist.get(ticker),
            market_intel=market_intel_state.get(ticker),
            delta_history=delta_history,
            comparison_history=comparison_history,
            core_thesis=core_theses.get(ticker),
        )
        decisions.append(d)

    decisions.sort(key=lambda d: (-d.priority_score, -d.weight_pct))

    return DecisionQueueResult(
        decisions=decisions,
        total_immediate     =sum(1 for d in decisions if d.urgency == "Immediate Review"),
        total_high_attention=sum(1 for d in decisions if d.urgency == "High Attention"),
        total_review        =sum(1 for d in decisions if d.urgency == "Review"),
        total_monitor       =sum(1 for d in decisions if d.urgency == "Monitor"),
        computed_at=datetime.now().isoformat(),
    )
