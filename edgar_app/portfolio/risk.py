"""
portfolio/risk.py
-----------------
Portfolio Risk Engine.

Sources of truth:
  · **Actual Holdings** (`holdings.py`)  — weight, market, sector, ticker identity.
    Weights are derived from market value (quantity × current_price).
  · **Research Watchlist** (`state.py`)  — thesis, conviction, action,
    Damodaran valuation, explainability uncertainty — joined by ticker
    when available; missing data degrades to "Unknown".
  · **Market intel state** (`market_intel_state.json`) — per-ticker
    alignment score from the External Market Intelligence layer.

This is NOT a price-volatility engine. Risk categories:
  · Concentration (single position too large)
  · Sector concentration
  · Country / market exposure
  · Valuation fragility (low Damodaran priority score)
  · Thesis deterioration (Weak / Broken status in watchlist)
  · External market disagreement (low alignment score)
  · High-uncertainty exposure (Low / Speculative confidence)
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime

from .holdings import Holding, portfolio_weights


# ── Storage locations ─────────────────────────────────────────────────────────

_DIR               = os.path.dirname(__file__)
_MARKET_INTEL_FILE = os.path.join(_DIR, "market_intel_state.json")


# ── Taxonomy ──────────────────────────────────────────────────────────────────

MARKETS: list[str] = ["US", "Saudi", "UK", "Europe", "Asia", "Other"]

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
    # Asset-class specific
    "commodity_risk":         "Commodity Risk",
    "currency_risk":          "Currency Risk",
    "manual_valuation_risk":  "Manual Valuation Risk",
}

_CATEGORY_WEIGHTS: dict[str, float] = {
    "concentration":        1.5,
    "sector_concentration": 1.0,
    "market_exposure":      0.8,
    "valuation_fragility":  1.0,
    "thesis_deterioration": 1.5,
    "market_disagreement":  0.7,
    "uncertainty_exposure": 1.0,
    "commodity_risk":        0.8,
    "currency_risk":         0.7,
    "manual_valuation_risk": 1.0,
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class PortfolioPosition:
    """One risk-engine row — joins Holding + Watchlist + Market Intel."""
    ticker:                 str
    company_name:           str
    # From Holding
    market:                 str
    sector:                 str
    weight_pct:             float           # derived from market value
    market_value:           float
    asset_type:             str = "Stock"   # from Holding.asset_type
    currency:               str = "USD"     # from Holding.currency
    has_ticker:             bool = True     # from Holding.has_ticker
    is_manual_price:        bool = False    # True when price_source == "manual" and no ticker
    # From PortfolioEntry (research watchlist) — Unknown if no analysis yet
    thesis_status:          str = "Unknown"
    conviction_score:       int = 0
    recommended_action:     str = "Unknown"
    valuation_impact:       str = "Unknown"
    priority_score:         int = 0
    uncertainty_level:      str = "Unknown"
    # From market intel state
    market_alignment_score: int = -1
    market_alignment_label: str = "No Baseline"


@dataclass
class RiskCategoryScore:
    key:          str
    name:         str
    score:        int           # 0-100
    detail:       str
    contributors: list[str] = field(default_factory=list)


@dataclass
class PortfolioRiskResult:
    risk_score:       int
    risk_regime:      str
    total_weight:     float          # always 100.0 when holdings have market value
    n_positions:      int
    total_market_value: float
    categories:       list[RiskCategoryScore]
    top_risks:        list[str]
    required_actions: list[str]
    computed_at:      str


# ── Market intel state persistence ────────────────────────────────────────────

def load_market_intel_state() -> dict[str, dict]:
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
    dominant_view:   str = "",     # "Bullish" | "Bearish" | "Mixed" | "Neutral"
    mispricing:      str = "",     # from MISPRICING_BADGE labels
) -> None:
    state = load_market_intel_state()
    state[ticker] = {
        "alignment_score": int(alignment_score),
        "alignment_label": alignment_label,
        "dominant_view":   dominant_view,
        "mispricing":      mispricing,
        "updated_at":      datetime.now().isoformat(),
    }
    os.makedirs(_DIR, exist_ok=True)
    with open(_MARKET_INTEL_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── Position assembly: join holdings + watchlist + market intel ───────────────

def build_positions(
    holdings:           dict[str, Holding],
    watchlist:          dict,                 # {ticker: PortfolioEntry}
    market_intel_state: dict[str, dict] | None = None,
) -> list[PortfolioPosition]:
    """
    Build the risk-engine view from Actual Holdings, enriched with
    Research Watchlist data and market intel where the ticker matches.
    """
    mi      = market_intel_state if market_intel_state is not None else load_market_intel_state()
    weights = portfolio_weights(holdings)

    positions: list[PortfolioPosition] = []
    for ticker, h in holdings.items():
        entry      = watchlist.get(ticker)        # may be None
        mi_entry   = mi.get(ticker, {})

        thesis    = getattr(entry, "thesis_status", "Unknown") if entry else "Unknown"
        convict   = int(getattr(entry, "conviction_score", 0) or 0) if entry else 0
        action    = getattr(entry, "recommended_action", "Unknown") if entry else "Unknown"
        val_imp   = getattr(entry, "valuation_impact", "Unknown") if entry else "Unknown"
        priority  = int(getattr(entry, "priority_score", 0) or 0) if entry else 0
        unc_level = getattr(entry, "uncertainty_level", "Unknown") if entry else "Unknown"

        is_manual = (
            not getattr(h, "has_ticker", True)
            or getattr(h, "price_source", "manual") == "manual"
        )
        positions.append(PortfolioPosition(
            ticker=ticker,
            company_name=h.company_name,
            market=h.market,
            sector=h.sector,
            weight_pct=weights.get(ticker, 0.0),
            market_value=h.market_value,
            asset_type=getattr(h, "asset_type", "Stock"),
            currency=getattr(h, "currency", "USD"),
            has_ticker=getattr(h, "has_ticker", True),
            is_manual_price=is_manual,
            thesis_status=thesis,
            conviction_score=convict,
            recommended_action=action,
            valuation_impact=val_imp,
            priority_score=priority,
            uncertainty_level=unc_level,
            market_alignment_score=int(mi_entry.get("alignment_score", -1)),
            market_alignment_label=mi_entry.get("alignment_label", "No Baseline"),
        ))
    return positions


# ── Risk engine ───────────────────────────────────────────────────────────────

def _regime_from_score(score: int) -> str:
    if score < 25:  return "Low"
    if score < 50:  return "Medium"
    if score < 75:  return "High"
    return "Critical"


def _empty_result(
    n_positions: int = 0,
    total_market_value: float = 0.0,
    top_risks: list[str] | None = None,
    required_actions: list[str] | None = None,
) -> PortfolioRiskResult:
    return PortfolioRiskResult(
        risk_score=0,
        risk_regime="Low",
        total_weight=0.0,
        n_positions=n_positions,
        total_market_value=total_market_value,
        categories=[],
        top_risks=top_risks or [
            "No holdings yet — add actual positions in the Holdings tab to compute risk."
        ],
        required_actions=required_actions or [
            "Open the **Holdings** tab and record your positions with quantity and average cost."
        ],
        computed_at=datetime.now().isoformat(),
    )


def compute_portfolio_risk(positions: list[PortfolioPosition]) -> PortfolioRiskResult:
    """Compute the full portfolio-level risk picture from holdings-derived positions."""
    if not positions:
        return _empty_result()

    total_market_value = sum(p.market_value for p in positions)
    if total_market_value <= 0:
        return _empty_result(
            n_positions=len(positions),
            total_market_value=0.0,
            top_risks=[
                "Holdings exist but no current prices set — risk cannot be computed."
            ],
            required_actions=[
                "Open the **Holdings** tab and enter a current price for each position."
            ],
        )

    total_weight = sum(p.weight_pct for p in positions)  # should be ~100

    # ── 1. Concentration risk (HHI) ───────────────────────────────────────────
    hhi = sum(p.weight_pct * p.weight_pct for p in positions)
    concentration_score = min(100, int(hhi / 50))
    largest = max(positions, key=lambda p: p.weight_pct)
    concentration_detail = (
        f"Largest position: {largest.ticker} at {largest.weight_pct:.1f}% of portfolio value."
    )
    sorted_positions = sorted(positions, key=lambda p: -p.weight_pct)
    concentration_contribs = [
        f"{p.ticker}: {p.weight_pct:.1f}%" for p in sorted_positions[:3]
    ]

    # ── 2. Sector concentration ───────────────────────────────────────────────
    sector_weights: dict[str, float] = {}
    for p in positions:
        sector_weights[p.sector] = sector_weights.get(p.sector, 0.0) + p.weight_pct
    max_sector_pct = max(sector_weights.values()) if sector_weights else 0.0
    sector_score = min(100, int(max_sector_pct * 1.5))
    top_sector = max(sector_weights, key=sector_weights.get) if sector_weights else "—"
    sector_detail = f"Top sector: {top_sector} ({max_sector_pct:.1f}% of portfolio value)."
    sector_contribs = [
        f"{s}: {w:.1f}%"
        for s, w in sorted(sector_weights.items(), key=lambda x: -x[1])[:3]
    ]

    # ── 3. Market / country exposure ──────────────────────────────────────────
    market_weights: dict[str, float] = {}
    for p in positions:
        market_weights[p.market] = market_weights.get(p.market, 0.0) + p.weight_pct
    max_market_pct = max(market_weights.values()) if market_weights else 0.0
    market_score = max(0, min(100, int((max_market_pct - 50) * 2)))
    top_market = max(market_weights, key=market_weights.get) if market_weights else "—"
    market_detail = f"Top market: {top_market} ({max_market_pct:.1f}% of portfolio value)."
    market_contribs = [
        f"{m}: {w:.1f}%"
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
        valuation_detail = "Unknown — no Damodaran valuation data for any held position."
        valuation_contribs = []

    # ── 5. Thesis deterioration ───────────────────────────────────────────────
    deteriorated = [p for p in positions if p.thesis_status in ("Weak", "Broken")]
    deteriorated_weight = sum(p.weight_pct for p in deteriorated)
    thesis_score = min(100, int(deteriorated_weight * 2))
    thesis_detail = (
        f"{len(deteriorated)} of {len(positions)} positions in Weak/Broken status — "
        f"{deteriorated_weight:.1f}% of portfolio value."
    )
    thesis_contribs = [
        f"{p.ticker}: {p.thesis_status} · action: {p.recommended_action}"
        for p in deteriorated[:3]
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
        disagreement_detail = "Unknown — no external market intelligence run for any held position."
        disagreement_contribs = []

    # ── 7. High-uncertainty exposure ──────────────────────────────────────────
    high_unc = [p for p in positions if p.uncertainty_level in ("Low Confidence", "Speculative")]
    any_unc_data = any(p.uncertainty_level != "Unknown" for p in positions)
    if any_unc_data:
        high_unc_pct = sum(p.weight_pct for p in high_unc)
        uncertainty_score = min(100, int(high_unc_pct * 2))
        uncertainty_detail = (
            f"{high_unc_pct:.1f}% of portfolio value in Low / Speculative confidence positions."
        )
        uncertainty_contribs = [f"{p.ticker}: {p.uncertainty_level}" for p in high_unc[:3]]
    else:
        uncertainty_score = 0
        uncertainty_detail = "Unknown — no explainability uncertainty data for any held position."
        uncertainty_contribs = []

    # ── 8. Commodity risk ─────────────────────────────────────────────────────
    commodity_types = ("Commodity", "Precious Metal")
    commodity_pos = [p for p in positions if p.asset_type in commodity_types]
    commodity_weight = sum(p.weight_pct for p in commodity_pos)
    commodity_score = min(100, int(commodity_weight * 1.5))
    commodity_detail = (
        f"{commodity_weight:.1f}% of portfolio value in commodity assets "
        f"({len(commodity_pos)} position(s))."
        if commodity_pos else
        "No commodity positions held."
    )
    commodity_contribs = [f"{p.ticker} ({p.asset_type}): {p.weight_pct:.1f}%" for p in commodity_pos[:3]]

    # ── 9. Currency risk ──────────────────────────────────────────────────────
    non_usd = [p for p in positions if p.currency not in ("USD", "")]
    non_usd_weight = sum(p.weight_pct for p in non_usd)
    currency_score = min(100, int(non_usd_weight * 1.2))
    currency_currencies = sorted({p.currency for p in non_usd})
    currency_detail = (
        f"{non_usd_weight:.1f}% of portfolio value in non-USD currencies "
        f"({', '.join(currency_currencies)})."
        if non_usd else
        "All holdings denominated in USD."
    )
    currency_contribs = [f"{p.ticker}: {p.currency} ({p.weight_pct:.1f}%)" for p in non_usd[:3]]

    # ── 10. Manual valuation risk ─────────────────────────────────────────────
    manual_pos = [p for p in positions if p.is_manual_price]
    manual_weight = sum(p.weight_pct for p in manual_pos)
    manual_score = min(100, int(manual_weight * 1.5))
    manual_detail = (
        f"{manual_weight:.1f}% of portfolio value relies on manually-entered prices "
        f"({len(manual_pos)} position(s)) — not verified by live market feed."
        if manual_pos else
        "All holdings have live or yfinance-sourced prices."
    )
    manual_contribs = [f"{p.ticker}: manual price" for p in manual_pos[:3]]

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
        RiskCategoryScore("commodity_risk",        RISK_CATEGORIES["commodity_risk"],
                          commodity_score, commodity_detail, commodity_contribs),
        RiskCategoryScore("currency_risk",         RISK_CATEGORIES["currency_risk"],
                          currency_score, currency_detail, currency_contribs),
        RiskCategoryScore("manual_valuation_risk", RISK_CATEGORIES["manual_valuation_risk"],
                          manual_score, manual_detail, manual_contribs),
    ]

    total_w = sum(_CATEGORY_WEIGHTS[c.key] for c in categories)
    risk_score = int(sum(c.score * _CATEGORY_WEIGHTS[c.key] for c in categories) / total_w)
    risk_regime = _regime_from_score(risk_score)

    sorted_cats = sorted(categories, key=lambda c: -c.score)
    top_risks: list[str] = []
    for c in sorted_cats:
        if c.score >= 25:
            top_risks.append(f"**{c.name}** (score {c.score}/100) — {c.detail}")
        if len(top_risks) >= 5:
            break
    if not top_risks:
        top_risks = ["No significant portfolio-level risks detected at the current weighting."]

    required_actions: list[str] = []
    if concentration_score >= 50:
        required_actions.append(
            f"Trim **{largest.ticker}** ({largest.weight_pct:.1f}% of portfolio) — "
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
    for p in deteriorated[:2]:
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
    if uncertainty_score >= 50 and high_unc:
        tickers = ", ".join(f"**{p.ticker}**" for p in high_unc[:3])
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
    if manual_score >= 50 and manual_pos:
        tickers_m = ", ".join(f"**{p.ticker}**" for p in manual_pos[:3])
        required_actions.append(
            f"Update manual prices for {tickers_m} — these affect {manual_weight:.1f}% "
            "of portfolio value and are not verified by a live market feed."
        )
    if commodity_score >= 60 and commodity_pos:
        required_actions.append(
            f"Review commodity exposure ({commodity_weight:.1f}% of portfolio) — "
            "consider target allocation limits for Gold/Silver/Commodity positions."
        )
    if not required_actions:
        required_actions = ["No critical actions required — portfolio risk is balanced."]

    return PortfolioRiskResult(
        risk_score=risk_score,
        risk_regime=risk_regime,
        total_weight=total_weight,
        n_positions=len(positions),
        total_market_value=total_market_value,
        categories=categories,
        top_risks=top_risks[:5],
        required_actions=required_actions[:5],
        computed_at=datetime.now().isoformat(),
    )
