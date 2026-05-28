"""
portfolio/risk.py
-----------------
Portfolio Risk Engine.

Combines existing intelligence layers (thesis status, conviction, Damodaran
valuation, explainability uncertainty, external market intelligence) with
user-supplied portfolio metadata (weight, sector, market) to compute a
holistic INVESTMENT risk score for the whole portfolio.

This is NOT a price-volatility engine. Risk here means:
  · Concentration (single position too large)
  · Sector concentration
  · Country / market exposure
  · Valuation fragility (low priority score)
  · Thesis deterioration (Weak / Broken status)
  · External market disagreement (low alignment score)
  · High-uncertainty exposure (Low / Speculative confidence)

Persistence is in two small JSON files alongside `portfolio_state.json`:
  · `position_metadata.json`   — per-ticker weight, sector, market
  · `market_intel_state.json`  — per-ticker latest alignment score + label

Missing data never crashes the engine. Each risk category degrades to
"Unknown" with a 0 score when its inputs are absent.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime


# ── Storage locations ─────────────────────────────────────────────────────────

_DIR                  = os.path.dirname(__file__)
_POSITION_META_FILE   = os.path.join(_DIR, "position_metadata.json")
_MARKET_INTEL_FILE    = os.path.join(_DIR, "market_intel_state.json")


# ── Taxonomy ──────────────────────────────────────────────────────────────────

MARKETS: list[str] = ["US", "Saudi", "Other"]

DEFAULT_SECTORS: list[str] = [
    "Technology",
    "Healthcare",
    "Financial Services",
    "Industrials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Materials",
    "Utilities",
    "Real Estate",
    "Communication Services",
    "Other",
]

RISK_REGIME_BADGE: dict[str, tuple[str, str]] = {
    "Low":      ("🟢", "Low"),
    "Medium":   ("🟡", "Medium"),
    "High":     ("🟠", "High"),
    "Critical": ("🔴", "Critical"),
}

RISK_CATEGORIES: dict[str, str] = {
    "concentration":        "Concentration Risk",
    "sector_concentration": "Sector Concentration",
    "market_exposure":      "Market / Country Exposure",
    "valuation_fragility":  "Valuation Fragility",
    "thesis_deterioration": "Thesis Deterioration",
    "market_disagreement":  "External Market Disagreement",
    "uncertainty_exposure": "High-Uncertainty Exposure",
}

# Relative weighting of each category in the final portfolio score
_CATEGORY_WEIGHTS: dict[str, float] = {
    "concentration":        1.5,
    "sector_concentration": 1.0,
    "market_exposure":      0.8,
    "valuation_fragility":  1.0,
    "thesis_deterioration": 1.5,
    "market_disagreement":  0.7,
    "uncertainty_exposure": 1.0,
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class PositionMetadata:
    """User-supplied position metadata (weight, sector, market)."""
    ticker:     str
    market:     str = "US"        # "US" | "Saudi" | "Other"
    sector:     str = "Other"
    weight_pct: float = 0.0       # 0-100


@dataclass
class PortfolioPosition:
    """One portfolio position — joins state + metadata + intelligence signals."""
    # Identity
    ticker:                 str
    company_name:           str
    # User-supplied metadata
    market:                 str
    sector:                 str
    weight_pct:             float
    # State from PortfolioEntry
    thesis_status:          str             # "Strong" | "Stable" | "Weak" | "Broken" | "Unknown"
    conviction_score:       int             # 0-100
    recommended_action:     str             # "Buy" | "Hold" | "Reduce" | "Exit" | "Unknown"
    # Intelligence-layer signals (optional, populated when available)
    valuation_impact:       str = "Unknown" # "Value Accretive" | "Neutral" | "Value Destructive" | "Unknown"
    priority_score:         int = 0         # 0-100 from Damodaran engine (0 = no data)
    uncertainty_level:      str = "Unknown" # "High Confidence" | ... | "Speculative" | "Unknown"
    market_alignment_score: int = -1        # 0-100 from market intel (-1 = no data)
    market_alignment_label: str = "No Baseline"


@dataclass
class RiskCategoryScore:
    """One category of the portfolio risk breakdown."""
    key:          str
    name:         str
    score:        int           # 0-100
    detail:       str           # human-readable summary
    contributors: list[str] = field(default_factory=list)  # ticker-level notes


@dataclass
class PortfolioRiskResult:
    """Result of compute_portfolio_risk()."""
    risk_score:        int                  # 0-100
    risk_regime:       str                  # Low | Medium | High | Critical
    total_weight:      float                # sum of weight_pct
    n_positions:       int
    categories:        list[RiskCategoryScore]
    top_risks:         list[str]
    required_actions:  list[str]
    computed_at:       str                  # ISO timestamp


# ── Position metadata persistence ─────────────────────────────────────────────

def load_position_metadata() -> dict[str, PositionMetadata]:
    """Load position metadata; return empty dict on missing or corrupt file."""
    if not os.path.exists(_POSITION_META_FILE):
        return {}
    try:
        with open(_POSITION_META_FILE, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, PositionMetadata] = {}
    for ticker, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            out[ticker] = PositionMetadata(
                ticker=ticker,
                market=entry.get("market", "US"),
                sector=entry.get("sector", "Other"),
                weight_pct=float(entry.get("weight_pct", 0.0)),
            )
        except Exception:
            continue
    return out


def save_position_metadata(meta: dict[str, PositionMetadata]) -> None:
    """Persist position metadata to disk."""
    os.makedirs(_DIR, exist_ok=True)
    with open(_POSITION_META_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {t: asdict(p) for t, p in meta.items()},
            f, indent=2, ensure_ascii=False,
        )


def upsert_position_metadata(
    ticker: str,
    market: str | None = None,
    sector: str | None = None,
    weight_pct: float | None = None,
) -> PositionMetadata:
    """Insert or update one position's metadata."""
    meta = load_position_metadata()
    existing = meta.get(ticker)
    new_entry = PositionMetadata(
        ticker=ticker,
        market=market     if market     is not None else (existing.market     if existing else "US"),
        sector=sector     if sector     is not None else (existing.sector     if existing else "Other"),
        weight_pct=weight_pct if weight_pct is not None else (existing.weight_pct if existing else 0.0),
    )
    meta[ticker] = new_entry
    save_position_metadata(meta)
    return new_entry


def delete_position_metadata(ticker: str) -> bool:
    """Remove one position's metadata."""
    meta = load_position_metadata()
    if ticker in meta:
        del meta[ticker]
        save_position_metadata(meta)
        return True
    return False


# ── Market intel state persistence ────────────────────────────────────────────

def load_market_intel_state() -> dict[str, dict]:
    """Load latest market-intel alignment per ticker."""
    if not os.path.exists(_MARKET_INTEL_FILE):
        return {}
    try:
        with open(_MARKET_INTEL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_market_intel_for_ticker(
    ticker: str,
    alignment_score: int,
    alignment_label: str,
) -> None:
    """Record the latest market-intel alignment score for one ticker."""
    state = load_market_intel_state()
    state[ticker] = {
        "alignment_score": int(alignment_score),
        "alignment_label": alignment_label,
        "updated_at":      datetime.now().isoformat(),
    }
    os.makedirs(_DIR, exist_ok=True)
    with open(_MARKET_INTEL_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── Position assembly ─────────────────────────────────────────────────────────

def build_positions(
    portfolio:          dict,            # {ticker: PortfolioEntry}
    position_metadata:  dict[str, PositionMetadata] | None = None,
    market_intel_state: dict[str, dict]  | None = None,
) -> list[PortfolioPosition]:
    """
    Join portfolio state + position metadata + market intel state into a
    unified list of PortfolioPosition objects. All field reads use safe
    fallbacks so missing data shows as 'Unknown' / 0 / -1 without crashing.
    """
    meta = position_metadata if position_metadata is not None else load_position_metadata()
    mi   = market_intel_state if market_intel_state is not None else load_market_intel_state()

    positions: list[PortfolioPosition] = []
    for ticker, entry in portfolio.items():
        m = meta.get(ticker)
        mi_entry = mi.get(ticker, {})

        positions.append(PortfolioPosition(
            ticker=ticker,
            company_name=getattr(entry, "company_name", "Unknown"),
            market=(m.market if m else "US"),
            sector=(m.sector if m else "Other"),
            weight_pct=(m.weight_pct if m else 0.0),
            thesis_status=getattr(entry, "thesis_status",
                                  getattr(entry, "thesis_impact", "Unknown")),
            conviction_score=int(getattr(entry, "conviction_score",
                                         getattr(entry, "confidence_score", 0)) or 0),
            recommended_action=getattr(entry, "recommended_action",
                                       getattr(entry, "suggested_action", "Unknown")),
            valuation_impact=getattr(entry, "valuation_impact", "Unknown"),
            priority_score=int(getattr(entry, "priority_score", 0) or 0),
            uncertainty_level=getattr(entry, "uncertainty_level", "Unknown"),
            market_alignment_score=int(mi_entry.get("alignment_score", -1)),
            market_alignment_label=mi_entry.get("alignment_label", "No Baseline"),
        ))
    return positions


# ── Risk engine ───────────────────────────────────────────────────────────────

def _regime_from_score(score: int) -> str:
    if score < 25:
        return "Low"
    if score < 50:
        return "Medium"
    if score < 75:
        return "High"
    return "Critical"


def _empty_result() -> PortfolioRiskResult:
    return PortfolioRiskResult(
        risk_score=0,
        risk_regime="Low",
        total_weight=0.0,
        n_positions=0,
        categories=[],
        top_risks=["No portfolio positions yet — add tickers and weights to compute risk."],
        required_actions=["Open the Portfolio Risk tab and enter weight, sector, and market for each ticker."],
        computed_at=datetime.now().isoformat(),
    )


def compute_portfolio_risk(positions: list[PortfolioPosition]) -> PortfolioRiskResult:
    """
    Compute the full portfolio-level risk picture from a list of positions.

    Score is a weighted average of 7 category scores. Each category is
    independently computed and returns 0 when its inputs are missing
    (rather than penalising the user for not having data yet).
    """
    if not positions:
        return _empty_result()

    total_weight = sum(p.weight_pct for p in positions)
    if total_weight <= 0:
        # Positions exist but no weights assigned — score nothing
        empty = _empty_result()
        empty.n_positions = len(positions)
        empty.top_risks = ["Positions added but no weights assigned — risk cannot be computed."]
        empty.required_actions = ["Assign a non-zero weight % to at least one position."]
        return empty

    # ── 1. Concentration risk (HHI) ───────────────────────────────────────────
    norm = [(p.weight_pct / total_weight) * 100 for p in positions]
    hhi = sum(w * w for w in norm)  # 0–10000 range
    concentration_score = min(100, int(hhi / 50))
    largest = max(positions, key=lambda p: p.weight_pct)
    concentration_detail = (
        f"Largest position: {largest.ticker} at "
        f"{(largest.weight_pct / total_weight * 100):.1f}% of portfolio weight."
    )
    sorted_positions = sorted(positions, key=lambda p: -p.weight_pct)
    concentration_contribs = [
        f"{p.ticker}: {(p.weight_pct / total_weight * 100):.1f}%"
        for p in sorted_positions[:3]
    ]

    # ── 2. Sector concentration ───────────────────────────────────────────────
    sector_weights: dict[str, float] = {}
    for p in positions:
        sector_weights[p.sector] = sector_weights.get(p.sector, 0.0) + p.weight_pct
    max_sector_pct = (max(sector_weights.values()) / total_weight * 100) if sector_weights else 0.0
    sector_score = min(100, int(max_sector_pct * 1.5))
    top_sector = max(sector_weights, key=sector_weights.get) if sector_weights else "—"
    sector_detail = f"Top sector: {top_sector} ({max_sector_pct:.1f}% of portfolio weight)."
    sector_contribs = [
        f"{s}: {(w / total_weight * 100):.1f}%"
        for s, w in sorted(sector_weights.items(), key=lambda x: -x[1])[:3]
    ]

    # ── 3. Market / country exposure ──────────────────────────────────────────
    market_weights: dict[str, float] = {}
    for p in positions:
        market_weights[p.market] = market_weights.get(p.market, 0.0) + p.weight_pct
    max_market_pct = (max(market_weights.values()) / total_weight * 100) if market_weights else 0.0
    # Score rises only above 50% single-market exposure
    market_score = max(0, min(100, int((max_market_pct - 50) * 2)))
    top_market = max(market_weights, key=market_weights.get) if market_weights else "—"
    market_detail = f"Top market: {top_market} ({max_market_pct:.1f}% of portfolio weight)."
    market_contribs = [
        f"{m}: {(w / total_weight * 100):.1f}%"
        for m, w in sorted(market_weights.items(), key=lambda x: -x[1])
    ]

    # ── 4. Valuation fragility ────────────────────────────────────────────────
    val_data = [(p.weight_pct, 100 - p.priority_score) for p in positions if p.priority_score > 0]
    if val_data:
        tw = sum(w for w, _ in val_data) or 1.0
        valuation_score = int(sum(w * f for w, f in val_data) / tw)
        valuation_detail = (
            f"Weighted-avg fragility across {len(val_data)} of {len(positions)} positions "
            "(higher = weaker valuation conviction)."
        )
        valuation_contribs = [
            f"{p.ticker}: priority {p.priority_score}/100, impact {p.valuation_impact}"
            for p in sorted(positions, key=lambda x: x.priority_score)
            if p.priority_score > 0
        ][:3]
    else:
        valuation_score = 0
        valuation_detail = "Unknown — no Damodaran valuation data for any position yet."
        valuation_contribs = []

    # ── 5. Thesis deterioration ───────────────────────────────────────────────
    deteriorated_positions = [
        p for p in positions if p.thesis_status in ("Weak", "Broken")
    ]
    deteriorated_weight = sum(p.weight_pct for p in deteriorated_positions)
    deteriorated_pct = deteriorated_weight / total_weight * 100
    thesis_score = min(100, int(deteriorated_pct * 2))
    thesis_detail = (
        f"{len(deteriorated_positions)} of {len(positions)} positions in "
        f"Weak/Broken status — {deteriorated_pct:.1f}% of portfolio weight."
    )
    thesis_contribs = [
        f"{p.ticker}: {p.thesis_status} · action: {p.recommended_action}"
        for p in deteriorated_positions[:3]
    ]

    # ── 6. External market disagreement ───────────────────────────────────────
    disagree_data = [
        (p.weight_pct, 100 - p.market_alignment_score)
        for p in positions if p.market_alignment_score >= 0
    ]
    if disagree_data:
        tw = sum(w for w, _ in disagree_data) or 1.0
        disagreement_score = int(sum(w * d for w, d in disagree_data) / tw)
        disagreement_detail = (
            f"Weighted-avg market-vs-thesis disagreement across "
            f"{len(disagree_data)} of {len(positions)} positions with market intel."
        )
        disagreement_contribs = [
            f"{p.ticker}: alignment {p.market_alignment_score}/100 ({p.market_alignment_label})"
            for p in sorted(positions, key=lambda x: x.market_alignment_score)
            if p.market_alignment_score >= 0
        ][:3]
    else:
        disagreement_score = 0
        disagreement_detail = "Unknown — no external market intelligence run for any position."
        disagreement_contribs = []

    # ── 7. High-uncertainty exposure ──────────────────────────────────────────
    high_unc_positions = [
        p for p in positions
        if p.uncertainty_level in ("Low Confidence", "Speculative")
    ]
    high_unc_weight = sum(p.weight_pct for p in high_unc_positions)
    any_unc_data = any(p.uncertainty_level != "Unknown" for p in positions)
    if any_unc_data:
        high_unc_pct = high_unc_weight / total_weight * 100
        uncertainty_score = min(100, int(high_unc_pct * 2))
        uncertainty_detail = (
            f"{high_unc_pct:.1f}% of portfolio weight in "
            f"Low / Speculative confidence positions."
        )
        uncertainty_contribs = [
            f"{p.ticker}: {p.uncertainty_level}"
            for p in high_unc_positions[:3]
        ]
    else:
        uncertainty_score = 0
        uncertainty_detail = "Unknown — no explainability uncertainty data for any position yet."
        uncertainty_contribs = []

    categories = [
        RiskCategoryScore("concentration",        RISK_CATEGORIES["concentration"],
                          concentration_score, concentration_detail, concentration_contribs),
        RiskCategoryScore("sector_concentration", RISK_CATEGORIES["sector_concentration"],
                          sector_score, sector_detail, sector_contribs),
        RiskCategoryScore("market_exposure",      RISK_CATEGORIES["market_exposure"],
                          market_score, market_detail, market_contribs),
        RiskCategoryScore("valuation_fragility",  RISK_CATEGORIES["valuation_fragility"],
                          valuation_score, valuation_detail, valuation_contribs),
        RiskCategoryScore("thesis_deterioration", RISK_CATEGORIES["thesis_deterioration"],
                          thesis_score, thesis_detail, thesis_contribs),
        RiskCategoryScore("market_disagreement",  RISK_CATEGORIES["market_disagreement"],
                          disagreement_score, disagreement_detail, disagreement_contribs),
        RiskCategoryScore("uncertainty_exposure", RISK_CATEGORIES["uncertainty_exposure"],
                          uncertainty_score, uncertainty_detail, uncertainty_contribs),
    ]

    # ── Weighted final score ──────────────────────────────────────────────────
    total_w = sum(_CATEGORY_WEIGHTS[c.key] for c in categories)
    risk_score = int(sum(c.score * _CATEGORY_WEIGHTS[c.key] for c in categories) / total_w)
    risk_regime = _regime_from_score(risk_score)

    # ── Top 5 risks (specific, ticker-aware) ──────────────────────────────────
    sorted_cats = sorted(categories, key=lambda c: -c.score)
    top_risks: list[str] = []
    for c in sorted_cats:
        if c.score >= 25:
            top_risks.append(f"**{c.name}** (score {c.score}/100) — {c.detail}")
        if len(top_risks) >= 5:
            break
    if not top_risks:
        top_risks = ["No significant portfolio-level risks detected at the current weighting."]

    # ── Top 5 required actions (prescriptive) ─────────────────────────────────
    required_actions: list[str] = []
    if concentration_score >= 50:
        required_actions.append(
            f"Trim **{largest.ticker}** "
            f"({(largest.weight_pct / total_weight * 100):.1f}% of portfolio) — "
            "single-position concentration risk."
        )
    if sector_score >= 50:
        required_actions.append(
            f"Diversify away from **{top_sector}** ({max_sector_pct:.1f}% of portfolio)."
        )
    if market_score >= 60:
        required_actions.append(
            f"Reduce **{top_market}** market exposure ({max_market_pct:.1f}%) — "
            "consider adding other markets."
        )
    for p in deteriorated_positions[:2]:
        required_actions.append(
            f"Re-evaluate **{p.ticker}** — thesis is {p.thesis_status}, "
            f"recommended action: {p.recommended_action}."
        )
    if disagreement_score >= 40 and disagree_data:
        worst = min(
            (p for p in positions if p.market_alignment_score >= 0),
            key=lambda p: p.market_alignment_score,
        )
        required_actions.append(
            f"Investigate market disagreement on **{worst.ticker}** "
            f"(alignment {worst.market_alignment_score}/100)."
        )
    if uncertainty_score >= 50 and high_unc_positions:
        tickers = ", ".join(f"**{p.ticker}**" for p in high_unc_positions[:3])
        required_actions.append(
            f"Strengthen evidence base for {tickers} — low-confidence positions."
        )
    if valuation_score >= 60 and val_data:
        weakest = min(
            (p for p in positions if p.priority_score > 0),
            key=lambda p: p.priority_score,
        )
        required_actions.append(
            f"Re-test valuation for **{weakest.ticker}** "
            f"(Damodaran priority {weakest.priority_score}/100)."
        )
    if not required_actions:
        required_actions = ["No critical actions required — portfolio risk is balanced."]

    return PortfolioRiskResult(
        risk_score=risk_score,
        risk_regime=risk_regime,
        total_weight=total_weight,
        n_positions=len(positions),
        categories=categories,
        top_risks=top_risks[:5],
        required_actions=required_actions[:5],
        computed_at=datetime.now().isoformat(),
    )
