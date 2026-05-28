"""
app.py — SEC EDGAR Filing Research Tool
----------------------------------------
Streamlit UI for SEC filings with AI analysis, Portfolio State Engine,
Delta Intelligence Engine, and Historical Filing Comparison.

Structure:
  edgar/       — EDGAR API data layer
  ai/          — AI analysis: fetcher, analyzer, cache, comparator
  portfolio/   — State engine, delta detection, comparison store
  app.py       — This file: UI only
"""

import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import streamlit as st

from edgar import EdgarAPIError, get_filings, lookup_company
from edgar.filings import Filing
from ai.analyzer import AnalysisResult, analyze_filing, get_api_key
from ai.cache import DAILY_LIMIT, cache_size, get_today_count
from ai.evidence import CONFIDENCE_BADGE, FIELD_LABELS, evidence_by_field
from portfolio import (
    # state
    PortfolioEntry,
    delete_ticker,
    load_portfolio,
    update_portfolio,
    # delta
    DeltaRecord,
    load_delta_history,
    ALERT_ACTION_DOWNGRADED,
    ALERT_ACTION_UPGRADED,
    ALERT_CONVICTION_DROPPED,
    ALERT_CONVICTION_IMPROVED,
    ALERT_FALLING_RISK,
    ALERT_RISING_RISK,
    ALERT_THESIS_IMPROVED,
    ALERT_THESIS_WEAKENED,
    # comparison
    ComparisonRecord,
    TREND_ICON,
    TONE_ICON,
    GUIDANCE_ICON,
    build_comparison_record,
    load_comparison_history,
    save_comparison,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SEC EDGAR Filing Research",
    page_icon="📋",
    layout="centered",
)

# ── Constants ─────────────────────────────────────────────────────────────────
FILING_TYPES = {
    "10-K": {"label": "10-K — Annual Report",    "limit": 3},
    "10-Q": {"label": "10-Q — Quarterly Report", "limit": 5},
    "8-K":  {"label": "8-K — Current Report",    "limit": 5},
}

_IMPACT_COLOR = {"Strong": "🟢", "Stable": "🔵", "Weak": "🟡", "Broken": "🔴"}
_ACTION_COLOR  = {"Buy": "🟢",   "Hold": "🔵",  "Reduce": "🟡", "Exit": "🔴"}

_ALERT_DISPLAY = {
    ALERT_THESIS_WEAKENED:    ("🔴", "Thesis weakened"),
    ALERT_THESIS_IMPROVED:    ("🟢", "Thesis improved"),
    ALERT_RISING_RISK:        ("🔴", "Rising risk"),
    ALERT_FALLING_RISK:       ("🟢", "Falling risk"),
    ALERT_ACTION_DOWNGRADED:  ("🔴", "Action downgraded"),
    ALERT_ACTION_UPGRADED:    ("🟢", "Action upgraded"),
    ALERT_CONVICTION_DROPPED: ("🔴", "Conviction dropped"),
    ALERT_CONVICTION_IMPROVED:("🟢", "Conviction improved"),
}

# Trend label → human-friendly text for comparison table
_TREND_LABEL = {
    "improving": "Improving",
    "stable":    "Stable",
    "declining": "Declining",
    "positive":  "Positive",
    "neutral":   "Neutral",
    "cautious":  "Cautious",
    "negative":  "Negative",
    "raised":    "Raised",
    "maintained":"Maintained",
    "lowered":   "Lowered",
    "withdrawn": "Withdrawn",
    "not_mentioned": "—",
}


# ── Helpers: secrets + API key ────────────────────────────────────────────────
def _st_secrets():
    try:
        return st.secrets
    except Exception:
        return None

_api_key  = get_api_key(_st_secrets())
_ai_ready = bool(_api_key)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    demo_mode = st.toggle(
        "Demo Analysis Mode",
        value=not _ai_ready,
        help="Returns sample data instantly without calling OpenAI.",
    )

    if demo_mode:
        st.info("Demo mode **on** — sample data returned.", icon="🧪")
    elif _ai_ready:
        st.success("Live AI analysis active.", icon="✅")
    else:
        st.warning("API key missing.", icon="🔑")

    st.divider()
    st.caption("🔑 **API Key Status**")
    if _ai_ready:
        st.success("OPENAI_API_KEY found", icon="✅")
    else:
        st.error("OPENAI_API_KEY missing", icon="❌")
        st.markdown("Add it in **Replit Secrets** with key `OPENAI_API_KEY`, then:")
        if st.button("🔄 Reload secrets", use_container_width=True):
            st.rerun()

    st.divider()
    st.caption("📊 **Usage Today**")
    _today_count = get_today_count()
    _pct = int(_today_count / DAILY_LIMIT * 100)
    st.progress(_pct / 100, text=f"{_today_count} / {DAILY_LIMIT} live analyses")
    if _today_count >= DAILY_LIMIT:
        st.error("Daily limit reached — enable Demo Mode or wait until midnight.", icon="🚫")
    elif _today_count >= DAILY_LIMIT * 0.8:
        st.warning(f"Approaching daily limit ({DAILY_LIMIT - _today_count} remaining).", icon="⚠️")

    st.divider()
    st.caption("📦 **Analysis Cache**")
    _n_cached = cache_size()
    st.caption(f"{_n_cached} filing(s) cached — repeat analyses are instant and free.")

_analyze_enabled = _ai_ready or demo_mode


# ═══════════════════════════════════════════════════════════════════════════════
# Render helpers
# ═══════════════════════════════════════════════════════════════════════════════

def render_analysis(result: AnalysisResult) -> None:
    """Render one AnalysisResult: status badge, metrics, narrative, comparison."""
    # ── Status banner ─────────────────────────────────────────────────────────
    if result.is_cached:
        st.success("📦 Cached result — loaded instantly, no API call made.", icon="📦")
    elif result.is_demo:
        label = "🧪 Demo result"
        if result.error:
            label += f" — {result.error}"
        st.info(label)
    elif result.error and not result.what_changed:
        st.error(f"**Analysis failed:** {result.error}")
        return

    # ── Core metrics ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Thesis Impact",    f"{_IMPACT_COLOR.get(result.thesis_impact,'⚪')} {result.thesis_impact}")
    col2.metric("Suggested Action", f"{_ACTION_COLOR.get(result.suggested_action,'⚪')} {result.suggested_action}")
    col3.metric("Confidence",       f"{result.confidence_score} / 100")

    st.markdown("**What changed**")
    st.write(result.what_changed)

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Key Catalysts**")
        for item in result.key_catalysts:
            st.markdown(f"- {item}")
    with col_r:
        st.markdown("**Key Risks**")
        for item in result.key_risks:
            st.markdown(f"- {item}")

    # ── Historical Comparison (only when available) ───────────────────────────
    if result.comparison:
        c = result.comparison
        adj = c.conviction_adjustment
        adj_sign = "+" if adj > 0 else ""
        adj_color = "🟢" if adj > 0 else ("🔴" if adj < 0 else "⚪")

        # Build evidence lookup for confidence-gating the trend grid
        ev_lookup = evidence_by_field(result.evidence)

        st.divider()
        st.markdown(
            f"**📊 vs. Previous Filing Comparison** — "
            f"Conviction adjustment: {adj_color} {adj_sign}{adj}"
        )

        # Trend grid — low-confidence fields show ❓ instead of a trend claim
        trend_rows = [
            ("Revenue growth",  c.revenue_growth_trend, TREND_ICON,    "revenue_growth"),
            ("Margins",         c.margin_trend,          TREND_ICON,    "margins"),
            ("Cash position",   c.cash_trend,            TREND_ICON,    "cash_position"),
            ("Debt / leverage", c.debt_trend,            TREND_ICON,    "debt"),
            ("Management tone", c.management_tone,       TONE_ICON,     "management_tone"),
            ("Guidance",        c.guidance_trend,        GUIDANCE_ICON, "guidance"),
        ]
        cols = st.columns(3)
        for idx, (label, value, icon_map, ev_field) in enumerate(trend_rows):
            ev = ev_lookup.get(ev_field)
            if ev and ev.confidence == "low":
                cols[idx % 3].metric(label, "❓ Low confidence")
            else:
                icon = icon_map.get(value, "❓")
                txt  = _TREND_LABEL.get(value, value.title())
                conf_icon = CONFIDENCE_BADGE.get(ev.confidence, ("⚪", ""))[0] if ev else ""
                cols[idx % 3].metric(label, f"{icon} {txt}", delta=conf_icon if conf_icon else None)

        # Four narrative sections
        with st.expander("What improved / weakened / new"):
            nc1, nc2 = st.columns(2)
            with nc1:
                if c.what_improved:
                    st.markdown("**✅ What improved**")
                    for item in c.what_improved:
                        st.markdown(f"- {item}")
                if c.new_catalysts:
                    st.markdown("**🚀 New catalysts**")
                    for item in c.new_catalysts:
                        st.markdown(f"- {item}")
            with nc2:
                if c.what_weakened:
                    st.markdown("**⚠️ What weakened**")
                    for item in c.what_weakened:
                        st.markdown(f"- {item}")
                if c.new_concerns:
                    st.markdown("**🔴 New concerns**")
                    for item in c.new_concerns:
                        st.markdown(f"- {item}")


    # ── Evidence Grounding (always shown when evidence exists) ────────────────
    if result.evidence:
        _render_evidence_section(result.evidence, has_comparison=result.comparison is not None)


def _render_evidence_section(evidence: list, has_comparison: bool) -> None:
    """Render collapsible evidence cards — one per financial field."""
    st.divider()
    # Count by confidence level
    n_high   = sum(1 for e in evidence if e.confidence == "high")
    n_medium = sum(1 for e in evidence if e.confidence == "medium")
    n_low    = sum(1 for e in evidence if e.confidence == "low")
    summary  = f"🟢 {n_high} high · 🟡 {n_medium} medium · 🔴 {n_low} low confidence"

    with st.expander(f"🔍 Evidence Grounding — {summary}"):
        st.caption(
            "Every AI conclusion is grounded in a direct quote or metric from the filing. "
            "🔴 Low confidence means the filing did not mention that topic."
        )
        for ev in evidence:
            _render_evidence_card(ev, has_comparison)


def _render_evidence_card(ev, has_comparison: bool) -> None:
    """Render one EvidenceItem as a structured card."""
    conf_icon, conf_label = CONFIDENCE_BADGE.get(ev.confidence, ("⚪", "Unknown"))
    field_label = FIELD_LABELS.get(ev.field, ev.field.replace("_", " ").title())

    with st.container(border=True):
        hc1, hc2 = st.columns([3, 1])
        with hc1:
            st.markdown(f"**{field_label}**")
            if ev.section and ev.section not in ("", "not_mentioned"):
                st.caption(f"📄 Section: {ev.section}")
        with hc2:
            st.markdown(f"{conf_icon} **{conf_label}**")

        if ev.confidence == "low":
            st.caption("_No relevant data found in this filing excerpt._")
            if ev.interpretation:
                st.caption(f"Note: {ev.interpretation}")
            return

        # Values row
        if has_comparison and ev.previous_value and ev.previous_value not in ("", "not_applicable"):
            vc1, vc2, vc3 = st.columns(3)
            vc1.metric("Previous", ev.previous_value)
            vc2.metric("Current",  ev.current_value)
            if ev.delta and ev.delta not in ("", "not_applicable"):
                # Try to detect positive/negative direction for delta colouring
                delta_str = ev.delta
                vc3.metric("Change", delta_str)
        else:
            st.markdown(f"**Value:** {ev.current_value}")

        # Quote
        if ev.quote:
            st.markdown(f"> *\"{ev.quote}\"*")

        # Interpretation
        if ev.interpretation:
            st.info(f"💡 {ev.interpretation}", icon="💡")


def render_delta_card(d: DeltaRecord) -> None:
    has_red = any(a in d.alerts for a in (
        ALERT_THESIS_WEAKENED, ALERT_RISING_RISK,
        ALERT_ACTION_DOWNGRADED, ALERT_CONVICTION_DROPPED,
    ))

    with st.container(border=True):
        hc1, hc2, hc3 = st.columns([2, 4, 2])
        with hc1:
            st.markdown(f"**{d.ticker}**")
            st.caption(d.company_name)
        with hc2:
            if d.is_first_analysis:
                st.caption("🆕 First analysis")
            elif d.alerts:
                badges = " · ".join(
                    f"{_ALERT_DISPLAY[a][0]} {_ALERT_DISPLAY[a][1]}"
                    for a in d.alerts if a in _ALERT_DISPLAY
                )
                if has_red:
                    st.error(badges)
                else:
                    st.success(badges)
            else:
                st.caption("No significant changes")
        with hc3:
            st.caption(f"📄 {d.filing_type}")
            st.caption(f"🕐 {d.timestamp[:16].replace('T', ' ')}")

        if not d.is_first_analysis:
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric(
                "Thesis",
                f"{_IMPACT_COLOR.get(d.thesis_new,'⚪')} {d.thesis_new}",
                delta=f"was {d.thesis_prev}" if d.thesis_changed else None,
            )
            sc2.metric(
                "Action",
                f"{_ACTION_COLOR.get(d.action_new,'⚪')} {d.action_new}",
                delta=f"was {d.action_prev}" if d.action_changed else None,
            )
            sc3.metric(
                "Conviction",
                f"{d.conviction_new}/100",
                delta=f"{d.conviction_delta:+d}" if d.conviction_delta != 0 else None,
                delta_color="normal",
            )

        with st.expander("What changed"):
            for line in d.what_changed:
                st.markdown(f"- {line}")
            if d.catalyst_trend != "same":
                st.markdown(f"- {'📈' if d.catalyst_trend == 'more' else '📉'} Catalyst count: {d.catalyst_trend}")
            if d.risk_trend != "same":
                st.markdown(f"- {'⚠️' if d.risk_trend == 'more' else '✅'} Risk count: {d.risk_trend}")


def render_comparison_card(rec: ComparisonRecord) -> None:
    """Render one ComparisonRecord in the Historical Delta Analysis section."""
    adj = rec.conviction_adjustment
    adj_sign  = "+" if adj > 0 else ""
    adj_color = "🟢" if adj > 0 else ("🔴" if adj < 0 else "⚪")

    with st.container(border=True):
        hc1, hc2, hc3 = st.columns([2, 4, 2])
        with hc1:
            st.markdown(f"**{rec.ticker}**")
            st.caption(rec.company_name)
        with hc2:
            adj_msg = f"Conviction {adj_sign}{adj}"
            if adj > 0:
                st.success(f"{adj_color} {adj_msg}")
            elif adj < 0:
                st.error(f"{adj_color} {adj_msg}")
            else:
                st.caption(f"{adj_color} No conviction change")
        with hc3:
            st.caption(f"📄 {rec.filing_type}")
            st.caption(f"🕐 {rec.timestamp[:16].replace('T', ' ')}")

        # Trend grid (6 cells, 3 per row)
        tc = st.columns(6)
        trend_cells = [
            ("Revenue",  rec.revenue_growth_trend, TREND_ICON),
            ("Margins",  rec.margin_trend,          TREND_ICON),
            ("Cash",     rec.cash_trend,            TREND_ICON),
            ("Debt",     rec.debt_trend,            TREND_ICON),
            ("Tone",     rec.management_tone,       TONE_ICON),
            ("Guidance", rec.guidance_trend,        GUIDANCE_ICON),
        ]
        for col, (label, value, icon_map) in zip(tc, trend_cells):
            col.metric(label, f"{icon_map.get(value, '❓')} {_TREND_LABEL.get(value, value)}")

        # Narrative sections (collapsed by default)
        has_content = any([
            rec.what_improved, rec.what_weakened,
            rec.new_catalysts, rec.new_concerns,
        ])
        if has_content:
            with st.expander("Detailed comparison"):
                nc1, nc2 = st.columns(2)
                with nc1:
                    if rec.what_improved:
                        st.markdown("**✅ Improved**")
                        for i in rec.what_improved:
                            st.markdown(f"- {i}")
                    if rec.new_catalysts:
                        st.markdown("**🚀 New catalysts**")
                        for i in rec.new_catalysts:
                            st.markdown(f"- {i}")
                with nc2:
                    if rec.what_weakened:
                        st.markdown("**⚠️ Weakened**")
                        for i in rec.what_weakened:
                            st.markdown(f"- {i}")
                    if rec.new_concerns:
                        st.markdown("**🔴 New concerns**")
                        for i in rec.new_concerns:
                            st.markdown(f"- {i}")


def render_filing_card(
    filing: Filing,
    company_name: str,
    ticker: str,
    index: int,
    previous_filing: Filing | None = None,
) -> None:
    with st.container(border=True):
        col_left, col_mid, col_right = st.columns([3, 1, 1])
        with col_left:
            st.markdown(f"**{filing.form_type} #{index}**")
            st.write(f"📅 Filed: **{filing.filing_date}**")
            if filing.report_date != "N/A":
                st.write(f"📆 Period: {filing.report_date}")
            st.caption(f"Accession: {filing.accession}")
            if previous_filing:
                st.caption(f"📊 Comparison: vs. {previous_filing.filing_date}")
        with col_mid:
            st.link_button("View on SEC.gov", filing.url, use_container_width=True)
        with col_right:
            analyze_key = f"analyze_{filing.accession}"
            result_key  = f"result_{filing.accession}"
            has_prev    = previous_filing is not None
            btn_label   = (
                "🧪 Demo Analysis" if (demo_mode and not _ai_ready)
                else ("Analyze + Compare" if has_prev else "Analyze Filing")
            )

            if st.button(
                btn_label,
                key=analyze_key,
                use_container_width=True,
                disabled=not _analyze_enabled,
                help=None if _analyze_enabled else "Enable Demo Mode or add OPENAI_API_KEY",
            ):
                st.session_state[result_key] = None
                spinner_msg = (
                    "Loading demo analysis…" if demo_mode
                    else ("Fetching & comparing filings…" if has_prev else "Fetching and analysing filing…")
                )
                with st.spinner(spinner_msg):
                    result = analyze_filing(
                        filing_url=filing.url,
                        form_type=filing.form_type,
                        company_name=company_name,
                        st_secrets=_st_secrets(),
                        demo_mode=demo_mode,
                        cache_key=filing.accession,
                        previous_filing_url=previous_filing.url if previous_filing else None,
                        previous_cache_key=previous_filing.accession if previous_filing else None,
                    )
                    st.session_state[result_key] = result

                    if result.what_changed:
                        adj = result.comparison.conviction_adjustment if result.comparison else 0
                        _entry, delta = update_portfolio(
                            ticker, company_name, result, filing.form_type,
                            conviction_adjustment=adj,
                        )

                        # Save comparison record if we have comparison data
                        if result.comparison:
                            rec = build_comparison_record(
                                ticker=ticker,
                                company_name=company_name,
                                filing_type=filing.form_type,
                                accession=filing.accession,
                                comparison=result.comparison,
                            )
                            save_comparison(rec)

                        # Toast
                        red_alerts = [
                            _ALERT_DISPLAY[a][1]
                            for a in delta.alerts
                            if a in _ALERT_DISPLAY and _ALERT_DISPLAY[a][0] == "🔴"
                        ]
                        if red_alerts:
                            st.toast(f"⚠️ {ticker}: {', '.join(red_alerts)}", icon="🔴")
                        elif adj != 0:
                            sign = "+" if adj > 0 else ""
                            st.toast(f"Portfolio updated · conviction {sign}{adj}", icon="💾")
                        else:
                            st.toast(f"Portfolio updated for {ticker}", icon="💾")

        if st.session_state.get(result_key) is not None:
            st.divider()
            render_analysis(st.session_state[result_key])


def render_section(
    form_type: str,
    filings: list[Filing],
    company_name: str,
    ticker: str,
    label: str,
) -> None:
    st.subheader(label)
    if not filings:
        st.warning(f"No {form_type} filings found.")
        return
    for idx, filing in enumerate(filings):
        # filings are newest-first; filings[idx+1] is the previous one
        prev = filings[idx + 1] if idx + 1 < len(filings) else None
        render_filing_card(filing, company_name, ticker, idx + 1, previous_filing=prev)


# ── Portfolio Dashboard ───────────────────────────────────────────────────────
def render_portfolio_dashboard() -> None:
    portfolio    = load_portfolio()
    delta_hist   = load_delta_history()
    compare_hist = load_comparison_history()

    # ── 1. Current Portfolio State ────────────────────────────────────────────
    st.header("📊 Portfolio State")

    if not portfolio:
        st.info(
            "No tickers tracked yet. Search for a company and click "
            "**Analyze Filing** to start tracking.",
            icon="💡",
        )
    else:
        st.caption(f"{len(portfolio)} ticker(s) tracked")
        for ticker, entry in sorted(portfolio.items()):
            t_icon = _IMPACT_COLOR.get(entry.thesis_status, "⚪")
            a_icon = _ACTION_COLOR.get(entry.recommended_action, "⚪")

            with st.container(border=True):
                hcol1, hcol2, hcol3 = st.columns([2, 3, 1])
                with hcol1:
                    st.markdown(f"### {ticker}")
                    st.caption(entry.company_name)
                with hcol2:
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric("Thesis",     f"{t_icon} {entry.thesis_status}")
                    mc2.metric("Action",     f"{a_icon} {entry.recommended_action}")
                    mc3.metric("Conviction", f"{entry.conviction_score}/100")
                with hcol3:
                    st.caption(f"Last: {entry.last_filing_type}")
                    st.caption(f"Updated: {entry.last_updated}")
                    if st.button("🗑️ Remove", key=f"del_{ticker}", use_container_width=True):
                        delete_ticker(ticker)
                        st.rerun()

                with st.expander("Catalysts & Risks"):
                    cl, cr = st.columns(2)
                    with cl:
                        st.markdown("**Key Catalysts**")
                        for c in entry.catalysts:
                            st.markdown(f"- {c}")
                    with cr:
                        st.markdown("**Key Risks**")
                        for r in entry.risks:
                            st.markdown(f"- {r}")
                    st.caption(f"Analyses run: {entry.analyses_count}")

    # ── 2. Historical Delta Analysis ──────────────────────────────────────────
    st.divider()
    st.header("📈 Historical Delta Analysis")
    st.caption("Filing-over-filing comparisons: revenue, margins, cash, debt, tone, guidance")

    if not compare_hist:
        st.info(
            "No comparisons yet. Click **Analyze + Compare** on any filing "
            "(available when at least 2 filings of the same type exist).",
            icon="📭",
        )
    else:
        cf1, cf2 = st.columns([2, 1])
        with cf1:
            cmp_filter = st.selectbox(
                "Filter by ticker",
                options=["All"] + sorted({r.ticker for r in compare_hist}),
                key="cmp_filter_ticker",
            )
        with cf2:
            cmp_adj_only = st.toggle(
                "Conviction changes only",
                value=False,
                key="cmp_adj_only",
            )

        filtered_cmp = [
            r for r in compare_hist
            if (cmp_filter == "All" or r.ticker == cmp_filter)
            and (not cmp_adj_only or r.conviction_adjustment != 0)
        ]

        if not filtered_cmp:
            st.info("No records match the current filter.")
        else:
            st.caption(f"Showing {len(filtered_cmp)} of {len(compare_hist)} comparison(s)")
            for rec in filtered_cmp:
                render_comparison_card(rec)

    # ── 3. Recent Changes (Delta Engine) ─────────────────────────────────────
    st.divider()
    st.header("🔄 Recent Changes")

    if not delta_hist:
        st.info("No change history yet. Run an analysis to start tracking deltas.", icon="📭")
        return

    fc1, fc2 = st.columns([2, 1])
    with fc1:
        filter_ticker = st.selectbox(
            "Filter by ticker",
            options=["All"] + sorted({d.ticker for d in delta_hist}),
            key="delta_filter_ticker",
        )
    with fc2:
        alerts_only = st.toggle("Alerts only", value=False, key="delta_alerts_only")

    filtered = [
        d for d in delta_hist
        if (filter_ticker == "All" or d.ticker == filter_ticker)
        and (not alerts_only or d.alerts)
    ]

    if not filtered:
        st.info("No records match the current filter.")
        return

    st.caption(f"Showing {len(filtered)} of {len(delta_hist)} record(s)")
    for d in filtered:
        render_delta_card(d)


# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("📋 SEC EDGAR Filing Research")
st.caption(
    "Look up SEC filings · AI analysis · Filing comparison · Portfolio state · Delta intelligence"
)

tab_search, tab_portfolio = st.tabs(["🔍 Filing Search", "📊 Portfolio & Changes"])

with tab_portfolio:
    render_portfolio_dashboard()

with tab_search:
    st.divider()

    col_input, col_btn = st.columns([3, 1])
    with col_input:
        ticker_input = st.text_input(
            "Stock Ticker Symbol",
            placeholder="e.g. AAPL, MSFT, VCYT",
            label_visibility="collapsed",
        ).strip().upper()
    with col_btn:
        search_clicked = st.button("Search", type="primary", use_container_width=True)

    if search_clicked or ticker_input:
        if not ticker_input:
            st.error("Please enter a ticker symbol.")
            st.stop()

        with st.spinner(f"Looking up {ticker_input}…"):
            try:
                company = lookup_company(ticker_input)
            except EdgarAPIError as e:
                st.error(str(e))
                st.stop()

        st.divider()
        st.markdown(f"### {company.name}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Ticker", company.ticker)
        col2.metric("CIK", company.cik)
        col3.metric("Filings Source", "SEC EDGAR")
        st.divider()

        with st.spinner("Fetching filings from SEC EDGAR…"):
            results: dict[str, list[Filing]] = {}
            fetch_errors: dict[str, str] = {}
            for form_type, cfg in FILING_TYPES.items():
                try:
                    results[form_type] = get_filings(company, form_type, limit=cfg["limit"])
                except EdgarAPIError as e:
                    results[form_type] = []
                    fetch_errors[form_type] = str(e)

        for form_type, msg in fetch_errors.items():
            st.warning(f"Could not fetch {form_type} filings: {msg}")

        filing_tabs = st.tabs([cfg["label"] for cfg in FILING_TYPES.values()])
        for ftab, (form_type, cfg) in zip(filing_tabs, FILING_TYPES.items()):
            with ftab:
                render_section(
                    form_type=form_type,
                    filings=results.get(form_type, []),
                    company_name=company.name,
                    ticker=company.ticker,
                    label=cfg["label"],
                )

    else:
        st.info(
            "Enter a US stock ticker above (e.g. **AAPL**, **MSFT**, **VCYT**) "
            "and press **Search** to view the latest SEC filings."
        )
        with st.expander("What are these filings?"):
            st.markdown("""
| Form | Name | Description |
|------|------|-------------|
| **10-K** | Annual Report | Comprehensive yearly financial report |
| **10-Q** | Quarterly Report | Unaudited financial report filed each quarter |
| **8-K** | Current Report | Material events (earnings, mergers, leadership changes) |
            """)
