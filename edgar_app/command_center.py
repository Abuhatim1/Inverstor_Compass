"""
command_center.py
-----------------
Portfolio Command Center — executive daily-review dashboard.

Aggregates existing portfolio layers (holdings, decision queue, risk engine,
thesis memory, research watchlist, Damodaran layer) without creating new
analysis logic. All sections degrade gracefully when data is missing.
"""

from __future__ import annotations

import datetime

import streamlit as st


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe(obj, *attrs, default=None):
    """Safely traverse an attribute chain, returning *default* on any error."""
    for attr in attrs:
        try:
            obj = getattr(obj, attr)
        except (AttributeError, TypeError):
            return default
    return obj if obj is not None else default


def _md(text: str | None, fallback: str = "—") -> str:
    return (text or "").strip() or fallback


# ── Main entry-point ──────────────────────────────────────────────────────────

def render_command_center_tab() -> None:
    """⚡ Command Center — executive portfolio dashboard."""

    from portfolio import (
        ACTION_BADGE,
        RISK_REGIME_BADGE,
        THESIS_STATUS_BADGE,
        THESIS_STATUS_BROKEN,
        THESIS_STATUS_STABLE,
        THESIS_STATUS_STRENGTHENING,
        THESIS_STATUS_WEAKENING,
        URGENCY_BADGE,
        build_positions,
        compute_decision_queue,
        compute_portfolio_risk,
        load_all_core_theses,
        load_comparison_history,
        load_delta_history,
        load_holdings,
        load_market_intel_state,
        load_portfolio,
        portfolio_weights,
    )
    import pandas as pd

    st.header("⚡ Portfolio Command Center")
    st.caption(
        f"Daily portfolio review — aggregated from all portfolio layers · "
        f"{datetime.datetime.now().strftime('%A, %d %b %Y  %H:%M')}"
    )

    # ── Load all data ─────────────────────────────────────────────────────────
    holdings   = load_holdings()
    watchlist  = load_portfolio()          # list[PortfolioEntry]
    mi_state   = load_market_intel_state()
    theses     = load_all_core_theses()    # dict[str, CoreThesis]

    if not holdings:
        st.info(
            "No holdings recorded yet. Add positions in the **💼 Holdings** "
            "tab to populate the Command Center.",
            icon="💡",
        )
        return

    # Derived helpers
    weights      = portfolio_weights(holdings)
    watchlist_by = {getattr(e, "ticker", ""): e for e in (watchlist or [])}

    positions = []
    try:
        positions = build_positions(holdings, watchlist, mi_state)
    except Exception:
        pass

    risk_result = None
    try:
        risk_result = compute_portfolio_risk(positions)
    except Exception:
        pass

    dq_result = None
    try:
        dq_result = compute_decision_queue(
            holdings           = holdings,
            watchlist          = watchlist,
            market_intel_state = mi_state,
            delta_history      = load_delta_history(),
            comparison_history = load_comparison_history(),
            core_theses        = theses,
        )
    except Exception:
        pass

    # ── Section 1 · KPI Cards ─────────────────────────────────────────────────
    _render_kpi_cards(
        holdings, weights, risk_result, dq_result,
        RISK_REGIME_BADGE, URGENCY_BADGE,
    )

    st.divider()

    # ── Section 2 · CIO Brief ─────────────────────────────────────────────────
    _render_cio_brief(dq_result, theses, risk_result, THESIS_STATUS_WEAKENING,
                      THESIS_STATUS_BROKEN, THESIS_STATUS_STRENGTHENING)

    st.divider()

    # ── Section 3 · Top Decision Priorities ───────────────────────────────────
    _render_top_decisions(dq_result, URGENCY_BADGE, ACTION_BADGE)

    st.divider()

    # ── Section 4 · Portfolio Risk Snapshot ───────────────────────────────────
    _render_risk_snapshot(risk_result, weights, theses, RISK_REGIME_BADGE,
                          THESIS_STATUS_WEAKENING, THESIS_STATUS_BROKEN)

    st.divider()

    # ── Section 5 · Thesis Health ─────────────────────────────────────────────
    _render_thesis_health(theses, THESIS_STATUS_BADGE,
                          THESIS_STATUS_STRENGTHENING, THESIS_STATUS_STABLE,
                          THESIS_STATUS_WEAKENING,     THESIS_STATUS_BROKEN)

    st.divider()

    # ── Section 6 · Valuation & Mispricing ────────────────────────────────────
    _render_valuation(positions, watchlist_by)

    st.divider()

    # ── Section 7 · Upcoming Catalysts / Monitoring ───────────────────────────
    _render_catalysts(theses, watchlist_by, pd)

    st.divider()

    # ── Section 8 · Action Checklist ──────────────────────────────────────────
    _render_action_checklist(dq_result, risk_result, theses, holdings,
                             URGENCY_BADGE, ACTION_BADGE,
                             THESIS_STATUS_BROKEN, THESIS_STATUS_WEAKENING,
                             pd)


# ── Section renderers ─────────────────────────────────────────────────────────

def _render_kpi_cards(holdings, weights, risk_result, dq_result,
                      RISK_REGIME_BADGE, URGENCY_BADGE):
    st.subheader("📊 Portfolio at a Glance")

    total_mv    = sum(h.market_value for h in holdings.values())
    total_cost  = sum(h.cost_basis   for h in holdings.values())
    total_pnl   = total_mv - total_cost
    pnl_pct     = (total_pnl / total_cost * 100) if total_cost else 0.0

    # Risk regime
    if risk_result:
        r_icon, r_label = RISK_REGIME_BADGE.get(
            risk_result.risk_regime, ("⚪", risk_result.risk_regime)
        )
        regime_str = f"{r_icon} {r_label}"
    else:
        regime_str = "Missing data"

    # Highest attention holding
    top_str = "None"
    if dq_result and dq_result.decisions:
        top  = dq_result.decisions[0]
        u_icon, _ = URGENCY_BADGE.get(top.urgency, ("⚪", top.urgency))
        top_str = f"{u_icon} {top.ticker}"

    # Review count
    _NEEDS_REVIEW = {"Immediate Review", "High Attention", "Review"}
    review_count  = (
        sum(1 for d in dq_result.decisions if d.urgency in _NEEDS_REVIEW)
        if dq_result else None
    )

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Portfolio Value",   f"${total_mv:,.0f}")
    k2.metric("Unrealized P&L",
              f"{'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%",
              delta=f"${total_pnl:+,.0f}")
    k3.metric("Risk Regime",             regime_str)
    k4.metric("Highest Attention",       top_str)
    k5.metric("Requiring Review",
              str(review_count) if review_count is not None else "Missing data")


def _render_cio_brief(dq_result, theses, risk_result,
                      WEAKENING, BROKEN, STRENGTHENING):
    st.subheader("📋 Today's CIO Brief")
    lines: list[str] = []

    if dq_result:
        immediate = [d for d in dq_result.decisions if d.urgency == "Immediate Review"]
        high_attn = [d for d in dq_result.decisions if d.urgency == "High Attention"]
        stable    = [d for d in dq_result.decisions if d.urgency == "Monitor"]

        if immediate:
            reason = immediate[0].key_reason if len(immediate) == 1 else "multiple issues flagged"
            lines.append(
                f"🔴 **Immediate review required:** "
                f"{', '.join(d.ticker for d in immediate)} — {reason}"
            )
        if high_attn:
            lines.append(
                f"🟠 **High attention needed:** "
                f"{', '.join(d.ticker for d in high_attn)}"
            )
        if not immediate and not high_attn:
            lines.append("✅ No positions flagged for urgent attention today.")
        if stable:
            lines.append(
                f"🟢 **Stable / monitoring:** "
                f"{', '.join(d.ticker for d in stable)}"
            )
    else:
        lines.append("⬜ Decision queue unavailable — add holdings to generate priorities.")

    if theses:
        broken       = [t for t, c in theses.items() if _safe(c, "thesis_status") == BROKEN]
        weakening    = [t for t, c in theses.items() if _safe(c, "thesis_status") == WEAKENING]
        strengthening = [t for t, c in theses.items() if _safe(c, "thesis_status") == STRENGTHENING]
        if broken:
            lines.append(f"🚨 **Thesis broken:** {', '.join(broken)} — review exit criteria.")
        if weakening:
            lines.append(f"⚠️ **Thesis weakening:** {', '.join(weakening)} — monitor closely.")
        if strengthening:
            lines.append(f"📈 **Opportunity improving:** {', '.join(strengthening)} thesis strengthening.")

    if risk_result and risk_result.top_risks:
        lines.append(f"🛡️ **Top portfolio risk:** {risk_result.top_risks[0]}")

    if not lines:
        lines.append("No brief data available — add holdings, import theses, and run analyses.")

    for line in lines:
        st.markdown(f"- {line}")


def _render_top_decisions(dq_result, URGENCY_BADGE, ACTION_BADGE):
    st.subheader("🎯 Top Decision Priorities")
    st.caption("Top 3 holdings ranked by attention priority score.")

    if not dq_result or not dq_result.decisions:
        st.info("No decision queue data. Add holdings and run analyses.", icon="ℹ️")
        return

    for i, d in enumerate(dq_result.decisions[:3], 1):
        u_icon, u_label = URGENCY_BADGE.get(d.urgency,        ("⚪", d.urgency))
        a_icon, a_label = ACTION_BADGE.get(d.suggested_action, ("⚪", d.suggested_action))
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            with c1:
                st.markdown(f"**#{i} {d.ticker}**")
                st.caption(d.company_name)
            c2.metric("Priority Score",  f"{d.priority_score}/100")
            c3.metric("Urgency",         f"{u_icon} {u_label}")
            c4.metric("Suggested",       f"{a_icon} {a_label}")
            st.progress(d.priority_score / 100.0)
            st.caption(f"**Why:** {d.key_reason}")


def _render_risk_snapshot(risk_result, weights, theses, RISK_REGIME_BADGE,
                          WEAKENING, BROKEN):
    st.subheader("🛡️ Portfolio Risk Snapshot")

    if not risk_result:
        st.warning(
            "Risk data unavailable. Ensure holdings have current prices set.",
            icon="⚠️",
        )
        return

    cat = {c.key: c for c in risk_result.categories}

    # Largest position
    largest_str = "Missing data"
    if weights:
        top_t  = max(weights, key=lambda t: weights[t])
        largest_str = f"{top_t} ({weights[top_t]:.1f}%)"

    # Thesis weakening/broken count
    tw_count = sum(
        1 for c in theses.values()
        if _safe(c, "thesis_status") in {WEAKENING, BROKEN}
    )

    def _cat(key: str) -> str:
        c = cat.get(key)
        return f"{c.score}/100" if c else "Missing data"

    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Concentration Risk",         _cat("concentration"),
              help=(cat["concentration"].detail if "concentration" in cat else None))
    r2.metric("Largest Position",           largest_str)
    r3.metric("Sector Concentration",       _cat("sector_concentration"),
              help=(cat["sector_concentration"].detail if "sector_concentration" in cat else None))
    r4.metric("Market / Country Exposure",  _cat("market_exposure"),
              help=(cat["market_exposure"].detail if "market_exposure" in cat else None))
    r5.metric("Thesis Weakening / Broken",  str(tw_count))

    if risk_result.top_risks:
        st.caption("**Top risk flags:**")
        for rf in risk_result.top_risks[:3]:
            st.markdown(f"- {rf}")


def _render_thesis_health(theses, THESIS_STATUS_BADGE,
                          STRENGTHENING, STABLE, WEAKENING, BROKEN):
    st.subheader("📜 Thesis Health")

    if not theses:
        st.info(
            "No theses recorded. Import research documents in "
            "the **📜 Thesis Memory** tab.",
            icon="ℹ️",
        )
        return

    counts = {STRENGTHENING: 0, STABLE: 0, WEAKENING: 0, BROKEN: 0}
    for core in theses.values():
        s = _safe(core, "thesis_status", default=STABLE)
        if s in counts:
            counts[s] += 1
        else:
            counts[STABLE] += 1

    def _badge(status: str) -> tuple[str, str]:
        return THESIS_STATUS_BADGE.get(status, ("⚪", status))

    th1, th2, th3, th4 = st.columns(4)
    ico, lbl = _badge(STRENGTHENING)
    th1.metric(f"{ico} {lbl}", counts[STRENGTHENING])
    ico, lbl = _badge(STABLE)
    th2.metric(f"{ico} {lbl}", counts[STABLE])
    ico, lbl = _badge(WEAKENING)
    th3.metric(f"{ico} {lbl}", counts[WEAKENING])
    ico, lbl = _badge(BROKEN)
    th4.metric(f"{ico} {lbl}", counts[BROKEN])

    # Priority list: broken first, then weakening
    priority = sorted(
        [(t, c) for t, c in theses.items()
         if _safe(c, "thesis_status") in {BROKEN, WEAKENING}],
        key=lambda x: 0 if _safe(x[1], "thesis_status") == BROKEN else 1,
    )

    if priority:
        st.caption("**Theses requiring attention:**")
        for ticker, core in priority:
            ico, lbl = _badge(_safe(core, "thesis_status", default=WEAKENING))
            trend    = _safe(core, "conviction_trend", default="")
            drivers  = (_safe(core, "thesis_drivers") or [])[:2]
            preview  = " · ".join(drivers) if drivers else "No drivers recorded"
            with st.container(border=True):
                st.markdown(
                    f"**{ticker}** — {ico} {lbl}"
                    + (f" · Conviction: {trend}" if trend else "")
                )
                st.caption(preview)


def _render_valuation(positions, watchlist_by):
    st.subheader("💰 Valuation & Mispricing")

    if not positions:
        st.info(
            "No position data. Ensure holdings are recorded with current prices.",
            icon="ℹ️",
        )
        return

    accretive   = [p for p in positions if "Accretive"   in (_safe(p, "valuation_impact") or "")]
    destructive = [p for p in positions if "Destructive" in (_safe(p, "valuation_impact") or "")]
    neutral     = [
        p for p in positions
        if "Accretive"   not in (_safe(p, "valuation_impact") or "")
        and "Destructive" not in (_safe(p, "valuation_impact") or "")
        and (_safe(p, "valuation_impact") or "Unknown") not in ("Unknown", "Unclear", "")
    ]
    unanalyzed = [
        p for p in positions
        if not _safe(p, "valuation_impact")
        or _safe(p, "valuation_impact") in ("Unknown", "Unclear / Low Confidence", "")
    ]

    v1, v2, v3, v4 = st.columns(4)
    v1.metric(
        "Value Accretive", len(accretive),
        help=", ".join(p.ticker for p in accretive) or "None",
    )
    v2.metric(
        "Value Destructive", len(destructive),
        help=", ".join(p.ticker for p in destructive) or "None",
    )
    v3.metric("Neutral", len(neutral))
    v4.metric("Not Yet Analyzed", len(unanalyzed))

    # Potential disconnects — positions where recommended action signals concern
    disconnects: list[str] = []
    for ticker, entry in watchlist_by.items():
        val_imp = _safe(entry, "valuation_impact", default="Unknown") or "Unknown"
        rec_act = _safe(entry, "recommended_action", default="") or ""
        if "Destructive" in val_imp or rec_act in ("Reduce", "Exit Watch"):
            disconnects.append(
                f"**{ticker}**: {val_imp}"
                + (f" — suggested action: *{rec_act}*" if rec_act else "")
            )

    if disconnects:
        st.caption("**Potential valuation disconnects:**")
        for item in disconnects[:6]:
            st.markdown(f"- {item}")
    else:
        st.caption("No valuation disconnects detected from available watchlist data.")

    if unanalyzed:
        st.caption(
            "ℹ️ Run **Upload Filing** or **Filing Search** analyses on "
            f"{', '.join(p.ticker for p in unanalyzed)} to populate valuation data."
        )


def _render_catalysts(theses, watchlist_by, pd):
    st.subheader("🚀 Upcoming Catalysts & Monitoring Items")

    rows: list[dict] = []

    # From core theses
    for ticker, core in theses.items():
        for cat in (_safe(core, "expected_catalysts") or []):
            rows.append({"Holding": ticker, "Type": "📅 Expected catalyst", "Item": cat})
        for rm in (_safe(core, "risk_matrix") or []):
            for ewi in (_safe(rm, "early_warning_indicators") or [])[:2]:
                rows.append({"Holding": ticker, "Type": "⚠️ Early warning", "Item": ewi})

    # From research watchlist (cap per ticker to avoid noise)
    for ticker, entry in watchlist_by.items():
        for cat in (_safe(entry, "catalysts") or [])[:3]:
            rows.append({"Holding": ticker, "Type": "🔬 Watchlist catalyst", "Item": cat})

    if not rows:
        st.info(
            "No catalyst data found. Import research documents in "
            "**📜 Thesis Memory** or run filing analyses to populate this section.",
            icon="ℹ️",
        )
        return

    df = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["Holding", "Item"])
        .sort_values(["Type", "Holding"])
        .reset_index(drop=True)
        .astype(str)
    )
    st.dataframe(df, hide_index=True, use_container_width=True)


def _render_action_checklist(dq_result, risk_result, theses, holdings,
                              URGENCY_BADGE, ACTION_BADGE,
                              BROKEN, WEAKENING, pd):
    st.subheader("✅ Action Checklist")
    st.caption("All pending actions across holdings, thesis health, and portfolio risk.")

    actions: list[dict] = []

    # ── From decision queue ────────────────────────────────────────────────────
    _NEEDS_ACTION = {"Immediate Review", "High Attention", "Review"}
    if dq_result:
        for d in dq_result.decisions:
            if d.urgency in _NEEDS_ACTION:
                u_icon, u_label = URGENCY_BADGE.get(d.urgency,        ("⚪", d.urgency))
                a_icon, a_label = ACTION_BADGE.get(d.suggested_action, ("⚪", d.suggested_action))
                actions.append({
                    "Priority": f"{u_icon} {u_label}",
                    "Holding":  d.ticker,
                    "Action":   f"{a_icon} {a_label}",
                    "Reason":   d.key_reason,
                })

    # ── Broken theses ──────────────────────────────────────────────────────────
    for ticker, core in theses.items():
        if _safe(core, "thesis_status") == BROKEN:
            actions.append({
                "Priority": "🚨 Immediate Review",
                "Holding":  ticker,
                "Action":   "🔧 Reassess or exit thesis",
                "Reason":   "Thesis is Broken — review exit criteria",
            })

    # ── Weakening theses with no drivers ──────────────────────────────────────
    for ticker, core in theses.items():
        if _safe(core, "thesis_status") == WEAKENING and not _safe(core, "thesis_drivers"):
            actions.append({
                "Priority": "🟠 High Attention",
                "Holding":  ticker,
                "Action":   "📝 Add missing thesis data",
                "Reason":   "Thesis weakening but no drivers recorded",
            })

    # ── Portfolio-level risk required actions ──────────────────────────────────
    for ra in (_safe(risk_result, "required_actions") or []):
        actions.append({
            "Priority": "🟡 Review",
            "Holding":  "Portfolio",
            "Action":   "🛡️ Risk mitigation",
            "Reason":   ra,
        })

    # ── Holdings missing a thesis ──────────────────────────────────────────────
    for ticker in holdings:
        if ticker not in theses:
            actions.append({
                "Priority": "🟡 Review",
                "Holding":  ticker,
                "Action":   "📋 Add thesis",
                "Reason":   "No thesis recorded — import a research document",
            })

    # ── Holdings with no current price ────────────────────────────────────────
    for ticker, h in holdings.items():
        if not getattr(h, "current_price", None):
            actions.append({
                "Priority": "🟡 Review",
                "Holding":  ticker,
                "Action":   "💰 Update current price",
                "Reason":   "Price missing — P&L and risk calculations are inaccurate",
            })

    if not actions:
        st.success("No pending actions — portfolio is up to date!", icon="✅")
        return

    # Deduplicate by (holding, action) and show
    seen:    set  = set()
    unique:  list = []
    for a in actions:
        key = (a["Holding"], a["Action"])
        if key not in seen:
            seen.add(key)
            unique.append(a)

    df = pd.DataFrame(unique).astype(str)
    st.dataframe(df, hide_index=True, use_container_width=True)
