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
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import streamlit as st

from edgar import EdgarAPIError, get_filings, lookup_company
from edgar.filings import Filing
from ai.analyzer import AnalysisResult, analyze_filing, get_api_key
from ai.cache import DAILY_LIMIT, cache_size, get_today_count
from ai.evidence import CONFIDENCE_BADGE, FIELD_LABELS, evidence_by_field
from ai.uploader import (
    SOURCE_ICON, SOURCE_LABELS,
    analyze_uploaded, extract_text,
)
from ai.valuation import DRIVER_DISPLAY, VALUATION_IMPACT_BADGE
from ai.explainability import (  # noqa: E402 — kept after valuation import
    CAUSE_DISPLAY,
    EXPLAINABILITY_TOPICS,
    UNCERTAINTY_BADGE as EXPLAIN_BADGE,
)
from ai.market_intel import (
    analyze_market_intel,
    ALIGNMENT_BADGE,
    MISPRICING_BADGE,
    DETECTION_ICON,
    DETECTION_TAXONOMY,
    INTEL_CATEGORIES,
    INTEL_CATEGORY_ICON,
    INTEL_VIEW_BADGE,
    INTEL_SOURCE_TYPES,
    MarketIntelResult,
)
from command_center import render_command_center_tab
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
    # ── Source + status banner ────────────────────────────────────────────────
    src_icon  = SOURCE_ICON.get(result.source_label, "📄") if result.source_label not in ("SEC", "") else "🏛️"
    src_label = result.source_label or "SEC"
    st.caption(f"{src_icon} Source: **{src_label}**")

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
    elif result.error:
        # Non-fatal notice (e.g. truncation warning)
        st.warning(result.error, icon="⚠️")

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

    # ── Damodaran Value Driver Analysis ───────────────────────────────────────
    if result.valuation:
        _render_valuation_section(result.valuation)

    # ── Explainability & Uncertainty Layer ────────────────────────────────────
    if result.uncertainty:
        _render_explainability_section(result.uncertainty)


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


def _render_valuation_section(val) -> None:
    """Render the Damodaran Value Driver Analysis section."""
    from ai.valuation import DRIVER_DISPLAY, VALUATION_IMPACT_BADGE

    v_icon, v_label = VALUATION_IMPACT_BADGE.get(
        val.valuation_impact, ("❓", val.valuation_impact)
    )
    priority = val.priority_score

    # Priority colour
    if priority >= 65:
        p_color = "🟢"
    elif priority >= 35:
        p_color = "🟡"
    else:
        p_color = "🔴"

    st.divider()
    with st.expander(
        f"📈 Damodaran Value Driver Analysis — {v_icon} {v_label} · "
        f"Priority {p_color} {priority}/100"
    ):
        st.caption(
            "Every conclusion is grounded in evidence from the filing. "
            "Priority = Thesis × Valuation × Risk × Confidence."
        )

        # ── 8-driver grid (4 columns × 2 rows) ───────────────────────────────
        drivers = val.drivers
        cols = st.columns(4)
        for idx, (field_attr, notes_attr, label, icon_map) in enumerate(DRIVER_DISPLAY):
            rating = getattr(drivers, field_attr, "—")
            notes  = getattr(drivers, notes_attr, "")
            icon   = icon_map.get(rating, "❓")
            with cols[idx % 4]:
                st.metric(label, f"{icon} {rating}")
                if notes:
                    st.caption(notes)

        # ── Valuation impact + priority ───────────────────────────────────────
        st.divider()
        pi1, pi2 = st.columns([2, 1])
        with pi1:
            st.markdown(f"**Overall Valuation Impact:** {v_icon} **{v_label}**")
        with pi2:
            st.metric(
                "Priority Score",
                f"{p_color} {priority} / 100",
                help=(
                    "Priority = Thesis × Valuation × Risk Factor × Confidence. "
                    "High score = event likely to move intrinsic value meaningfully."
                ),
            )

        # ── Reasoning bullets ─────────────────────────────────────────────────
        if val.valuation_reasoning:
            st.markdown("**Valuation Reasoning** *(evidence-grounded)*")
            for reason in val.valuation_reasoning:
                st.markdown(f"- {reason}")


def _render_explainability_section(unc) -> None:
    """Render the Explainability & Uncertainty Layer section."""
    icon, label = EXPLAIN_BADGE.get(unc.overall_uncertainty, ("❓", unc.overall_uncertainty))
    overconf_warn = " ⚠️ Overconfidence flag" if unc.overconfidence_flag else ""

    st.divider()
    with st.expander(
        f"🔍 Explainability & Uncertainty — {icon} {label}{overconf_warn}",
        expanded=False,
    ):
        st.caption(
            "Every conclusion is explained: what the system believes, why, "
            "which assumptions were made, and what evidence is missing."
        )

        # ── Overall uncertainty + causes ──────────────────────────────────────
        row1, row2 = st.columns([2, 3])
        with row1:
            st.metric("Overall Uncertainty", f"{icon} {label}")

        with row2:
            if unc.uncertainty_causes:
                st.markdown("**Detected uncertainty sources:**")
                cause_chips = "  ".join(
                    f"`{CAUSE_DISPLAY.get(c, ('⚠️', c))[0]} {CAUSE_DISPLAY.get(c, ('⚠️', c))[1]}`"
                    for c in unc.uncertainty_causes
                )
                st.markdown(cause_chips)
            else:
                st.markdown("*No significant uncertainty sources detected.*")

        # ── Overconfidence warning ────────────────────────────────────────────
        if unc.overconfidence_flag:
            st.warning(
                "**Overconfidence flag:** Management language is more positive than the "
                "numerical evidence supports. Treat qualitative conclusions with extra caution.",
                icon="⚠️",
            )

        # ── What Could Break This Thesis? ─────────────────────────────────────
        if unc.what_could_break:
            st.divider()
            st.markdown("#### 🔥 What Could Break This Thesis?")
            st.caption(
                "Specific, falsifiable scenarios that would directly contradict the "
                "evidence used to reach the current conclusion."
            )
            for scenario in unc.what_could_break:
                st.markdown(f"- {scenario}")

        # ── What Would Change Our View? ───────────────────────────────────────
        if unc.what_would_change_view:
            st.divider()
            st.markdown("#### 🔄 What Would Change Our View?")
            st.caption(
                "Concrete future data points or events that would trigger an "
                "upgrade or downgrade of this analysis."
            )
            for trigger in unc.what_would_change_view:
                st.markdown(f"- {trigger}")

        # ── Per-topic explainability cards (2 × 2 grid) ───────────────────────
        if unc.cards:
            st.divider()
            st.markdown("#### 🃏 Conclusion Explainability Cards")
            st.caption(
                "Four key conclusions explained in detail — reasoning, assumptions, "
                "strongest evidence, and what data is weak or missing."
            )
            cols = st.columns(2)
            for idx, card in enumerate(unc.cards):
                topic_label = EXPLAINABILITY_TOPICS.get(card.topic, card.topic.replace("_", " ").title())
                c_icon, c_label = EXPLAIN_BADGE.get(card.uncertainty, ("❓", card.uncertainty))

                with cols[idx % 2]:
                    with st.container(border=True):
                        st.markdown(f"**{topic_label}** — {c_icon} {c_label}")

                        st.markdown("**Why we believe this:**")
                        st.markdown(card.reasoning)

                        if card.assumptions:
                            st.markdown("**Assumptions:**")
                            for assumption in card.assumptions:
                                st.markdown(f"- *{assumption}*")

                        st.markdown("**Strongest evidence:**")
                        st.success(card.strongest_evidence, icon="✅")

                        st.markdown("**Weak or missing evidence:**")
                        st.info(card.weak_evidence, icon="⚠️")


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
    from portfolio import (
        load_holdings, upsert_holding, MARKETS, DEFAULT_SECTORS,
    )
    portfolio    = load_portfolio()
    delta_hist   = load_delta_history()
    compare_hist = load_comparison_history()
    holdings     = load_holdings()

    # ── 1. Research Watchlist ─────────────────────────────────────────────────
    st.header("🔬 Research Watchlist")
    st.caption(
        "Tickers you've researched — *not* positions you own. "
        "Use **💼 Add to Holdings** to record actual ownership."
    )

    if not portfolio:
        st.info(
            "No tickers researched yet. Search for a company and click "
            "**Analyze Filing** to start tracking.",
            icon="💡",
        )
    else:
        st.caption(f"{len(portfolio)} ticker(s) on watchlist")
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
                    src = getattr(entry, "source_label", "SEC") or "SEC"
                    src_ico = SOURCE_ICON.get(src, "📄") if src != "SEC" else "🏛️"
                    st.caption(f"{src_ico} {src}")
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

                # ── Add to Holdings ────────────────────────────────────────
                existing_h = holdings.get(ticker)
                badge = (f"  ·  ✅ Held ({existing_h.quantity:g} sh @ "
                         f"${existing_h.avg_cost:.2f})") if existing_h else ""
                with st.expander(f"💼 Add to Holdings{badge}", expanded=False):
                    with st.form(f"add_holding_{ticker}", clear_on_submit=False):
                        f1, f2 = st.columns(2)
                        with f1:
                            qty = st.number_input(
                                "Quantity (shares)", min_value=0.0, step=1.0,
                                value=float(existing_h.quantity) if existing_h else 0.0,
                                key=f"qty_{ticker}",
                            )
                            avg_cost = st.number_input(
                                "Average cost ($/share)", min_value=0.0, step=0.01,
                                value=float(existing_h.avg_cost) if existing_h else 0.0,
                                format="%.2f", key=f"cost_{ticker}",
                            )
                            cur_price = st.number_input(
                                "Current price ($/share, optional)", min_value=0.0, step=0.01,
                                value=float(existing_h.current_price) if existing_h else 0.0,
                                format="%.2f", key=f"price_{ticker}",
                            )
                        with f2:
                            mkt_default = existing_h.market if existing_h else "US"
                            sec_default = existing_h.sector if existing_h else "Other"
                            mkt = st.selectbox(
                                "Market", MARKETS,
                                index=MARKETS.index(mkt_default) if mkt_default in MARKETS else 0,
                                key=f"mkt_{ticker}",
                            )
                            sec = st.selectbox(
                                "Sector", DEFAULT_SECTORS,
                                index=DEFAULT_SECTORS.index(sec_default) if sec_default in DEFAULT_SECTORS else len(DEFAULT_SECTORS)-1,
                                key=f"sec_{ticker}",
                            )
                        verb = "Update Holding" if existing_h else "Add to Holdings"
                        if st.form_submit_button(f"💼 {verb}", type="primary"):
                            upsert_holding(
                                ticker=ticker,
                                company_name=entry.company_name,
                                market=mkt,
                                sector=sec,
                                quantity=qty,
                                avg_cost=avg_cost,
                                current_price=cur_price,
                            )
                            st.toast(f"{ticker} saved to Holdings", icon="💼")
                            st.rerun()

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


# ── Market Intelligence Tab ───────────────────────────────────────────────────

def _render_market_intel_results(result: MarketIntelResult) -> None:
    """Render the full market intelligence reconciliation UI."""
    align_icon, align_label = ALIGNMENT_BADGE.get(
        result.reconciliation.alignment_label, ("❓", result.reconciliation.alignment_label)
    )
    mis_icon, mis_label = MISPRICING_BADGE.get(
        result.reconciliation.potential_mispricing, ("❓", result.reconciliation.potential_mispricing)
    )
    score = result.reconciliation.consensus_alignment_score

    # ── Score colour ──────────────────────────────────────────────────────────
    if score >= 80:
        score_prefix = "🟢"
    elif score >= 60:
        score_prefix = "🔵"
    elif score >= 40:
        score_prefix = "🟡"
    elif score >= 20:
        score_prefix = "🟠"
    else:
        score_prefix = "🔴"

    st.subheader("🌐 Market vs Thesis Reconciliation")
    st.caption(
        "⚠️ **External intelligence is advisory only.** "
        "It is classified and compared against the filing-based thesis — never overrides it."
    )

    # ── Top metrics row ───────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Consensus Alignment", f"{score_prefix} {score}/100")
    with m2:
        st.metric("Alignment Label", f"{align_icon} {align_label}")
    with m3:
        st.metric("Mispricing Signal", f"{mis_icon} {mis_label}")
    with m4:
        st.metric("Internal Thesis", f"{result.internal_thesis_impact} / {result.internal_action}")

    # ── No internal basis warning ─────────────────────────────────────────────
    if not result.has_internal_basis:
        st.warning(
            "No prior filing analysis found for this ticker. "
            "Reconciliation accuracy is limited — run a filing analysis first for a grounded baseline.",
            icon="⚠️",
        )

    # ── Detected conditions ───────────────────────────────────────────────────
    if result.reconciliation.detections:
        st.divider()
        st.markdown("**Detected Market Conditions:**")
        det_cols = st.columns(min(len(result.reconciliation.detections), 3))
        for idx, det in enumerate(result.reconciliation.detections):
            icon = DETECTION_ICON.get(det, "🔎")
            with det_cols[idx % 3]:
                st.info(f"{icon} {det}")

    # ── Market view summary ───────────────────────────────────────────────────
    if result.reconciliation.market_view_summary:
        st.divider()
        st.markdown("**External Market View Summary:**")
        st.markdown(f"> {result.reconciliation.market_view_summary}")

    # ── Mispricing rationale ──────────────────────────────────────────────────
    if result.reconciliation.mispricing_rationale:
        st.markdown(f"**Mispricing Rationale:** {result.reconciliation.mispricing_rationale}")

    # ── Classified intelligence cards ─────────────────────────────────────────
    if result.classified:
        st.divider()
        st.markdown("#### Classified Intelligence")
        st.caption("Each block of external intelligence classified by type and directional view.")
        card_cols = st.columns(2)
        for idx, item in enumerate(result.classified):
            cat_label = INTEL_CATEGORIES.get(item.category, item.category.replace("_", " ").title())
            cat_icon  = INTEL_CATEGORY_ICON.get(item.category, "📄")
            v_icon, v_label = INTEL_VIEW_BADGE.get(item.view, ("❓", item.view))
            with card_cols[idx % 2]:
                with st.container(border=True):
                    st.markdown(f"**{cat_icon} {cat_label}** — {v_icon} {v_label}")
                    st.markdown(item.summary)
                    if item.key_points:
                        for pt in item.key_points:
                            st.markdown(f"- {pt}")

    # ── Reconciliation notes ──────────────────────────────────────────────────
    if result.reconciliation.reconciliation_notes:
        st.divider()
        st.markdown("#### Reconciliation Notes")
        st.caption("Where the external market view and the internal filing thesis agree or diverge.")
        for note in result.reconciliation.reconciliation_notes:
            if note.startswith("ALIGNED:"):
                st.success(note, icon="✅")
            elif note.startswith("DIVERGENT:"):
                st.error(note, icon="❌")
            elif note.startswith("WATCH:"):
                st.warning(note, icon="⚠️")
            else:
                st.markdown(f"- {note}")

    # ── Source snippet ────────────────────────────────────────────────────────
    if result.source_snippet:
        with st.expander("📄 Source text preview"):
            st.caption(result.source_snippet + ("…" if len(result.source_snippet) >= 300 else ""))


def render_market_intel_tab() -> None:
    """Render the Market Intelligence tab."""
    st.subheader("🌐 External Market Intelligence")
    st.caption(
        "Paste or upload an external report — InvestingPro summary, analyst note, "
        "valuation analysis, or technical summary. The AI classifies the intelligence "
        "and reconciles it against your internal filing thesis. "
        "External reports never override grounded filing evidence."
    )

    # ── Ticker + company ──────────────────────────────────────────────────────
    portfolio = load_portfolio()
    portfolio_tickers = sorted(portfolio.keys()) if portfolio else []

    st.divider()
    mc1, mc2 = st.columns(2)
    with mc1:
        if portfolio_tickers:
            ticker_options = ["— Enter manually —"] + portfolio_tickers
            selected = st.selectbox(
                "Select Portfolio Ticker",
                ticker_options,
                help="Select a ticker with a prior filing analysis for full reconciliation.",
            )
            if selected == "— Enter manually —":
                mi_ticker = st.text_input(
                    "Ticker Symbol",
                    placeholder="e.g. AAPL, MSFT",
                ).strip().upper()
            else:
                mi_ticker = selected
        else:
            mi_ticker = st.text_input(
                "Ticker Symbol",
                placeholder="e.g. AAPL, MSFT",
                help="Run a filing analysis first for full reconciliation.",
            ).strip().upper()

    with mc2:
        mi_company = st.text_input(
            "Company Name",
            placeholder="e.g. Apple Inc.",
        ).strip()

    mi_source = st.selectbox("Source Type", INTEL_SOURCE_TYPES)

    # ── Internal thesis context (from portfolio) ──────────────────────────────
    internal_thesis: dict | None = None
    if mi_ticker and mi_ticker in portfolio:
        entry = portfolio[mi_ticker]
        # Safely read fields — guard against any schema variation
        thesis  = getattr(entry, "thesis_status",      getattr(entry, "thesis_impact",    "Unknown"))
        action  = getattr(entry, "recommended_action",  getattr(entry, "suggested_action", "Unknown"))
        score   = getattr(entry, "conviction_score",    getattr(entry, "confidence_score", 0))
        cats    = getattr(entry, "catalysts",           getattr(entry, "key_catalysts",    []))
        rsks    = getattr(entry, "risks",               getattr(entry, "key_risks",        []))
        internal_thesis = {
            "thesis_impact":    thesis,
            "suggested_action": action,
            "confidence_score": score,
            "key_catalysts":    cats,
            "key_risks":        rsks,
        }
        st.divider()
        ctx1, ctx2, ctx3 = st.columns(3)
        with ctx1:
            st.metric("Internal Thesis", thesis)
        with ctx2:
            st.metric("Internal Action", action)
        with ctx3:
            st.metric("Internal Confidence", f"{score}/100")
        st.caption(
            f"Using filing analysis for **{mi_ticker}** ({entry.company_name}) as the baseline. "
            "External intelligence will be reconciled against this thesis."
        )
    elif mi_ticker:
        st.info(
            f"No filing analysis found for **{mi_ticker}** in your portfolio. "
            "Run a Filing Search analysis first for full reconciliation. "
            "Classification-only mode will still work.",
            icon="ℹ️",
        )

    # ── Intelligence input ────────────────────────────────────────────────────
    st.divider()
    input_mode = st.radio(
        "Input method",
        ["📋 Paste text", "📎 Upload file (PDF / TXT)"],
        horizontal=True,
        label_visibility="collapsed",
    )

    mi_text = ""
    if input_mode == "📋 Paste text":
        mi_text = st.text_area(
            "Paste external intelligence here",
            height=220,
            placeholder=(
                "Paste an InvestingPro summary, analyst note, valuation table, "
                "technical analysis, or any market commentary…"
            ),
            label_visibility="collapsed",
        ).strip()
    else:
        mi_upload = st.file_uploader(
            "Upload file",
            type=["pdf", "txt"],
            label_visibility="collapsed",
            help="PDF or plain text files. Text-based PDFs work best.",
        )
        if mi_upload:
            with st.spinner("Extracting text…"):
                try:
                    mi_text, _ = extract_text(mi_upload)
                except Exception as exc:
                    st.error(f"Could not extract text: {exc}")
            if mi_text:
                st.caption(f"✅ {len(mi_text):,} characters extracted from **{mi_upload.name}**")

    # ── Analyse button ────────────────────────────────────────────────────────
    st.divider()
    btn_label = (
        "🧪 Demo Intelligence Analysis" if (demo_mode and not _ai_ready)
        else "Analyze Intelligence"
    )
    can_analyze = bool(mi_ticker and (mi_text or (demo_mode and not _ai_ready)))
    if not mi_ticker:
        st.caption("Enter a ticker symbol to enable analysis.")

    if st.button(
        btn_label,
        type="primary",
        disabled=not (can_analyze or (demo_mode and not _ai_ready)),
        use_container_width=False,
    ):
        with st.spinner("Classifying intelligence and reconciling with thesis…"):
            mi_result = analyze_market_intel(
                text=mi_text,
                ticker=mi_ticker or "DEMO",
                company_name=mi_company or mi_ticker or "Demo Company",
                source_type=mi_source,
                internal_thesis=internal_thesis,
                st_secrets=_st_secrets(),
                demo_mode=(demo_mode and not _ai_ready),
            )
        st.session_state["market_intel_result"] = mi_result
        # Persist alignment score per ticker so the Portfolio Risk Engine can
        # use it across sessions. Best-effort; never crash the UI.
        if mi_ticker:
            try:
                from portfolio import save_market_intel_for_ticker
                # Compute the dominant external view by counting classified votes
                view_votes: dict[str, int] = {}
                for c in getattr(mi_result, "classified", []) or []:
                    v = getattr(c, "view", "") or ""
                    if v:
                        view_votes[v] = view_votes.get(v, 0) + 1
                dominant_view = (max(view_votes, key=view_votes.get)
                                 if view_votes else "Neutral")
                save_market_intel_for_ticker(
                    ticker=mi_ticker,
                    alignment_score=int(getattr(mi_result.reconciliation,
                                                "consensus_alignment_score", 0) or 0),
                    alignment_label=getattr(mi_result.reconciliation,
                                            "alignment_label", "No Baseline"),
                    dominant_view=dominant_view,
                    mispricing=getattr(mi_result.reconciliation,
                                       "potential_mispricing", "") or "",
                )
            except Exception:
                pass
        st.toast(f"Intelligence classified for {mi_ticker or 'DEMO'}", icon="🌐")

    # ── Results ───────────────────────────────────────────────────────────────
    if st.session_state.get("market_intel_result") is not None:
        r: MarketIntelResult = st.session_state["market_intel_result"]
        st.divider()
        _render_market_intel_results(r)

    # ── Tips ──────────────────────────────────────────────────────────────────
    if not st.session_state.get("market_intel_result"):
        with st.expander("💡 What can I paste here?"):
            st.markdown("""
| Source | What to paste |
|--------|--------------|
| **InvestingPro** | The AI summary, fair value estimate, financial health score |
| **Analyst reports** | The key thesis, price target, rating rationale |
| **Valuation summaries** | DCF assumptions, comparable multiples, target range |
| **Technical analysis** | RSI, moving averages, support/resistance levels, trend summary |
| **News & commentary** | Relevant articles, earnings call summaries, macro commentary |

**Tips:**
- More text = better classification. Include analyst names, targets, and rationales if available.
- The system works best when you paste the full summary, not just a headline.
- External intelligence never replaces the SEC filing analysis — it enriches it.
            """)


# ── Upload Filing Tab ─────────────────────────────────────────────────────────

_UPLOAD_DOC_TYPES = [
    "10-K",
    "10-Q",
    "8-K",
    "Earnings Presentation",
    "Analyst Report",
    "Tadawul Announcement",
    "Annual Report",
    "Other",
]

_UPLOAD_SOURCES = {
    "SEC Filing":               "sec",
    "Uploaded Report":          "uploaded_report",
    "Tadawul Announcement":     "tadawul",
    "Analyst Report":           "analyst_report",
    "Earnings Presentation":    "earnings_presentation",
}


def render_portfolio_risk_tab() -> None:
    """Portfolio Risk Engine dashboard — operates on Actual Holdings only."""
    from portfolio import (
        RISK_REGIME_BADGE,
        build_positions,
        compute_portfolio_risk,
        load_holdings,
        load_market_intel_state,
        load_portfolio,
    )
    import pandas as pd

    st.header("🛡️ Portfolio Risk Engine")
    st.caption(
        "Investment-risk view (not price volatility) over **Actual Holdings**. "
        "Weights are derived from market value. Enriched with research watchlist "
        "and market intel where available."
    )

    holdings  = load_holdings()
    watchlist = load_portfolio()
    mi_state  = load_market_intel_state()

    if not holdings:
        st.info(
            "No actual holdings yet. Open the **💼 Holdings** tab to record "
            "positions, or click **💼 Add to Holdings** on any watchlist entry "
            "in the **🔬 Research Watchlist** tab.",
            icon="💡",
        )
        return

    positions = build_positions(holdings, watchlist, mi_state)
    result    = compute_portfolio_risk(positions)

    # ── Risk score header ─────────────────────────────────────────────────────
    icon, label = RISK_REGIME_BADGE.get(result.risk_regime, ("⚪", result.risk_regime))
    score_cols = st.columns([1, 1, 1, 1])
    with score_cols[0]:
        st.metric("Portfolio Risk Score", f"{result.risk_score}/100")
    with score_cols[1]:
        st.metric("Risk Regime", f"{icon} {label}")
    with score_cols[2]:
        st.metric("Positions", result.n_positions)
    with score_cols[3]:
        st.metric("Total Market Value", f"${result.total_market_value:,.2f}")

    st.progress(result.risk_score / 100.0)

    # ── 3. Category breakdown ─────────────────────────────────────────────────
    st.subheader("🧮 Risk Category Breakdown")
    cat_rows = []
    for c in result.categories:
        cat_rows.append({
            "Category": c.name,
            "Score":    c.score,
            "Detail":   c.detail,
        })
    cat_df = pd.DataFrame(cat_rows)
    st.dataframe(
        cat_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d",
            ),
        },
    )

    with st.expander("🔎 Per-category contributors", expanded=False):
        for c in result.categories:
            st.markdown(f"**{c.name}** — score {c.score}/100")
            if c.contributors:
                for note in c.contributors:
                    st.markdown(f"  · {note}")
            else:
                st.markdown("  · _No data available for this category yet._")

    # ── 4. Top 5 risks ────────────────────────────────────────────────────────
    st.subheader("⚠️ Top 5 Portfolio Risks")
    for i, risk in enumerate(result.top_risks, start=1):
        st.markdown(f"**{i}.** {risk}")

    # ── 5. Top 5 actions ──────────────────────────────────────────────────────
    st.subheader("🎯 Top 5 Required Actions")
    for i, action in enumerate(result.required_actions, start=1):
        st.markdown(f"**{i}.** {action}")

    # ── Position detail table ─────────────────────────────────────────────────
    with st.expander("📊 Full position detail (all intelligence signals)", expanded=False):
        detail_rows = []
        for p in positions:
            mi_score = (f"{p.market_alignment_score}/100"
                        if p.market_alignment_score >= 0 else "—")
            detail_rows.append({
                "Ticker":      p.ticker,
                "Weight %":    round(p.weight_pct, 2),
                "Mkt Value":   round(p.market_value, 2),
                "Market":      p.market,
                "Sector":      p.sector,
                "Thesis":      p.thesis_status,
                "Conviction":  p.conviction_score,
                "Action":      p.recommended_action,
                "Valuation":   p.valuation_impact,
                "Priority":    p.priority_score if p.priority_score > 0 else "—",
                "Uncertainty": p.uncertainty_level,
                "Mkt Align":   mi_score,
            })
        st.dataframe(pd.DataFrame(detail_rows), hide_index=True, use_container_width=True)

    st.caption(f"Computed at {result.computed_at}")


def render_holdings_tab() -> None:
    """Actual Holdings + Transactions tab."""
    from portfolio import (
        DEFAULT_SECTORS, MARKETS,
        delete_holding,
        load_holdings, load_portfolio, load_transactions,
        portfolio_weights, record_transaction,
        total_cost_basis, total_market_value,
        update_current_price, upsert_holding,
    )
    import pandas as pd
    from datetime import date

    st.header("💼 Actual Holdings")
    st.caption(
        "Positions you actually own. Risk Engine reads from this tab. "
        "Watchlist tickers can be promoted via **💼 Add to Holdings** on the "
        "**🔬 Research Watchlist** tab."
    )

    holdings  = load_holdings()
    watchlist = load_portfolio()

    # ── Summary metrics ───────────────────────────────────────────────────────
    if holdings:
        mv     = total_market_value(holdings)
        cb     = total_cost_basis(holdings)
        pnl    = mv - cb
        pnl_pct = (pnl / cb * 100.0) if cb > 0 else 0.0
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Positions", len(holdings))
        m2.metric("Market Value", f"${mv:,.2f}")
        m3.metric("Cost Basis", f"${cb:,.2f}")
        m4.metric(
            "Unrealized P&L",
            f"${pnl:,.2f}",
            delta=f"{pnl_pct:+.2f}%",
        )
    else:
        st.info(
            "No holdings yet. Use the **➕ Add Holding** form below, record a "
            "**BUY** transaction, or click **💼 Add to Holdings** on a watchlist "
            "entry.",
            icon="💡",
        )

    # ── Holdings table with current-price editing ─────────────────────────────
    if holdings:
        st.subheader("📋 Holdings")
        st.caption(
            "Edit **Current Price** inline, then click **💾 Save prices**. "
            "Other fields are edited via **💼 Add to Holdings** on the Watchlist."
        )
        weights = portfolio_weights(holdings)
        rows = []
        for ticker, h in sorted(holdings.items()):
            rows.append({
                "Ticker":         ticker,
                "Company":        h.company_name,
                "Market":         h.market,
                "Sector":         h.sector,
                "Quantity":       round(h.quantity, 4),
                "Avg Cost":       round(h.avg_cost, 2),
                "Current Price":  round(h.current_price, 2),
                "Market Value":   round(h.market_value, 2),
                "Cost Basis":     round(h.cost_basis, 2),
                "Unreal. P&L":    round(h.unrealized_pnl, 2),
                "P&L %":          round(h.unrealized_pnl_pct, 2),
                "Weight %":       round(weights.get(ticker, 0.0), 2),
            })
        df = pd.DataFrame(rows)
        edited = st.data_editor(
            df,
            hide_index=True,
            use_container_width=True,
            disabled=["Ticker", "Company", "Market", "Sector", "Quantity",
                      "Avg Cost", "Market Value", "Cost Basis",
                      "Unreal. P&L", "P&L %", "Weight %"],
            column_config={
                "Current Price": st.column_config.NumberColumn(
                    "Current Price", min_value=0.0, step=0.01, format="%.2f",
                ),
            },
            key="holdings_price_editor",
        )
        save_cols = st.columns([1, 1, 4])
        with save_cols[0]:
            if st.button("💾 Save prices", type="primary", use_container_width=True):
                changed = 0
                for _, row in edited.iterrows():
                    new_price = float(row["Current Price"])
                    if abs(new_price - holdings[row["Ticker"]].current_price) > 1e-9:
                        update_current_price(row["Ticker"], new_price)
                        changed += 1
                st.toast(f"Updated {changed} price(s)", icon="💾")
                st.rerun()
        with save_cols[1]:
            del_ticker = st.selectbox(
                "Remove holding",
                options=["—"] + sorted(holdings.keys()),
                label_visibility="collapsed",
                key="del_holding_select",
            )
        if del_ticker and del_ticker != "—":
            if st.button(f"🗑️ Remove {del_ticker}", type="secondary"):
                delete_holding(del_ticker)
                st.toast(f"{del_ticker} removed", icon="🗑️")
                st.rerun()

    # ── Add Holding form ──────────────────────────────────────────────────────
    st.divider()
    with st.expander("➕ Add Holding (manual)", expanded=not holdings):
        with st.form("add_holding_manual", clear_on_submit=True):
            ah1, ah2 = st.columns(2)
            with ah1:
                # Suggest watchlist tickers but allow free text
                wl_options = sorted(watchlist.keys())
                if wl_options:
                    new_ticker_src = st.radio(
                        "Source",
                        options=["From Watchlist", "New Ticker"],
                        horizontal=True,
                        key="add_h_src",
                    )
                    if new_ticker_src == "From Watchlist":
                        new_ticker = st.selectbox("Ticker", options=wl_options, key="add_h_wl")
                        new_company = watchlist[new_ticker].company_name if new_ticker else ""
                    else:
                        new_ticker = st.text_input("Ticker", key="add_h_tk").strip().upper()
                        new_company = st.text_input("Company name", key="add_h_co")
                else:
                    new_ticker = st.text_input("Ticker", key="add_h_tk").strip().upper()
                    new_company = st.text_input("Company name", key="add_h_co")
                new_qty = st.number_input("Quantity", min_value=0.0, step=1.0, key="add_h_qty")
                new_cost = st.number_input(
                    "Avg cost ($/share)", min_value=0.0, step=0.01, format="%.2f", key="add_h_cost",
                )
                new_price = st.number_input(
                    "Current price ($/share)", min_value=0.0, step=0.01, format="%.2f", key="add_h_price",
                )
            with ah2:
                new_market = st.selectbox("Market", MARKETS, key="add_h_mkt")
                new_sector = st.selectbox("Sector", DEFAULT_SECTORS, key="add_h_sec")
            if st.form_submit_button("➕ Add holding", type="primary"):
                if not new_ticker:
                    st.error("Ticker is required.")
                elif new_qty <= 0:
                    st.error("Quantity must be greater than 0.")
                else:
                    upsert_holding(
                        ticker=new_ticker,
                        company_name=new_company or new_ticker,
                        market=new_market,
                        sector=new_sector,
                        quantity=new_qty,
                        avg_cost=new_cost,
                        current_price=new_price,
                    )
                    st.toast(f"{new_ticker} added to Holdings", icon="💼")
                    st.rerun()

    # ── Record Transaction form ───────────────────────────────────────────────
    with st.expander("🔁 Record Buy / Sell Transaction", expanded=False):
        with st.form("record_txn", clear_on_submit=True):
            t1, t2 = st.columns(2)
            with t1:
                # Source ticker
                all_tickers = sorted(set(holdings.keys()) | set(watchlist.keys()))
                if all_tickers:
                    txn_src = st.radio(
                        "Source",
                        options=["From Existing", "New Ticker"],
                        horizontal=True,
                        key="txn_src",
                    )
                    if txn_src == "From Existing":
                        txn_ticker = st.selectbox("Ticker", options=all_tickers, key="txn_tk_sel")
                    else:
                        txn_ticker = st.text_input("Ticker", key="txn_tk_txt").strip().upper()
                else:
                    txn_ticker = st.text_input("Ticker", key="txn_tk_txt").strip().upper()
                txn_side = st.radio("Side", options=["BUY", "SELL"], horizontal=True, key="txn_side")
                txn_qty  = st.number_input("Quantity", min_value=0.0, step=1.0, key="txn_qty")
                txn_price = st.number_input(
                    "Price ($/share)", min_value=0.0, step=0.01, format="%.2f", key="txn_price",
                )
            with t2:
                txn_date = st.date_input("Date", value=date.today(), key="txn_date")
                txn_notes = st.text_area("Notes (optional)", key="txn_notes", height=80)
                # Market / sector only used if BUY creates a new holding
                new_h_market = st.selectbox("Market (new holdings only)", MARKETS, key="txn_mkt")
                new_h_sector = st.selectbox("Sector (new holdings only)", DEFAULT_SECTORS, key="txn_sec")
            if st.form_submit_button("🔁 Record transaction", type="primary"):
                if not txn_ticker:
                    st.error("Ticker is required.")
                else:
                    # Get company name from watchlist or existing holding if available
                    company_name = ""
                    if txn_ticker in watchlist:
                        company_name = watchlist[txn_ticker].company_name
                    elif txn_ticker in holdings:
                        company_name = holdings[txn_ticker].company_name
                    else:
                        company_name = txn_ticker

                    txn, updated, err = record_transaction(
                        ticker=txn_ticker,
                        side=txn_side,
                        quantity=float(txn_qty),
                        price=float(txn_price),
                        txn_date=txn_date.isoformat(),
                        notes=txn_notes,
                        company_name=company_name,
                        market=new_h_market,
                        sector=new_h_sector,
                    )
                    if err:
                        st.error(err)
                    else:
                        st.toast(f"{txn_side} {txn_qty:g} {txn_ticker} @ ${txn_price:.2f} recorded",
                                 icon="🔁")
                        st.rerun()

    # ── Transaction history ───────────────────────────────────────────────────
    txns = load_transactions()
    if txns:
        st.subheader("📜 Transaction History")
        st.caption(f"{len(txns)} transaction(s) recorded. Most recent first.")
        sorted_txns = sorted(txns, key=lambda t: (t.date, t.recorded_at), reverse=True)
        txn_rows = [{
            "Date":      t.date,
            "Ticker":    t.ticker,
            "Side":      t.side,
            "Quantity":  t.quantity,
            "Price":     round(t.price, 2),
            "Value":     round(t.quantity * t.price, 2),
            "Notes":     t.notes,
        } for t in sorted_txns]
        st.dataframe(pd.DataFrame(txn_rows), hide_index=True, use_container_width=True)
    else:
        st.caption("No transactions recorded yet.")


def render_thesis_memory_tab() -> None:
    """Dynamic Thesis State Engine — strategic state models for each holding."""
    from portfolio import (
        CONVICTION_BADGE, CONVICTION_FALLING, CONVICTION_RISING, CONVICTION_STABLE,
        EVENT_BADGE,
        RISK_CATEGORIES, RISK_KINDS, RISK_SEVERITIES, RISK_STATUSES,
        THESIS_STATUS_BADGE, THESIS_STATUS_BROKEN,
        THESIS_STATUS_STABLE, THESIS_STATUS_STRENGTHENING,
        THESIS_STATUS_WEAKENING, TIME_HORIZONS,
        ThesisImportError,
        ThesisQuotaExceeded,
        build_preview_thesis,
        delete_core_thesis, delete_risk_item, load_all_core_theses, load_holdings,
        load_core_thesis,
        extract_text_from_document, extract_thesis_from_text,
        extract_thesis_rule_based,
        save_core_thesis,
        thesis_preview_summary,
        upsert_core_thesis_fields, upsert_risk_item,
    )

    st.header("📜 Thesis Memory — Dynamic State Engine")
    st.caption(
        "Each holding is a **continuously monitored strategic state model**: "
        "core thesis · scenarios (bull/base/bear) · risk/return matrix · "
        "validation events · conviction trend. Every new filing reweights "
        "scenarios, generates validation events, and updates conviction — "
        "without overwriting your original investment intent."
    )

    holdings = load_holdings()
    theses   = load_all_core_theses()

    if not holdings:
        st.info(
            "Add positions in the **💼 Holdings** tab first, then return here "
            "to author the original investment thesis for each one.",
            icon="💡",
        )
        return

    # ── Summary ───────────────────────────────────────────────────────────────
    counts = {
        THESIS_STATUS_STRENGTHENING: 0,
        THESIS_STATUS_STABLE:        0,
        THESIS_STATUS_WEAKENING:     0,
        THESIS_STATUS_BROKEN:        0,
    }
    no_thesis = 0
    drift_count = 0
    for t in holdings:
        c = theses.get(t)
        if c is None:
            no_thesis += 1
        else:
            counts[c.thesis_status] = counts.get(c.thesis_status, 0) + 1
            if c.drift_detected:
                drift_count += 1

    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("📈 Strengthening", counts[THESIS_STATUS_STRENGTHENING])
    s2.metric("➖ Stable",         counts[THESIS_STATUS_STABLE])
    s3.metric("📉 Weakening",      counts[THESIS_STATUS_WEAKENING])
    s4.metric("💔 Broken",         counts[THESIS_STATUS_BROKEN])
    s5.metric("📝 No Thesis Yet",  no_thesis)

    if drift_count:
        st.warning(
            f"⚠️ Thesis drift detected on **{drift_count}** holding(s) — "
            "the company narrative has materially diverged from the original "
            "investment case. Review CIO commentary below.",
            icon="🧭",
        )

    # ── 📥 Import Thesis From Report ──────────────────────────────────────────
    _render_thesis_import_section(
        holdings=holdings, existing_theses=theses,
        extract_text=extract_text_from_document,
        extract_thesis=extract_thesis_from_text,
        extract_thesis_rule_based=extract_thesis_rule_based,
        build_preview=build_preview_thesis,
        preview_summary_fn=thesis_preview_summary,
        save_thesis=save_core_thesis,
        ImportError_=ThesisImportError,
        QuotaExceeded=ThesisQuotaExceeded,
        demo_mode=demo_mode,
    )
    st.divider()

    # ── Per-holding editor cards ──────────────────────────────────────────────
    # Sort: holdings with a thesis first (worst status first), then unauthored
    _STATUS_ORDER = {
        THESIS_STATUS_BROKEN:        0,
        THESIS_STATUS_WEAKENING:     1,
        THESIS_STATUS_STABLE:        2,
        THESIS_STATUS_STRENGTHENING: 3,
    }
    def _sort_key(item):
        ticker, h = item
        c = theses.get(ticker)
        if c is None:
            return (5, ticker)  # unauthored at bottom
        return (_STATUS_ORDER.get(c.thesis_status, 4),
                0 if c.drift_detected else 1,
                ticker)

    for ticker, h in sorted(holdings.items(), key=_sort_key):
        c = theses.get(ticker)
        with st.container(border=True):
            # ── Header row: identity · status · conviction trend ─────────────
            hc1, hc2, hc3 = st.columns([2.5, 2, 2])
            with hc1:
                st.markdown(f"### {ticker}")
                st.caption(f"{h.company_name} · {h.sector} · {h.market}")
            with hc2:
                if c is None:
                    st.markdown("**Status:** _no thesis recorded yet_")
                else:
                    icon, lbl = THESIS_STATUS_BADGE.get(
                        c.thesis_status, ("⚪", c.thesis_status))
                    st.markdown(f"**Status:** {icon} {lbl}")
                    if c.last_status_change:
                        st.caption(f"Since: {c.last_status_change}")
            with hc3:
                if c is not None:
                    tr_icon, tr_lbl = CONVICTION_BADGE.get(
                        c.conviction_trend, ("➖", "Stable"))
                    st.markdown(
                        f"**Conviction:** {c.last_conviction_score}/100 · "
                        f"{tr_icon} {tr_lbl}"
                    )
                    st.caption(
                        f"Evaluations: {c.evaluations_count}"
                        + (f" · Horizon: {c.time_horizon}" if c.time_horizon else "")
                    )

            # ── Provenance badge (Imported vs Manual) ───────────────────────
            if c is not None:
                if c.source_type == "Imported" and c.imported_from:
                    src_kind = c.import_source_kind or "doc"
                    imp_date = (c.imported_at or "")[:10] or "—"
                    st.caption(
                        f"📥 **User-authored / imported** from `{c.imported_from}` "
                        f"({src_kind}) on {imp_date}"
                    )
                else:
                    st.caption("✍️ **User-authored** (manual entry)")

            # ── CIO Commentary + drift ──────────────────────────────────────
            if c is not None:
                if c.cio_commentary:
                    st.markdown(f"**🧑‍💼 CIO Commentary:** {c.cio_commentary}")
                if c.drift_detected and c.drift_summary:
                    st.warning(f"🧭 **Drift:** {c.drift_summary}", icon="⚠️")
                if not c.cio_commentary and c.evaluations_count == 0:
                    st.caption(
                        "Commentary will appear after the next filing analysis "
                        "for this ticker."
                    )

                # ── Scenario probability bar ────────────────────────────────
                _render_scenario_bar(c)

            # ── Sub-sections (expanders) ────────────────────────────────────
            # Auto-expand Core Thesis right after a fresh import.
            _recently_imported = (
                st.session_state.get("last_saved_thesis_import", {})
                    .get("ticker") == ticker
            )
            edit_label = (
                "✏️ Core Thesis & Scenarios" if c is not None
                else "📜 Author Core Thesis & Scenarios"
            )
            with st.expander(
                edit_label,
                expanded=(c is None or _recently_imported),
            ):
                # ── Read-only field summary ──────────────────────────
                if c is not None:
                    _render_thesis_field_summary(c)
                _render_core_thesis_form(
                    ticker, h, c,
                    upsert_fn=upsert_core_thesis_fields,
                    delete_fn=delete_core_thesis,
                    time_horizons=TIME_HORIZONS,
                )

            if c is not None:
                # ── Stored Thesis JSON debug ─────────────────────────
                with st.expander("🐞 Stored Thesis JSON", expanded=False):
                    from dataclasses import asdict as _asdict
                    try:
                        st.json(_asdict(c))
                    except Exception as _e:
                        st.error(f"Could not serialise thesis: {_e}")

                with st.expander(
                    f"🛡️ Risk / Return Matrix ({len(c.risk_matrix)} item(s))",
                    expanded=False,
                ):
                    _render_risk_matrix_section(
                        ticker, c,
                        upsert_fn=upsert_risk_item,
                        delete_fn=delete_risk_item,
                        categories=RISK_CATEGORIES,
                        kinds=RISK_KINDS,
                        severities=RISK_SEVERITIES,
                        statuses=RISK_STATUSES,
                    )

                with st.expander(
                    f"📅 Validation Events ({len(c.validation_events)})",
                    expanded=False,
                ):
                    _render_validation_events_section(c, badge_map=EVENT_BADGE)


def _render_thesis_import_section(
    *, holdings, existing_theses,
    extract_text, extract_thesis, extract_thesis_rule_based,
    build_preview, preview_summary_fn,
    save_thesis, ImportError_, QuotaExceeded,
    demo_mode: bool = False,
) -> None:
    """📥 Import Thesis From Report — upload PDF/DOCX/TXT and extract via AI.

    When OpenAI quota is exhausted, surfaces a friendly Demo Mode fallback
    that runs a rule-based section parser on the document instead.
    """
    from dataclasses import asdict
    from portfolio import load_core_thesis

    PENDING_KEY    = "pending_thesis_import"
    QUOTA_KEY      = "pending_thesis_quota_fallback"
    LAST_SAVED_KEY = "last_saved_thesis_import"

    with st.expander("📥 Import Thesis From Report", expanded=False):
        st.caption(
            "Upload an investment research note (**PDF**, **DOCX**, or **TXT**) "
            "and the system will extract the thesis fields — drivers, "
            "catalysts, risks, scenarios, valuation, risk/return matrix — "
            "for you to review and edit before saving. You stay in control: "
            "nothing is auto-applied to your holdings."
        )

        pending  = st.session_state.get(PENDING_KEY)
        quota_fb = st.session_state.get(QUOTA_KEY)
        last_saved = st.session_state.get(LAST_SAVED_KEY)

        # ── Show "Stored Thesis Debug" right after a successful save ─────
        if pending is None and last_saved is not None:
            st.success(
                f"✅ Thesis for **{last_saved['ticker']}** saved successfully "
                f"from `{last_saved['filename']}`.",
                icon="📜",
            )
            with st.expander(
                f"🐞 Stored Thesis Debug — {last_saved['ticker']} "
                "(reloaded from disk)",
                expanded=True,
            ):
                st.caption(
                    "This is what is now persisted in "
                    "`portfolio/core_theses.json` for this ticker — "
                    "reloaded fresh from storage after save."
                )
                st.json(last_saved["stored_json"])
                if st.button(
                    "Dismiss debug panel",
                    key=f"dismiss_last_saved_{last_saved['ticker']}",
                ):
                    del st.session_state[LAST_SAVED_KEY]
                    st.rerun()

        # ── Quota-exhausted state → offer Demo Mode rule-based fallback ──
        if pending is None and quota_fb is not None:
            st.warning(
                "🪫 **OpenAI quota exhausted** — the AI extractor couldn't "
                "run because there are no remaining credits on the API key.\n\n"
                "You can still import this document using **Demo Mode**: a "
                "lightweight rule-based parser that scans for standard "
                "research-note section headers (recommendation, drivers, "
                "catalysts, risks, bull/base/bear cases, target prices). "
                "Results may be less complete than AI extraction — review "
                "carefully in the preview before saving.",
                icon="🪫",
            )
            st.caption(
                f"Document: `{quota_fb['filename']}` ({quota_fb['kind']}) · "
                f"Ticker: **{quota_fb['ticker']}** · "
                f"{len(quota_fb['text']):,} characters extracted."
            )
            qc1, qc2 = st.columns([2, 1])
            with qc1:
                use_fallback = st.button(
                    "🛟 Use Demo Mode (rule-based extraction)",
                    type="primary", use_container_width=True,
                    key="use_rule_fallback",
                )
            with qc2:
                cancel_qf = st.button(
                    "❌ Cancel", use_container_width=True,
                    key="cancel_quota_fb",
                )
            if cancel_qf:
                del st.session_state[QUOTA_KEY]
                st.rerun()
            if use_fallback:
                try:
                    extracted = extract_thesis_rule_based(quota_fb["text"])
                    preview = build_preview(
                        quota_fb["ticker"], quota_fb["company_name"], extracted,
                        filename=quota_fb["filename"],
                        source_kind=quota_fb["kind"],
                    )
                    st.session_state[PENDING_KEY] = {
                        "ticker":   quota_fb["ticker"],
                        "filename": quota_fb["filename"],
                        "kind":     quota_fb["kind"],
                        "preview":  preview,
                        "demo_mode": True,
                    }
                    st.session_state.pop(LAST_SAVED_KEY, None)
                    del st.session_state[QUOTA_KEY]
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"Rule-based extraction failed: {e}", icon="❌")
            return

        # ── No pending import → show upload form ─────────────────────────
        if pending is None:
            tickers = sorted(holdings.keys())
            if not tickers:
                st.info("Add at least one holding first.")
                return

            # Warn about Demo Mode limitations before the user uploads
            if demo_mode:
                st.warning(
                    "**Demo extraction is limited.** The rule-based parser "
                    "can only find content that is explicitly labelled with "
                    "recognised section headers (e.g. *Thesis Drivers:*, "
                    "*Catalysts:*, *Key Risks:*, *Bull Case:* …). "
                    "For full thesis extraction from Arabic/English research "
                    "reports, DOCX tables, and unstructured prose, "
                    "**enable Live AI extraction** by adding your "
                    "`OPENAI_API_KEY` in Replit Secrets and turning off "
                    "Demo Analysis Mode.",
                    icon="⚠️",
                )

            ic1, ic2 = st.columns([1, 2])
            with ic1:
                t_choice = st.selectbox(
                    "Holding", tickers, key="import_ticker_choice",
                    help="Pick the holding this research note relates to.",
                )
            with ic2:
                uploaded = st.file_uploader(
                    "Research document",
                    type=["pdf", "docx", "txt", "md"],
                    accept_multiple_files=False,
                    key="thesis_upload",
                    help="PDF, DOCX, TXT, or Markdown · max 8 MB",
                )

            if demo_mode:
                extract_clicked = st.button(
                    "🛟 Extract with rule-based parser (Demo Mode)",
                    type="primary", use_container_width=True,
                    disabled=(uploaded is None),
                    help="Scans the document for labelled section headers. "
                         "Best effort — results will be partial for most "
                         "documents.",
                )
            else:
                extract_clicked = st.button(
                    "🤖 Extract Thesis from Document", type="primary",
                    use_container_width=True,
                    disabled=(uploaded is None),
                )

            if extract_clicked and uploaded is not None:
                ticker_sel = t_choice
                holding    = holdings[ticker_sel]
                try:
                    with st.spinner("Extracting text from document…"):
                        text, kind = extract_text(uploaded.getvalue(), uploaded.name)

                    if demo_mode:
                        # Skip AI entirely — go straight to rule-based
                        with st.spinner("Running rule-based section parser…"):
                            extracted = extract_thesis_rule_based(text)
                        preview = build_preview(
                            ticker_sel, holding.company_name, extracted,
                            filename=uploaded.name, source_kind=kind,
                        )
                        st.session_state[PENDING_KEY] = {
                            "ticker":    ticker_sel,
                            "filename":  uploaded.name,
                            "kind":      kind,
                            "preview":   preview,
                            "demo_mode": True,
                        }
                        st.session_state.pop(LAST_SAVED_KEY, None)
                        st.rerun()
                    else:
                        with st.spinner(
                            "AI is reading the document and structuring the "
                            "thesis (this can take 10-30 seconds)…"
                        ):
                            try:
                                _secrets = st.secrets
                            except Exception:
                                _secrets = None
                            extracted = extract_thesis(
                                text, ticker_sel, holding.company_name,
                                st_secrets=_secrets,
                            )
                        preview = build_preview(
                            ticker_sel, holding.company_name, extracted,
                            filename=uploaded.name, source_kind=kind,
                        )
                        st.session_state[PENDING_KEY] = {
                            "ticker":   ticker_sel,
                            "filename": uploaded.name,
                            "kind":     kind,
                            "preview":  preview,
                            "demo_mode": False,
                        }
                        st.session_state.pop(LAST_SAVED_KEY, None)
                        st.rerun()
                except QuotaExceeded:
                    st.session_state[QUOTA_KEY] = {
                        "ticker":       ticker_sel,
                        "company_name": holding.company_name,
                        "filename":     uploaded.name,
                        "kind":         kind,
                        "text":         text,
                    }
                    st.rerun()
                except ImportError_ as e:
                    st.error(f"Import failed: {e}", icon="❌")
                except Exception as e:  # noqa: BLE001
                    st.error(f"Unexpected error during import: {e}", icon="❌")
            return

        # ── Pending import → preview + save / discard ────────────────────
        preview  = pending["preview"]
        ticker   = pending["ticker"]
        filename = pending["filename"]
        kind     = pending["kind"]
        existing = existing_theses.get(ticker)

        is_demo_pending = pending.get("demo_mode", False)

        if is_demo_pending:
            st.warning(
                f"**Demo extraction is limited** — rule-based parser ran on "
                f"`{filename}` ({kind}) for **{ticker}**. No AI was called.\n\n"
                "The parser can only extract content that is explicitly "
                "labelled with recognised section headers. It cannot interpret "
                "unstructured prose, tables without headers, or context that "
                "requires reading comprehension. **For full extraction from "
                "Arabic/English research reports, enable Live AI extraction.**",
                icon="⚠️",
            )
        else:
            st.success(
                f"✅ Extracted thesis for **{ticker}** from `{filename}` "
                f"({kind}). Review the preview below before saving.",
                icon="📥",
            )

        # ── Field completeness check (demo mode) ─────────────────────────
        summ = preview_summary_fn(preview)
        _populated_fields = (
            (1 if preview.rationale else 0)
            + summ["drivers_count"]
            + summ["catalysts_count"]
            + summ["risks_count"]
            + (1 if preview.valuation_thesis else 0)
            + (1 if preview.expected_moat else 0)
            + summ["risk_matrix_count"]
            + (1 if preview.scenario_bull.description else 0)
            + (1 if preview.scenario_base.description else 0)
            + (1 if preview.scenario_bear.description else 0)
        )
        _FIELD_THRESHOLD = 4  # warn if fewer than this many items found

        if is_demo_pending and _populated_fields < _FIELD_THRESHOLD:
            st.error(
                f"⚠️ **Most fields are empty** — only {_populated_fields} "
                f"item(s) were extracted from the document. "
                "The document may lack clearly labelled section headers, or "
                "use a format the rule-based parser does not recognise. "
                "You can:\n"
                "- Fill in the empty fields manually in the form below, then "
                "save the partial thesis as a starting point.\n"
                "- Or cancel and re-import using **Live AI extraction** for "
                "better results.",
                icon="🚨",
            )

        # Preview summary metrics
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Drivers found",     summ["drivers_count"])
        sc1.metric("Catalysts found",   summ["catalysts_count"])
        sc2.metric("Risks found",       summ["risks_count"])
        sc2.metric("Risk matrix rows",  summ["risk_matrix_count"])
        sc3.metric("Bull / Base / Bear",
                   f"{summ['bull_prob']:.0f} / {summ['base_prob']:.0f} / "
                   f"{summ['bear_prob']:.0f}")

        # ── 🐞 Debug: parsed JSON BEFORE save ────────────────────────────
        with st.expander(
            "🐞 Debug — Parsed Thesis (JSON before save)",
            expanded=False,
        ):
            st.caption(
                "Exactly what the parser produced from the document. Edits "
                "you make in the form below are applied on top of this "
                "before saving. Empty fields mean the parser did not find "
                "them — fill them in manually."
            )
            try:
                st.json(asdict(preview))
            except Exception as _e:  # noqa: BLE001
                st.error(f"Could not render parsed JSON: {_e}")

        # ── Overwrite confirmation (outside the form, no submit needed) ──
        confirm_ok = True
        if existing is not None:
            st.warning(
                f"⚠️ A thesis already exists for **{ticker}**. Saving will "
                f"replace it (live state — events log, conviction history, "
                f"scenario probabilities — will be reset). Current source: "
                f"**{existing.source_type}**"
                + (f" · `{existing.imported_from}`"
                   if existing.imported_from else "")
                + ".",
                icon="🚨",
            )
            confirm_ok = st.checkbox(
                f"Yes, overwrite the existing thesis for {ticker}",
                key=f"confirm_overwrite_{ticker}",
            )
            if confirm_ok:
                _save_btn_label = (
                    "💾 Confirm overwrite — save extracted fields"
                    if is_demo_pending else
                    "✅ Confirm Save Imported Thesis"
                )
                st.info(
                    f"✅ Overwrite confirmed. Scroll to the bottom of the "
                    f"form and click **{_save_btn_label}** "
                    "to write this thesis to disk.",
                    icon="👇",
                )
            else:
                st.caption(
                    "_The save button below is disabled until you tick the "
                    "checkbox above._"
                )

        if is_demo_pending:
            st.caption(
                "✏️ **Review the extracted fields below** — empty fields were "
                "not found by the rule-based parser. You can fill them in "
                "manually before saving, or save the partial thesis as a "
                "starting point and complete it later."
            )
        else:
            st.caption(
                "✏️ **Review and edit every field below before saving.** "
                "Nothing has been written to your holdings yet. After saving, "
                "you can still fine-tune the thesis in the holding's card below."
            )

        _cancel_label = (
            "❌ Cancel — use Live AI extraction instead"
            if is_demo_pending else
            "❌ Discard import"
        )
        _cancel_help = (
            "Discard the rule-based preview. Turn off Demo Mode in the "
            "sidebar and re-upload the document to get full AI extraction."
            if is_demo_pending else
            "Throw away the extracted preview without saving."
        )
        cancel_clicked = st.button(
            _cancel_label, key="discard_import", help=_cancel_help,
        )
        if cancel_clicked:
            del st.session_state[PENDING_KEY]
            st.rerun()

        # ── Editable preview form ────────────────────────────────────────
        saved = _render_import_preview_form(
            preview=preview, ticker=ticker, confirm_ok=confirm_ok,
            save_thesis=save_thesis, filename=filename, kind=kind,
            load_thesis=load_core_thesis,
            last_saved_key=LAST_SAVED_KEY,
            demo_mode=is_demo_pending,
        )
        if saved:
            del st.session_state[PENDING_KEY]
            st.rerun()


def _lines_to_list(s: str) -> list[str]:
    return [ln.strip() for ln in (s or "").splitlines() if ln.strip()]


def _list_to_lines(xs) -> str:
    return "\n".join(xs or [])


def _render_import_preview_form(
    *, preview, ticker: str, confirm_ok: bool,
    save_thesis, filename: str, kind: str,
    load_thesis=None, last_saved_key: str = "last_saved_thesis_import",
    demo_mode: bool = False,
) -> bool:
    """Editable form bound to the pending-import preview. Returns True if
    the user submitted and the thesis was saved."""
    from dataclasses import asdict
    from portfolio import (
        RISK_CATEGORIES, RISK_KINDS, RISK_SEVERITIES, RISK_STATUSES,
        TIME_HORIZONS, normalize_scenario_probabilities,
    )
    from portfolio.core_thesis import RiskMatrixItem, ScenarioCase

    with st.form(f"import_preview_form_{ticker}", clear_on_submit=False):
        st.markdown("##### 📋 Edit extracted thesis")

        rationale = st.text_area(
            "Rationale (1-3 sentences)", value=preview.rationale,
            height=80, key=f"imp_rationale_{ticker}",
        )

        c1, c2 = st.columns(2)
        with c1:
            drivers_txt = st.text_area(
                "Thesis drivers (one per line)",
                value=_list_to_lines(preview.thesis_drivers),
                height=120, key=f"imp_drivers_{ticker}",
            )
            catalysts_txt = st.text_area(
                "Expected catalysts (one per line)",
                value=_list_to_lines(preview.expected_catalysts),
                height=100, key=f"imp_catalysts_{ticker}",
            )
            risks_txt = st.text_area(
                "Key risks (one per line)",
                value=_list_to_lines(preview.key_risks),
                height=100, key=f"imp_risks_{ticker}",
            )
        with c2:
            value_drivers_txt = st.text_area(
                "Expected value drivers (one per line)",
                value=_list_to_lines(preview.expected_value_drivers),
                height=120, key=f"imp_value_drivers_{ticker}",
            )
            mgmt_txt = st.text_area(
                "Mgmt execution assumptions (one per line)",
                value=_list_to_lines(preview.management_execution_assumptions),
                height=100, key=f"imp_mgmt_{ticker}",
            )
            try:
                horizon_idx = TIME_HORIZONS.index(preview.time_horizon)
            except ValueError:
                horizon_idx = 1
            time_horizon = st.selectbox(
                "Time horizon", TIME_HORIZONS, index=horizon_idx,
                key=f"imp_horizon_{ticker}",
            )

        c3, c4 = st.columns(2)
        with c3:
            expected_moat = st.text_input(
                "Expected moat", value=preview.expected_moat,
                key=f"imp_moat_{ticker}",
            )
            expected_margin_profile = st.text_input(
                "Expected margin profile", value=preview.expected_margin_profile,
                key=f"imp_margin_{ticker}",
            )
        with c4:
            expected_management = st.text_input(
                "Expected management behavior", value=preview.expected_management,
                key=f"imp_mgmtbeh_{ticker}",
            )
            expected_growth_profile = st.text_input(
                "Expected growth profile", value=preview.expected_growth_profile,
                key=f"imp_growth_{ticker}",
            )

        valuation_thesis = st.text_input(
            "Valuation thesis (one-liner)", value=preview.valuation_thesis,
            key=f"imp_val_{ticker}",
        )

        # Scenarios
        st.markdown("##### 🎯 Bull / Base / Bear scenarios")
        st.caption(
            "Probabilities will be auto-rescaled to sum to 100% on save."
        )
        scn_inputs: list[dict] = []
        for label, scn, default_prob in [
            ("🐂 Bull",  preview.scenario_bull, 25),
            ("⚖️ Base",  preview.scenario_base, 55),
            ("🐻 Bear",  preview.scenario_bear, 20),
        ]:
            with st.container(border=True):
                st.markdown(f"**{label} case**")
                sc1, sc2 = st.columns([3, 1])
                with sc1:
                    desc = st.text_area(
                        f"{label} — description", value=scn.description,
                        height=70, key=f"imp_{label}_desc_{ticker}",
                        label_visibility="collapsed",
                    )
                with sc2:
                    prob = st.number_input(
                        f"{label} probability (%)", min_value=0.0, max_value=100.0,
                        value=float(scn.probability or default_prob), step=1.0,
                        key=f"imp_{label}_prob_{ticker}",
                    )
                tgt = st.text_input(
                    f"{label} — valuation target",
                    value=scn.valuation_target,
                    key=f"imp_{label}_tgt_{ticker}",
                )
                assumptions_txt = st.text_area(
                    f"{label} — key assumptions (one per line)",
                    value=_list_to_lines(scn.key_assumptions),
                    height=70, key=f"imp_{label}_assum_{ticker}",
                )
                scn_inputs.append({
                    "description":      desc,
                    "probability":      prob,
                    "valuation_target": tgt,
                    "key_assumptions":  _lines_to_list(assumptions_txt),
                })

        # Risk matrix
        st.markdown("##### 🛡️ Risk / Return matrix")
        risk_inputs: list[dict] = []
        if not preview.risk_matrix:
            st.caption("_No risk-matrix rows were extracted. You can add them "
                       "from the holding's card after saving._")
        for idx, item in enumerate(preview.risk_matrix):
            with st.expander(
                f"{item.kind}: {item.name} "
                f"({item.severity} · {item.current_status})",
                expanded=(idx == 0),
            ):
                rc1, rc2, rc3, rc4 = st.columns(4)
                with rc1:
                    name = st.text_input(
                        "Name", value=item.name,
                        key=f"imp_risk_{idx}_name_{ticker}",
                    )
                with rc2:
                    cat_idx = (RISK_CATEGORIES.index(item.category)
                               if item.category in RISK_CATEGORIES else 0)
                    category = st.selectbox(
                        "Category", RISK_CATEGORIES, index=cat_idx,
                        key=f"imp_risk_{idx}_cat_{ticker}",
                    )
                with rc3:
                    kind_idx = (RISK_KINDS.index(item.kind)
                                if item.kind in RISK_KINDS else 0)
                    risk_kind = st.selectbox(
                        "Kind", RISK_KINDS, index=kind_idx,
                        key=f"imp_risk_{idx}_kind_{ticker}",
                    )
                with rc4:
                    sev_idx = (RISK_SEVERITIES.index(item.severity)
                               if item.severity in RISK_SEVERITIES else 1)
                    severity = st.selectbox(
                        "Severity", RISK_SEVERITIES, index=sev_idx,
                        key=f"imp_risk_{idx}_sev_{ticker}",
                    )
                rc5, rc6 = st.columns([1, 3])
                with rc5:
                    st_idx = (RISK_STATUSES.index(item.current_status)
                              if item.current_status in RISK_STATUSES else 1)
                    status = st.selectbox(
                        "Status", RISK_STATUSES, index=st_idx,
                        key=f"imp_risk_{idx}_st_{ticker}",
                    )
                with rc6:
                    impact = st.text_input(
                        "Expected impact", value=item.expected_impact,
                        key=f"imp_risk_{idx}_imp_{ticker}",
                    )
                ewi_txt = st.text_area(
                    "Early-warning indicators (one per line)",
                    value=_list_to_lines(item.early_warning_indicators),
                    height=70, key=f"imp_risk_{idx}_ewi_{ticker}",
                )
                action = st.text_input(
                    "Required action if this materializes",
                    value=item.required_action,
                    key=f"imp_risk_{idx}_act_{ticker}",
                )
                hedge = st.text_input(
                    "Possible hedge (optional)", value=item.possible_hedge,
                    key=f"imp_risk_{idx}_hdg_{ticker}",
                )
                risk_inputs.append({
                    "original_id":              item.id,
                    "name":                     name,
                    "category":                 category,
                    "kind":                     risk_kind,
                    "severity":                 severity,
                    "current_status":           status,
                    "expected_impact":          impact,
                    "early_warning_indicators": _lines_to_list(ewi_txt),
                    "required_action":          action,
                    "possible_hedge":           hedge,
                })

        _submit_label = (
            f"💾 Save only extracted fields ({ticker})"
            if demo_mode else
            f"✅ Confirm Save Imported Thesis ({ticker})"
        )
        submitted = st.form_submit_button(
            _submit_label,
            type="primary", use_container_width=True,
            disabled=(not confirm_ok),
            help=(
                "Saves the extracted fields (which may be partial) to "
                "portfolio/core_theses.json. You can fill in the remaining "
                "empty fields from the holding card below after saving."
                if demo_mode else
                "Writes the thesis (with your edits) to "
                "portfolio/core_theses.json. Disabled until the overwrite "
                "checkbox above is ticked (when a thesis already exists)."
            ),
        )

    if not submitted:
        return False
    if not confirm_ok:
        st.error(
            "Please tick the overwrite confirmation checkbox above before "
            "clicking Confirm Save.",
            icon="⚠️",
        )
        return False

    # Build the final CoreThesis from edited values (preserving provenance)
    p_bull, p_base, p_bear = normalize_scenario_probabilities(
        scn_inputs[0]["probability"], scn_inputs[1]["probability"],
        scn_inputs[2]["probability"],
    )
    final = preview  # mutate in place; provenance fields already set
    final.rationale                        = rationale.strip()
    final.thesis_drivers                   = _lines_to_list(drivers_txt)
    final.expected_value_drivers           = _lines_to_list(value_drivers_txt)
    final.expected_catalysts               = _lines_to_list(catalysts_txt)
    final.key_risks                        = _lines_to_list(risks_txt)
    final.management_execution_assumptions = _lines_to_list(mgmt_txt)
    final.expected_moat                    = expected_moat.strip()
    final.expected_management              = expected_management.strip()
    final.expected_margin_profile          = expected_margin_profile.strip()
    final.expected_growth_profile          = expected_growth_profile.strip()
    final.time_horizon                     = time_horizon
    final.valuation_thesis                 = valuation_thesis.strip()
    final.scenario_bull = ScenarioCase(
        description=scn_inputs[0]["description"], probability=p_bull,
        valuation_target=scn_inputs[0]["valuation_target"],
        key_assumptions=scn_inputs[0]["key_assumptions"],
    )
    final.scenario_base = ScenarioCase(
        description=scn_inputs[1]["description"], probability=p_base,
        valuation_target=scn_inputs[1]["valuation_target"],
        key_assumptions=scn_inputs[1]["key_assumptions"],
    )
    final.scenario_bear = ScenarioCase(
        description=scn_inputs[2]["description"], probability=p_bear,
        valuation_target=scn_inputs[2]["valuation_target"],
        key_assumptions=scn_inputs[2]["key_assumptions"],
    )
    new_risks: list[RiskMatrixItem] = []
    for r in risk_inputs:
        if not r["name"].strip():
            continue
        new_risks.append(RiskMatrixItem(
            id=r["original_id"] or "",
            name=r["name"].strip(),
            category=r["category"], kind=r["kind"],
            severity=r["severity"], current_status=r["current_status"],
            expected_impact=r["expected_impact"].strip(),
            early_warning_indicators=r["early_warning_indicators"],
            required_action=r["required_action"].strip(),
            possible_hedge=r["possible_hedge"].strip(),
        ))
    final.risk_matrix = new_risks
    # Re-assert provenance (defensive — should already be set)
    final.source_type        = "Imported"
    final.imported_from      = filename
    final.import_source_kind = kind
    if not final.imported_at:
        final.imported_at = datetime.now().isoformat(timespec="seconds")

    try:
        save_thesis(final)
    except Exception as e:  # noqa: BLE001
        st.error(
            f"❌ Could not save the imported thesis: **{type(e).__name__}** — "
            f"{e}\n\nYour edits are preserved in the form above; please try "
            "again or click **Discard import** to cancel.",
            icon="🚨",
        )
        return False

    # Reload the persisted thesis fresh from disk and stash it so the
    # next render can show the "Stored Thesis Debug" expander.
    try:
        stored = load_thesis(ticker) if load_thesis else None
        stored_json = asdict(stored) if stored is not None else asdict(final)
    except Exception as _e:  # noqa: BLE001
        stored_json = {
            "_warning": (
                f"Saved, but could not reload from disk: {type(_e).__name__}: "
                f"{_e}"
            ),
            **asdict(final),
        }
    st.session_state[last_saved_key] = {
        "ticker":      ticker,
        "filename":    filename,
        "kind":        kind,
        "stored_json": stored_json,
    }
    return True


def _render_scenario_bar(core) -> None:
    """Compact bull/base/bear probability bar with values."""
    bull = core.scenario_bull.probability
    base = core.scenario_base.probability
    bear = core.scenario_bear.probability
    sc1, sc2, sc3 = st.columns(3)
    sc1.markdown(f"📗 **Bull:** {bull:.0f}%")
    sc2.markdown(f"📘 **Base:** {base:.0f}%")
    sc3.markdown(f"📕 **Bear:** {bear:.0f}%")
    sc1.progress(min(1.0, bull / 100.0))
    sc2.progress(min(1.0, base / 100.0))
    sc3.progress(min(1.0, bear / 100.0))


def _render_validation_events_section(core, *, badge_map: dict) -> None:
    """Read-only timeline of validation events (newest first)."""
    events = list(core.validation_events or [])
    if not events:
        st.caption(
            "No validation events recorded yet. Events are generated "
            "automatically each time a filing is analysed for this ticker."
        )
        return
    for ev in events[:20]:
        icon, lbl = badge_map.get(ev.event_type, ("⚪", ev.event_type))
        ts = ev.timestamp.replace("T", " ")[:16] if ev.timestamp else "—"
        with st.container(border=True):
            top1, top2 = st.columns([4, 1])
            with top1:
                st.markdown(f"{icon} **{lbl}** · {ev.title}")
                if ev.detail:
                    st.caption(ev.detail)
                if ev.related_terms:
                    st.caption(f"Terms: {', '.join(ev.related_terms)}")
            with top2:
                st.caption(ts)
                st.caption(f"_{ev.source}_")
            if ev.scenario_deltas:
                deltas_str = " · ".join(
                    f"{k}: {('+' if v >= 0 else '')}{v:g}"
                    for k, v in ev.scenario_deltas.items()
                )
                st.caption(f"Scenario impact: {deltas_str}")


def _render_risk_matrix_section(
    ticker, core, *,
    upsert_fn, delete_fn, categories, kinds, severities, statuses,
) -> None:
    """Risk / Return Matrix — list existing rows with edit/delete, plus an add form."""
    # ── Existing rows ────────────────────────────────────────────────────────
    if not core.risk_matrix:
        st.caption(
            "No risks or opportunities recorded yet. Use the form below to "
            "add the first one."
        )
    else:
        _SEV_ICON = {"Low": "🟢", "Medium": "🟡", "High": "🟠", "Critical": "🔴"}
        _STATUS_ICON = {
            "Active": "🚨", "Monitoring": "👁️", "Realized": "💥",
            "Mitigated": "🛡️", "Closed": "✅",
        }
        for item in sorted(
            core.risk_matrix,
            key=lambda r: (
                {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}.get(r.severity, 4),
                0 if r.current_status == "Active" else 1,
            ),
        ):
            kind_icon = "⚠️" if item.kind == "Risk" else "✨"
            sev_icon  = _SEV_ICON.get(item.severity, "⚪")
            st_icon   = _STATUS_ICON.get(item.current_status, "⚪")
            with st.container(border=True):
                top1, top2 = st.columns([5, 1])
                with top1:
                    st.markdown(
                        f"{kind_icon} **{item.name or '(unnamed)'}** "
                        f"· {item.category} · {sev_icon} {item.severity} "
                        f"· {st_icon} {item.current_status}"
                    )
                    if item.expected_impact:
                        st.caption(f"**Impact:** {item.expected_impact}")
                    if item.early_warning_indicators:
                        st.caption(
                            "**Early warnings:** "
                            + " · ".join(item.early_warning_indicators)
                        )
                    if item.required_action:
                        st.caption(f"**Required action:** {item.required_action}")
                    if item.possible_hedge:
                        st.caption(f"**Possible hedge:** {item.possible_hedge}")
                with top2:
                    if st.button(
                        "🗑️",
                        key=f"del_risk_{ticker}_{item.id}",
                        help="Delete this row",
                        use_container_width=True,
                    ):
                        delete_fn(ticker, item.id)
                        st.rerun()

    # ── Add new risk/opportunity form ────────────────────────────────────────
    st.markdown("**Add a risk or opportunity:**")
    with st.form(key=f"add_risk_form_{ticker}", clear_on_submit=True):
        rc1, rc2 = st.columns(2)
        with rc1:
            r_name = st.text_input(
                "Name", placeholder="Apple Pay competitive escalation")
            r_category = st.selectbox("Category", categories, index=0)
            r_kind     = st.selectbox("Type", kinds, index=0)
            r_severity = st.selectbox("Severity", severities, index=1)
            r_status   = st.selectbox("Current status", statuses, index=1)
        with rc2:
            r_impact = st.text_area(
                "Expected impact",
                placeholder="Could compress branded checkout share by 200-400bps",
                height=80,
            )
            r_warnings = st.text_area(
                "Early warning indicators (one per line)",
                placeholder="Apple Pay merchant adoption\nBranded checkout share data",
                height=80,
            )
            r_action = st.text_input(
                "Required action",
                placeholder="Cut position if share loss two consecutive quarters",
            )
            r_hedge = st.text_input(
                "Possible hedge",
                placeholder="Long V/MA as offset",
            )
        if st.form_submit_button(
            "➕ Add to Matrix", type="primary", use_container_width=True,
        ):
            if not r_name.strip():
                st.error("Name is required.")
            else:
                upsert_fn(
                    ticker = ticker,
                    name = r_name.strip(),
                    category = r_category,
                    kind = r_kind,
                    severity = r_severity,
                    current_status = r_status,
                    expected_impact = r_impact.strip(),
                    early_warning_indicators = [
                        ln.strip() for ln in r_warnings.splitlines() if ln.strip()
                    ],
                    required_action = r_action.strip(),
                    possible_hedge = r_hedge.strip(),
                )
                st.rerun()


def _render_thesis_field_summary(core) -> None:
    """Compact read-only snapshot of what is actually stored in a CoreThesis.

    Shown at the top of the "Core Thesis & Scenarios" expander so the user
    can immediately see which fields were populated by the importer vs which
    are still empty — without having to scroll through all form widgets.
    """
    def _badge(val) -> str:
        if isinstance(val, list):
            return f"✅ {len(val)} item(s)" if val else "⬜ empty"
        return f"✅ set" if (val or "").strip() else "⬜ empty"

    def _preview_list(lst, n=3) -> str:
        if not lst:
            return "_none_"
        items = [f"`{x}`" for x in lst[:n]]
        more = f" … +{len(lst)-n} more" if len(lst) > n else ""
        return ", ".join(items) + more

    rows = [
        ("Rationale",        _badge(core.rationale),        (core.rationale or "")[:120] or "_empty_"),
        ("Thesis drivers",   _badge(core.thesis_drivers),   _preview_list(core.thesis_drivers)),
        ("Value drivers",    _badge(core.expected_value_drivers), _preview_list(core.expected_value_drivers)),
        ("Catalysts",        _badge(core.expected_catalysts), _preview_list(core.expected_catalysts)),
        ("Key risks",        _badge(core.key_risks),        _preview_list(core.key_risks)),
        ("Moat",             _badge(core.expected_moat),    (core.expected_moat or "")[:80] or "_empty_"),
        ("Management",       _badge(core.expected_management), (core.expected_management or "")[:80] or "_empty_"),
        ("Margin profile",   _badge(core.expected_margin_profile), (core.expected_margin_profile or "")[:80] or "_empty_"),
        ("Growth profile",   _badge(core.expected_growth_profile), (core.expected_growth_profile or "")[:80] or "_empty_"),
        ("Valuation thesis", _badge(core.valuation_thesis), (core.valuation_thesis or "")[:120] or "_empty_"),
        ("Mgmt assumptions", _badge(core.management_execution_assumptions), _preview_list(core.management_execution_assumptions)),
        ("Bull description", _badge(getattr(core.scenario_bull, "description", "")), (getattr(core.scenario_bull, "description", "") or "")[:80] or "_empty_"),
        ("Base description", _badge(getattr(core.scenario_base, "description", "")), (getattr(core.scenario_base, "description", "") or "")[:80] or "_empty_"),
        ("Bear description", _badge(getattr(core.scenario_bear, "description", "")), (getattr(core.scenario_bear, "description", "") or "")[:80] or "_empty_"),
        ("Risk matrix rows", _badge(core.risk_matrix), _preview_list([r.name for r in (core.risk_matrix or [])])),
    ]

    populated = sum(1 for _, b, _ in rows if b.startswith("✅"))
    total     = len(rows)

    with st.expander(
        f"📊 Imported field summary — {populated}/{total} fields populated",
        expanded=True,
    ):
        if populated == 0:
            st.warning(
                "No thesis fields were extracted. If you just imported a "
                "document, the parser may not have recognised the section "
                "headers. Open **🐞 Stored Thesis JSON** below to inspect "
                "the raw stored data, then edit the fields in the form below "
                "or re-import with a better-structured document.",
                icon="⚠️",
            )
            return
        cols = st.columns(3)
        for i, (field, badge, preview) in enumerate(rows):
            with cols[i % 3]:
                st.markdown(f"**{field}** {badge}")
                st.caption(preview)


def _render_core_thesis_form(
    ticker, holding, core, *,
    upsert_fn, delete_fn, time_horizons,
) -> None:
    """Inline form to author/edit a CoreThesis for one ticker — including scenarios."""
    form_key = f"core_thesis_form_{ticker}"

    def _val(field, default=""):
        return getattr(core, field, default) if core else default
    def _join(lst):
        return "\n".join(lst or [])

    with st.form(key=form_key, clear_on_submit=False):
        # ── Intent ──────────────────────────────────────────────────────────
        st.markdown("##### 🧭 Investment Intent")
        rationale = st.text_area(
            "Why this position exists",
            value=_val("rationale"),
            placeholder="e.g. Dominant share in a structurally growing market...",
            height=80,
        )
        c1, c2 = st.columns(2)
        with c1:
            drivers = st.text_area(
                "Thesis drivers (one per line)",
                value=_join(core.thesis_drivers if core else None),
                placeholder="Pricing power\nNetwork effects\nRecurring revenue",
                height=100,
            )
            value_drivers = st.text_area(
                "Expected value drivers (one per line)",
                value=_join(core.expected_value_drivers if core else None),
                placeholder="Revenue per unit\nMargin expansion\nFree cash flow conversion",
                height=80,
                help="The *financial outcomes* the thesis depends on (vs the drivers, which are the *mechanisms*).",
            )
            catalysts = st.text_area(
                "Expected catalysts (one per line)",
                value=_join(core.expected_catalysts if core else None),
                placeholder="Q3 product launch\nFDA decision in 2027",
                height=80,
            )
            moat = st.text_input(
                "Expected moat",
                value=_val("expected_moat"),
                placeholder="Switching costs from data lock-in",
            )
            mgmt = st.text_input(
                "Expected management behavior",
                value=_val("expected_management"),
                placeholder="Capital-disciplined; consistent guidance",
            )
        with c2:
            risks = st.text_area(
                "Key risks accepted at purchase (one per line)",
                value=_join(core.key_risks if core else None),
                placeholder="Customer concentration\nFX exposure",
                height=100,
            )
            mgmt_exec = st.text_area(
                "Required management execution assumptions (one per line)",
                value=_join(core.management_execution_assumptions if core else None),
                placeholder="Maintain R&D investment pace\nNo dilutive M&A",
                height=80,
                help="Explicit assumptions about how management must execute for the thesis to play out.",
            )
            margin = st.text_input(
                "Expected margin profile",
                value=_val("expected_margin_profile"),
                placeholder="Operating margin expanding to 30%+",
            )
            growth = st.text_input(
                "Expected growth profile",
                value=_val("expected_growth_profile"),
                placeholder="15-20% revenue CAGR for 3 years",
            )
            horizon_idx = (
                list(time_horizons).index(core.time_horizon)
                if core and core.time_horizon in time_horizons
                else 1
            )
            horizon = st.selectbox(
                "Expected time horizon", time_horizons, index=horizon_idx,
            )
            valuation = st.text_input(
                "Expected valuation thesis",
                value=_val("valuation_thesis"),
                placeholder="Re-rates to 25× FCF as margins expand",
            )

        # ── Scenarios ───────────────────────────────────────────────────────
        st.divider()
        st.markdown("##### 🎲 Scenarios (Bull / Base / Bear)")
        st.caption(
            "Seed probabilities sum to 100. The engine will auto-adjust them as "
            "new evidence arrives (events, breaks, confirmations)."
        )
        bull_prob_default = float(core.scenario_bull.probability) if core else 25.0
        base_prob_default = float(core.scenario_base.probability) if core else 55.0
        bear_prob_default = float(core.scenario_bear.probability) if core else 20.0

        sc_a, sc_b, sc_c = st.columns(3)
        with sc_a:
            st.markdown("**📗 Bull**")
            bull_desc = st.text_area(
                "Bull thesis",
                value=(core.scenario_bull.description if core else ""),
                placeholder="Everything goes right…", height=80,
                label_visibility="collapsed",
            )
            bull_prob = st.slider(
                "Probability %", 5, 90, int(bull_prob_default),
                key=f"bull_prob_{ticker}",
            )
            bull_tgt = st.text_input(
                "Valuation target",
                value=(core.scenario_bull.valuation_target if core else ""),
                placeholder="$250/share at 25× FCF",
                key=f"bull_tgt_{ticker}",
            )
            bull_kas = st.text_area(
                "Key assumptions (one per line)",
                value=_join(core.scenario_bull.key_assumptions if core else None),
                placeholder="Hyperscaler capex sustained\nNo regulatory action",
                height=70, key=f"bull_kas_{ticker}",
            )
        with sc_b:
            st.markdown("**📘 Base**")
            base_desc = st.text_area(
                "Base thesis",
                value=(core.scenario_base.description if core else ""),
                placeholder="Most likely outcome…", height=80,
                label_visibility="collapsed",
            )
            base_prob = st.slider(
                "Probability %", 5, 90, int(base_prob_default),
                key=f"base_prob_{ticker}",
            )
            base_tgt = st.text_input(
                "Valuation target",
                value=(core.scenario_base.valuation_target if core else ""),
                placeholder="$180/share at 20× FCF",
                key=f"base_tgt_{ticker}",
            )
            base_kas = st.text_area(
                "Key assumptions (one per line)",
                value=_join(core.scenario_base.key_assumptions if core else None),
                placeholder="Steady AI growth\nMargins stable",
                height=70, key=f"base_kas_{ticker}",
            )
        with sc_c:
            st.markdown("**📕 Bear**")
            bear_desc = st.text_area(
                "Bear thesis",
                value=(core.scenario_bear.description if core else ""),
                placeholder="What kills the thesis…", height=80,
                label_visibility="collapsed",
            )
            bear_prob = st.slider(
                "Probability %", 5, 90, int(bear_prob_default),
                key=f"bear_prob_{ticker}",
            )
            bear_tgt = st.text_input(
                "Valuation target",
                value=(core.scenario_bear.valuation_target if core else ""),
                placeholder="$80/share at 12× FCF",
                key=f"bear_tgt_{ticker}",
            )
            bear_kas = st.text_area(
                "Key assumptions (one per line)",
                value=_join(core.scenario_bear.key_assumptions if core else None),
                placeholder="Custom silicon adoption\nCustomer concentration realized",
                height=70, key=f"bear_kas_{ticker}",
            )
        st.caption(
            f"Probabilities will be normalized to sum to 100 (currently "
            f"{bull_prob + base_prob + bear_prob}). Engine deltas from "
            f"validation events are applied separately."
        )

        # ── Action buttons ──────────────────────────────────────────────────
        st.divider()
        bc1, bc2 = st.columns([3, 1])
        with bc1:
            submitted = st.form_submit_button(
                "💾 Save Thesis & Scenarios",
                use_container_width=True, type="primary",
            )
        with bc2:
            delete_clicked = st.form_submit_button(
                "🗑️ Delete", use_container_width=True,
                disabled=(core is None),
            )

        if submitted:
            def _split(s: str) -> list[str]:
                return [line.strip() for line in (s or "").splitlines() if line.strip()]
            upsert_fn(
                ticker                            = ticker,
                company_name                      = holding.company_name,
                rationale                         = rationale.strip(),
                thesis_drivers                    = _split(drivers),
                expected_value_drivers            = _split(value_drivers),
                expected_catalysts                = _split(catalysts),
                key_risks                         = _split(risks),
                expected_moat                     = moat.strip(),
                expected_management               = mgmt.strip(),
                expected_margin_profile           = margin.strip(),
                expected_growth_profile           = growth.strip(),
                time_horizon                      = horizon,
                valuation_thesis                  = valuation.strip(),
                management_execution_assumptions  = _split(mgmt_exec),
                bull_description                  = bull_desc.strip(),
                bull_probability                  = float(bull_prob),
                bull_valuation_target             = bull_tgt.strip(),
                bull_key_assumptions              = _split(bull_kas),
                base_description                  = base_desc.strip(),
                base_probability                  = float(base_prob),
                base_valuation_target             = base_tgt.strip(),
                base_key_assumptions              = _split(base_kas),
                bear_description                  = bear_desc.strip(),
                bear_probability                  = float(bear_prob),
                bear_valuation_target             = bear_tgt.strip(),
                bear_key_assumptions              = _split(bear_kas),
            )
            st.success(f"Thesis saved for {ticker}.", icon="✅")
            st.rerun()
        if delete_clicked and core is not None:
            delete_fn(ticker)
            st.warning(f"Core thesis for {ticker} deleted.", icon="🗑️")
            st.rerun()


def render_decision_queue_tab() -> None:
    """Portfolio Decision Ranking — attention allocation, not trading signals."""
    from portfolio import (
        ACTION_BADGE, URGENCY_BADGE,
        compute_decision_queue,
        load_all_core_theses,
        load_comparison_history, load_delta_history,
        load_holdings, load_market_intel_state, load_portfolio,
    )
    import pandas as pd

    st.header("🎯 Decision Queue")
    st.caption(
        "**Attention allocation, not trading signals.** Ranks your actual "
        "holdings by which ones need your attention *today*, combining "
        "position size, thesis, valuation, market intel, filing & risk "
        "deterioration, tone, balance sheet, sentiment, and confidence."
    )

    holdings = load_holdings()
    if not holdings:
        st.info(
            "No actual holdings yet. Add positions in the **💼 Holdings** tab "
            "to populate the decision queue.",
            icon="💡",
        )
        return

    result = compute_decision_queue(
        holdings           = holdings,
        watchlist          = load_portfolio(),
        market_intel_state = load_market_intel_state(),
        delta_history      = load_delta_history(),
        comparison_history = load_comparison_history(),
        core_theses        = load_all_core_theses(),
    )

    # ── Queue summary ─────────────────────────────────────────────────────────
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("🔴 Immediate", result.total_immediate)
    s2.metric("🟠 High Attention", result.total_high_attention)
    s3.metric("🟡 Review", result.total_review)
    s4.metric("🟢 Monitor", result.total_monitor)
    st.divider()

    if result.total_immediate + result.total_high_attention == 0:
        st.success(
            "No holdings flagged for urgent attention. Routine monitoring suggested.",
            icon="✅",
        )

    # ── Ranked decisions ──────────────────────────────────────────────────────
    st.subheader(f"📋 Ranked Decisions ({len(result.decisions)} holding(s))")
    st.caption("Highest attention priority at the top.")

    for d in result.decisions:
        u_icon, u_label = URGENCY_BADGE.get(d.urgency, ("⚪", d.urgency))
        a_icon, a_label = ACTION_BADGE.get(d.suggested_action, ("⚪", d.suggested_action))

        with st.container(border=True):
            hc1, hc2, hc3, hc4 = st.columns([2, 1.4, 1.4, 1.4])
            with hc1:
                st.markdown(f"### {d.ticker}")
                st.caption(f"{d.company_name} · {d.weight_pct:.1f}% of portfolio")
            with hc2:
                st.metric("Priority", f"{d.priority_score}/100")
            with hc3:
                st.metric("Urgency", f"{u_icon} {u_label}")
            with hc4:
                st.metric("Suggested", f"{a_icon} {a_label}")

            st.progress(d.priority_score / 100.0)
            st.markdown(f"**Why:** {d.key_reason}")

            with st.expander("All 10 signals", expanded=False):
                rows = sorted(
                    d.signals, key=lambda s: -(s.score * s.weight),
                )
                df = pd.DataFrame([{
                    "Signal":  s.name,
                    "Score":   s.score,
                    "Weight":  s.weight,
                    "Detail":  s.detail,
                } for s in rows])
                st.dataframe(df, hide_index=True, use_container_width=True)

    st.caption(f"Computed at {result.computed_at}")


def render_upload_tab() -> None:
    """Render the Upload Filing tab."""
    st.subheader("📂 Upload a Document for AI Analysis")
    st.caption(
        "Upload a PDF or text file — earnings presentations, analyst reports, "
        "Tadawul announcements, or any other company document. "
        "The same AI analysis engine and Evidence Grounding Layer are applied."
    )

    # ── File uploader ─────────────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "Choose a file",
        type=["pdf", "txt"],
        help="PDF files are parsed page-by-page. Plain text (.txt) is read directly.",
    )

    # ── Document metadata ─────────────────────────────────────────────────────
    st.divider()
    mc1, mc2 = st.columns(2)
    with mc1:
        company_input = st.text_input(
            "Company Name",
            placeholder="e.g. Saudi Aramco, Apple Inc.",
            help="Used in the AI prompt and portfolio state.",
        ).strip()
    with mc2:
        ticker_input = st.text_input(
            "Portfolio Ticker / Symbol",
            placeholder="e.g. 2222.SR, AAPL",
            help="Used to group results in your portfolio. Can be any unique label.",
        ).strip().upper()

    dc1, dc2 = st.columns(2)
    with dc1:
        doc_type = st.selectbox("Document Type", _UPLOAD_DOC_TYPES)
    with dc2:
        source_display = st.selectbox(
            "Source",
            list(_UPLOAD_SOURCES.keys()),
            help="Tagging the source helps you track where each insight came from.",
        )

    source_type = _UPLOAD_SOURCES[source_display]

    # ── Analyse button ────────────────────────────────────────────────────────
    st.divider()
    btn_label = (
        "🧪 Demo Analysis" if (demo_mode and not _ai_ready)
        else "Analyze Document"
    )
    analyze_clicked = st.button(
        btn_label,
        type="primary",
        use_container_width=True,
        disabled=not _analyze_enabled,
        help=None if _analyze_enabled else "Enable Demo Mode or add OPENAI_API_KEY",
    )

    if analyze_clicked:
        if not uploaded and not demo_mode:
            st.error("Please upload a file first.")
            st.stop()
        if not company_input:
            st.error("Please enter the company name.")
            st.stop()
        if not ticker_input:
            st.error("Please enter a portfolio ticker or label.")
            st.stop()

        with st.spinner("Extracting text and analysing…"):
            if demo_mode and not uploaded:
                # Demo mode with no file — reuse demo result directly
                from ai.analyzer import _DEMO_RESULT
                from dataclasses import replace as _dc_replace
                result = _dc_replace(
                    _DEMO_RESULT,
                    source_label=SOURCE_LABELS.get(source_type, source_display),
                )
                file_bytes = b""
                page_count = 0
                char_count = 0
            else:
                # Real file — extract then analyse
                uploaded.seek(0)
                file_bytes = uploaded.read()
                uploaded.seek(0)
                file_text, page_count = extract_text(uploaded)
                char_count = len(file_text)

                if not file_text.strip():
                    st.error(
                        "Could not extract any text from this file. "
                        "Try a different PDF or paste the text as a .txt file."
                    )
                    st.stop()

                result = analyze_uploaded(
                    file_bytes=file_bytes,
                    file_text=file_text,
                    source_type=source_type,
                    doc_type=doc_type,
                    company_name=company_input,
                    ticker=ticker_input,
                    st_secrets=_st_secrets(),
                    demo_mode=demo_mode,
                )

            st.session_state["upload_result"] = result

            # Feed into Portfolio State + Delta Engine
            if result.what_changed:
                adj = result.comparison.conviction_adjustment if result.comparison else 0
                _entry, delta = update_portfolio(
                    ticker_input,
                    company_input,
                    result,
                    doc_type,
                    conviction_adjustment=adj,
                    source_label=result.source_label,
                )

                red_alerts = [
                    _ALERT_DISPLAY[a][1]
                    for a in delta.alerts
                    if a in _ALERT_DISPLAY and _ALERT_DISPLAY[a][0] == "🔴"
                ]
                if red_alerts:
                    st.toast(f"⚠️ {ticker_input}: {', '.join(red_alerts)}", icon="🔴")
                else:
                    st.toast(f"Portfolio updated for {ticker_input}", icon="💾")

            # File info summary
            if not demo_mode and uploaded:
                info_parts = [f"{char_count:,} chars extracted"]
                if page_count:
                    info_parts.append(f"{page_count} pages")
                st.caption(f"📄 {uploaded.name} — {' · '.join(info_parts)}")

    # ── Show result ───────────────────────────────────────────────────────────
    if st.session_state.get("upload_result") is not None:
        st.divider()
        render_analysis(st.session_state["upload_result"])

    # ── Tips ──────────────────────────────────────────────────────────────────
    if not st.session_state.get("upload_result"):
        with st.expander("💡 What can I upload?"):
            st.markdown("""
| File type | Examples |
|-----------|---------|
| **PDF** | Earnings slide decks, annual reports, broker notes, Tadawul filings |
| **TXT** | Copy-pasted press releases, earnings call transcripts, announcements |

**Tips for best results:**
- Text-based PDFs work best. Scanned / image-only PDFs may return empty text.
- If your PDF is image-only, copy-paste the text into a `.txt` file instead.
- Documents are analysed up to **8,000 characters** (roughly 5–10 pages).
- The analysis uses the same AI model and Evidence Grounding Layer as EDGAR filings.
""")


# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("📋 SEC EDGAR Filing Research")
st.caption(
    "Look up SEC filings · Upload reports · AI analysis · Portfolio state · Delta intelligence"
)

(tab_command, tab_search, tab_upload, tab_market_intel,
 tab_watchlist, tab_holdings, tab_thesis, tab_decisions, tab_risk) = st.tabs([
    "⚡ Command Center",
    "🔍 Filing Search",
    "📂 Upload Filing",
    "🌐 Market Intel",
    "🔬 Research Watchlist",
    "💼 Holdings",
    "📜 Thesis Memory",
    "🎯 Decision Queue",
    "🛡️ Portfolio Risk",
])

with tab_command:
    render_command_center_tab()

with tab_watchlist:
    render_portfolio_dashboard()

with tab_holdings:
    render_holdings_tab()

with tab_thesis:
    render_thesis_memory_tab()

with tab_decisions:
    render_decision_queue_tab()

with tab_upload:
    render_upload_tab()

with tab_market_intel:
    render_market_intel_tab()

with tab_risk:
    render_portfolio_risk_tab()

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
