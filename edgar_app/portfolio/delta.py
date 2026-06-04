"""
portfolio/delta.py
------------------
Delta Intelligence Engine.

Compares a previous PortfolioEntry against a new AnalysisResult and
produces a DeltaRecord describing exactly what changed, with alert flags
for adverse moves (thesis weakening, rising risk, action downgrades).

Change history is stored in:
  edgar_app/portfolio/delta_history.json   (list, newest first, max 100)
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime

_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "delta_history.json")
_MAX_HISTORY  = 100

# ── Ordinal rankings (lower = worse) ─────────────────────────────────────────
_THESIS_RANK = {"Strong": 3, "Stable": 2, "Weak": 1, "Broken": 0}
_ACTION_RANK = {"Buy": 3, "Hold": 2, "Reduce": 1, "Exit": 0}


# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class DeltaRecord:
    ticker:           str
    company_name:     str
    filing_type:      str
    timestamp:        str           # ISO datetime  e.g. "2026-05-28T09:15:00"

    # Thesis
    thesis_prev:      str
    thesis_new:       str
    thesis_changed:   bool

    # Recommended action
    action_prev:      str
    action_new:       str
    action_changed:   bool

    # Conviction
    conviction_prev:  int
    conviction_new:   int
    conviction_delta: int           # positive = improved, negative = declined

    # Catalyst / risk trends (based on list-count comparison)
    catalyst_trend:   str           # "more" | "fewer" | "same"
    risk_trend:       str           # "more" | "fewer" | "same"

    # Human-readable change lines, e.g. ["Thesis improved: Stable → Strong"]
    what_changed:     list[str]

    # Alert tags for highlighting (see _ALERT_* constants below)
    alerts:           list[str]

    # True when there was no previous state to compare against
    is_first_analysis: bool


# Alert tag constants — used both here and in app.py for rendering
ALERT_THESIS_WEAKENED   = "thesis_weakened"
ALERT_THESIS_IMPROVED   = "thesis_improved"
ALERT_RISING_RISK       = "rising_risk"
ALERT_FALLING_RISK      = "falling_risk"
ALERT_ACTION_DOWNGRADED = "action_downgraded"
ALERT_ACTION_UPGRADED   = "action_upgraded"
ALERT_CONVICTION_DROPPED   = "conviction_dropped"
ALERT_CONVICTION_IMPROVED  = "conviction_improved"


# ── Core detection logic ──────────────────────────────────────────────────────

def detect_delta(
    previous,       # PortfolioEntry | None
    analysis,       # AnalysisResult  — typed loosely to avoid circular import
    ticker:        str,
    company_name:  str,
    filing_type:   str,
) -> DeltaRecord:
    """
    Compare previous portfolio state against a new AnalysisResult.
    Returns a DeltaRecord (not yet saved — call save_delta to persist it).
    """
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # ── First analysis — no comparison possible ───────────────────────────────
    if previous is None:
        return DeltaRecord(
            ticker=ticker.upper(),
            company_name=company_name,
            filing_type=filing_type,
            timestamp=now,
            thesis_prev="—",
            thesis_new=analysis.thesis_impact,
            thesis_changed=False,
            action_prev="—",
            action_new=analysis.suggested_action,
            action_changed=False,
            conviction_prev=0,
            conviction_new=analysis.confidence_score,
            conviction_delta=0,
            catalyst_trend="same",
            risk_trend="same",
            what_changed=[f"First analysis recorded for {ticker.upper()}."],
            alerts=[],
            is_first_analysis=True,
        )

    # ── Field-by-field comparison ─────────────────────────────────────────────
    changes: list[str] = []
    alerts:  list[str] = []

    # Thesis
    t_prev = previous.thesis_status
    t_new  = analysis.thesis_impact
    t_changed = t_prev != t_new
    if t_changed:
        direction = "improved" if _THESIS_RANK.get(t_new, 0) > _THESIS_RANK.get(t_prev, 0) else "weakened"
        changes.append(f"Thesis {direction}: {t_prev} → {t_new}")
        if direction == "weakened":
            alerts.append(ALERT_THESIS_WEAKENED)
        else:
            alerts.append(ALERT_THESIS_IMPROVED)

    # Action
    a_prev    = previous.recommended_action
    a_new     = analysis.suggested_action
    a_changed = a_prev != a_new
    if a_changed:
        direction = "upgraded" if _ACTION_RANK.get(a_new, 0) > _ACTION_RANK.get(a_prev, 0) else "downgraded"
        changes.append(f"Action {direction}: {a_prev} → {a_new}")
        if direction == "downgraded":
            alerts.append(ALERT_ACTION_DOWNGRADED)
        else:
            alerts.append(ALERT_ACTION_UPGRADED)

    # Conviction
    c_prev  = previous.conviction_score
    c_new   = analysis.confidence_score
    c_delta = c_new - c_prev
    if abs(c_delta) >= 5:
        sign = "+" if c_delta > 0 else ""
        changes.append(f"Conviction score: {c_prev} → {c_new} ({sign}{c_delta})")
        if c_delta <= -10:
            alerts.append(ALERT_CONVICTION_DROPPED)
        elif c_delta >= 10:
            alerts.append(ALERT_CONVICTION_IMPROVED)

    # Catalyst trend (count-based)
    cat_prev  = len(previous.catalysts)
    cat_new   = len(analysis.key_catalysts)
    cat_trend = "more" if cat_new > cat_prev else ("fewer" if cat_new < cat_prev else "same")
    if cat_trend != "same":
        word = "added" if cat_trend == "more" else "removed"
        diff = abs(cat_new - cat_prev)
        changes.append(f"Catalysts: {diff} {word} (now {cat_new})")

    # Risk trend (count-based)
    risk_prev  = len(previous.risks)
    risk_new   = len(analysis.key_risks)
    risk_trend = "more" if risk_new > risk_prev else ("fewer" if risk_new < risk_prev else "same")
    if risk_trend != "same":
        word = "added" if risk_trend == "more" else "removed"
        diff = abs(risk_new - risk_prev)
        changes.append(f"Risks: {diff} {word} (now {risk_new})")
        if risk_trend == "more":
            alerts.append(ALERT_RISING_RISK)
        else:
            alerts.append(ALERT_FALLING_RISK)

    if not changes:
        changes.append("No significant changes detected from previous analysis.")

    return DeltaRecord(
        ticker=ticker.upper(),
        company_name=company_name,
        filing_type=filing_type,
        timestamp=now,
        thesis_prev=t_prev,
        thesis_new=t_new,
        thesis_changed=t_changed,
        action_prev=a_prev,
        action_new=a_new,
        action_changed=a_changed,
        conviction_prev=c_prev,
        conviction_new=c_new,
        conviction_delta=c_delta,
        catalyst_trend=cat_trend,
        risk_trend=risk_trend,
        what_changed=changes,
        alerts=alerts,
        is_first_analysis=False,
    )


# ── History file I/O ──────────────────────────────────────────────────────────

def load_delta_history() -> list[DeltaRecord]:
    """Load all delta records from disk, newest first. Returns [] if no file."""
    if not os.path.exists(_HISTORY_FILE):
        return []
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [DeltaRecord(**r) for r in raw]
    except (json.JSONDecodeError, OSError, TypeError):
        return []


def save_delta(record: DeltaRecord) -> None:
    """Prepend a new record to the history file, capped at _MAX_HISTORY."""
    history = load_delta_history()
    history.insert(0, record)          # newest first
    history = history[:_MAX_HISTORY]   # cap size
    os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in history], f, indent=2, ensure_ascii=False)
