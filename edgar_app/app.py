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
import base64
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import streamlit as st

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
from portfolio.display_metrics import fmt_money_compact
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
_ICON_PATH = os.path.join(_HERE, "static", "icon.png")
try:
    from PIL import Image as _PILImage
    _page_icon = _PILImage.open(_ICON_PATH)
except Exception:
    _page_icon = "🧭"

st.set_page_config(
    page_title="بوصلة",
    page_icon=_page_icon,
    layout="wide",
)

# ── Apple touch icon (iPhone "Add to Home Screen") ────────────────────────────
# Static file serving enabled (enableStaticServing=true in .streamlit/config.toml)
# → edgar_app/static/icon.png is served at /app/static/icon.png
st.markdown(
    '<link rel="apple-touch-icon" href="/app/static/icon.png">',
    unsafe_allow_html=True,
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Mobile scroll fix ───────────────────────────────────────────────── */
    /* iOS captures touch-scroll gestures for any element with overflow:auto  */
    /* even when content doesn't actually overflow, preventing page scroll.   */
    /* Setting overflow:hidden removes that scroll context; touch-action:pan-x */
    /* on textareas / pan-y on containers tells iOS vertical swipes = page.   */

    /* Dataframes (direct child + one level deeper for expander-nested ones) */
    [data-testid="stDataFrame"] > div,
    [data-testid="stDataFrame"] > div > div {
        overflow: hidden !important;
        touch-action: pan-y !important;
    }

    /* Textareas (Notes fields etc.) — pan-x only so vertical goes to page */
    textarea {
        touch-action: pan-x !important;
    }

    /* Expander content — remove any overflow scroll context */
    [data-testid="stExpanderDetails"] {
        overflow: visible !important;
    }

    /* Prevent iOS rubber-band bounce at top/bottom page boundaries.
       Without this, the first swipe at page edges triggers an elastic
       animation instead of scrolling, making it feel like scroll failed. */
    html, body,
    section[data-testid="stMain"],
    [data-testid="stAppViewContainer"] {
        overscroll-behavior-y: none !important;
    }

    /* ── Bidi / Arabic text ─────────────────────────────────────────────── */
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] div,
    [data-testid="stMarkdownContainer"] span { unicode-bidi: plaintext; }

    /* ── Hide Replit deploy badge (overlaps content on mobile) ──────────── */
    [data-testid="stDecoration"] { display: none !important; }

    /* ── Page chrome ────────────────────────────────────────────────────── */
    .block-container {
        padding-top:   0.4rem !important;
        padding-left:  2rem   !important;
        padding-right: 2rem   !important;
        max-width: 100% !important;
        overflow-x: hidden !important;
    }

    /* ── Sticky global header ───────────────────────────────────────────── */
    [data-testid="stHorizontalBlock"]:has(.bousala-appbar) {
        position: sticky !important;
        top: 2.875rem !important;
        z-index: 999  !important;
        background-color: #ffffff !important;
        border-bottom: 1px solid #e2e8f0 !important;
        padding-bottom: 6px !important;
        padding-top:    4px !important;
        margin-left:  -2rem !important;
        margin-right: -2rem !important;
        padding-left:  2rem !important;
        padding-right: 2rem !important;
    }

    /* ── Brand bar ──────────────────────────────────────────────────────── */
    .bousala-appbar {
        display: flex;
        align-items: center;
        gap: 10px;
        white-space: nowrap;
        padding: 4px 0;
    }
    .bousala-appbar .ba-name {
        font-size: 1.05rem;
        font-weight: 700;
        color: #0f172a;
        font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
        letter-spacing: 0.01em;
        line-height: 1.2;
    }

    /* ── KPI strip ──────────────────────────────────────────────────────── */
    .gh-kpi-row {
        display: flex;
        gap: 2.2rem;
        align-items: flex-start;
        flex-wrap: nowrap;
        padding: 4px 0;
    }
    .gh-kpi { min-width: 0; }
    .gh-lbl {
        font-size: 0.88rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        line-height: 1.5;
        white-space: nowrap;
    }
    .gh-val-big { font-size: 2rem;    font-weight: 700; line-height: 1.1; white-space: nowrap; }
    .gh-val-med { font-size: 1.5rem;  font-weight: 600; line-height: 1.1; white-space: nowrap; }
    .gh-val-sm  { font-size: 1.4rem;  font-weight: 600; line-height: 1.1; }
    .gh-val-xs  { font-size: 1.15rem; color: #6b7280;   line-height: 1.4; }
    .gh-pct     { font-size: 0.88rem; font-weight: 500; }

    /* ── Filtered Allocation Summary KPI cards ───────────────────────────
       Pure-HTML flex grid — bypasses Streamlit column system entirely.
       Portrait  (<640 px): min-width 42% → 2-per-row → 2-2-1 for 5 cards.
       Landscape (≥640 px): min-width 0  → all 5 in one row.
    ─────────────────────────────────────────────────────────────────── */
    .fas-kpi-grid { display:flex; flex-wrap:wrap; gap:0.5rem 1.5rem; margin:0.5rem 0 1rem; }
    .fas-kpi-card { flex:1; min-width:42%; }
    .fas-kpi-lbl  { font-size:0.72rem; color:#6b7280; margin-bottom:2px; }
    .fas-kpi-val  { font-size:1.35rem; font-weight:700; line-height:1.15; }
    .fas-kpi-pct  { font-size:0.78rem; font-weight:600; border-radius:999px;
                    padding:2px 7px; display:inline-block; margin-top:3px; }
    @media (min-width: 640px) {
        .fas-kpi-card { min-width:0; }
    }

    /* ── Header — compact on narrow landscape phones (≤768 px) ─────────── */
    @media (max-width: 768px) {
        /* Drop the Arabic name; keep the compass icon only */
        .bousala-appbar .ba-name { display: none !important; }
        /* Tighten KPI strip gap and scale down the large numbers */
        .gh-kpi-row  { gap: 0.9rem !important; }
        .gh-lbl      { font-size: 0.78rem !important; }
        .gh-val-big  { font-size: 1.35rem !important; }
        .gh-val-med  { font-size: 1.05rem !important; }
        .gh-val-sm   { font-size: 0.95rem !important; }
        .gh-val-xs   { font-size: 0.88rem !important; }
        .gh-pct      { font-size: 0.75rem !important; }
        /* Prevent Streamlit from stacking narrow columns — lets 2- and 3-col
           rows stay horizontal on portrait phones (min-width default ~200 px
           causes wrapping at small viewport widths). */
        [data-testid="column"] { min-width: 0 !important; }
    }

    /* ── Tab bar — always horizontally scrollable, never wraps ──────────── */
    [data-testid="stTabs"] > div:first-child {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        flex-wrap: nowrap !important;
        scrollbar-width: none !important;
        -ms-overflow-style: none !important;
    }
    [data-testid="stTabs"] > div:first-child::-webkit-scrollbar { display: none; }
    [data-testid="stTabs"] button[role="tab"] { white-space: nowrap !important; }

    /* ── Accounts summary strip ─────────────────────────────────────────── */
    .acct-summary-row {
        display: flex;
        gap: 1.5rem;
        align-items: flex-start;
        padding: 6px 0 10px 0;
    }
    .acct-kpi-lbl {
        font-size: 0.85rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        line-height: 1.5;
    }
    .acct-kpi-val {
        font-size: 1.25rem;
        font-weight: 700;
        line-height: 1.1;
        color: #0f172a;
    }

    /* ══════════════════════════════════════════════════════════════════════
       PORTRAIT / MOBILE  ≤ 700 px
       ══════════════════════════════════════════════════════════════════════ */
    @media (max-width: 700px) {
        /* Tighter page margins */
        .block-container {
            padding-left:  0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top:   0.2rem !important;
        }
        /* Push sticky header flush to toolbar */
        [data-testid="stHorizontalBlock"]:has(.bousala-appbar) {
            margin-left:  -0.6rem !important;
            margin-right: -0.6rem !important;
            padding-left:  0.6rem !important;
            padding-right: 0.6rem !important;
        }
        /* Shrink logo */
        .bousala-appbar svg { width: 30px !important; height: 30px !important; }
        .bousala-appbar .ba-name { font-size: 0.85rem !important; }

        /* KPI 2 × 2 compact grid */
        .gh-kpi-row {
            flex-wrap: wrap !important;
            gap: 0.4rem 0.8rem !important;
        }
        .gh-kpi {
            flex: 1 1 calc(50% - 0.4rem) !important;
            min-width: calc(50% - 0.4rem) !important;
        }
        .gh-val-big { font-size: 1.15rem !important; }
        .gh-val-med { font-size: 0.98rem !important; }
        .gh-val-sm  { font-size: 0.88rem !important; }
        .gh-val-xs  { font-size: 0.78rem !important; }
        .gh-lbl     { font-size: 0.72rem !important; }
        .gh-pct     { font-size: 0.70rem !important; }

        /* Parent tabs compact on mobile */
        [data-testid="stTabs"] [role="tablist"] [role="tab"] {
            padding: 0.3rem 0.5rem !important;
            font-size: 0.68rem !important;
            font-weight: 600 !important;
        }
        /* Sub-tabs even more compact on mobile */
        [role="tabpanel"] [role="tablist"] [role="tab"] {
            font-size: 0.56rem !important;
            font-weight: 400 !important;
            padding: 3px 5px !important;
            color: #9ca3af !important;
        }
        [role="tabpanel"] [role="tablist"] [role="tab"][aria-selected="true"] {
            color: #374151 !important;
            font-weight: 600 !important;
        }

        /* Smaller page headings */
        h1 { font-size: 1.3rem !important; margin-bottom: 0.3rem !important; }
        h2 { font-size: 1.1rem !important; margin-bottom: 0.2rem !important; }
        h3 { font-size: 0.95rem !important; }

        /* Compact st.metric tiles */
        [data-testid="stMetric"] { padding: 0.2rem 0 !important; }
        [data-testid="stMetricLabel"] p { font-size: 0.7rem !important; }
        [data-testid="stMetricValue"]   { font-size: 1.05rem !important; }

        /* Smaller buttons */
        [data-testid="stButton"] > button {
            font-size: 0.78rem !important;
            padding: 0.3rem 0.5rem !important;
        }

        /* Compact accounts summary strip */
        .acct-summary-row { gap: 1rem; padding-bottom: 6px; }
        .acct-kpi-val { font-size: 1rem !important; }
    }

    /* ══════════════════════════════════════════════════════════════════════
       LANDSCAPE PHONES / SMALL TABLETS  ≤ 1024 px + landscape orientation
       ══════════════════════════════════════════════════════════════════════ */
    @media (max-width: 1024px) and (orientation: landscape) {
        .block-container { padding-top: 0.15rem !important; }
        [data-testid="stHorizontalBlock"]:has(.bousala-appbar) {
            padding-top:    2px !important;
            padding-bottom: 2px !important;
        }
        .bousala-appbar svg { width: 32px !important; height: 32px !important; }
        .gh-kpi-row { gap: 1.4rem !important; flex-wrap: nowrap !important; }
        .gh-val-big { font-size: 1.4rem !important; }
        .gh-val-med { font-size: 1.1rem !important; }
        .gh-val-sm  { font-size: 0.95rem !important; }
        .gh-val-xs  { font-size: 0.82rem !important; }
    }

    /* ── Compact selectbox inside header ────────────────────────────────── */
    [data-testid="stHorizontalBlock"]:has(.bousala-appbar)
    [data-testid="stSelectbox"] { margin-bottom: 0 !important; }

    /* ── Compact expander inside header ─────────────────────────────────── */
    [data-testid="stHorizontalBlock"]:has(.bousala-appbar)
    [data-testid="stExpander"] {
        border: none !important;
        box-shadow: none !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    [data-testid="stHorizontalBlock"]:has(.bousala-appbar)
    [data-testid="stExpander"] summary {
        padding: 2px 4px !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        color: #475569 !important;
        min-height: unset !important;
    }

    /* ── Tab hierarchy: parent tabs bold, sub-tabs compact & secondary ─── */
    /*
     * Streamlit 1.57 ARIA structure (confirmed from bundle):
     *   [role="tablist"]   = the scrollable tab-list bar
     *   [role="tab"]       = each tab button
     *   [role="tabpanel"]  = the content area per active tab
     *
     * Parent tabs are [role="tab"] NOT inside a [role="tabpanel"].
     * Sub-tabs are [role="tab"] INSIDE a [role="tabpanel"].
     * The sub-tab selector is more specific so it always wins.
     */

    /* Parent tabs — prominent (desktop / tablet) */
    [data-testid="stTabs"] [role="tablist"] [role="tab"] {
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em !important;
    }

    /* Sub-tabs — clearly secondary */
    [role="tabpanel"] [role="tablist"] [role="tab"] {
        font-size: 0.68rem !important;
        font-weight: 400 !important;
        color: #6b7280 !important;
        padding: 4px 8px !important;
        letter-spacing: 0 !important;
    }

    /* Active sub-tab */
    [role="tabpanel"] [role="tablist"] [role="tab"][aria-selected="true"] {
        font-weight: 600 !important;
        color: #1e293b !important;
    }

    /* Sub-tab bar — thinner divider, tighter spacing */
    [role="tabpanel"] [role="tablist"] {
        border-bottom: 1px solid #e2e8f0 !important;
        margin-bottom: 0.2rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
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


# ── Centralised money formatter (T11 / U6) ────────────────────────────────────
def _fmt_money(val: float, ccy: str = "", decimals: int = 0) -> str:
    """
    Format a monetary value with thousands separator.

    Examples:
        _fmt_money(1234567.8, "SAR")      → "1,234,568 SAR"
        _fmt_money(1234.5, "USD", 2)      → "1,234.50 USD"
        _fmt_money(12.3456, decimals=2)   → "12.35"
    """
    s = f"{val:,.{decimals}f}"
    return f"{s} {ccy}".rstrip() if ccy else s


def _fmt_pct(val: float | None, decimals: int = 1, suffix: str = "%") -> str:
    """Format a percentage; returns '—' when val is None."""
    if val is None:
        return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.{decimals}f}{suffix}"


def _fmt_compact(v: float) -> str:
    """Compact money label: 2dp millions, 1dp thousands, 2dp otherwise.

    Delegates to the shared canonical formatter (portfolio.display_metrics) so
    the Holdings/Allocation and Balance Sheet KPIs can never drift apart.

    Examples:
        _fmt_compact(1_234_567.8)  → "1.23M"
        _fmt_compact(12_345.6)     → "12.3K"
        _fmt_compact(999.99)       → "999.99"
    """
    return fmt_money_compact(v)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div class="bousala-title" style="padding:0.6rem 0 0.2rem 0;">
          <div style="font-size:2rem; line-height:1.2;">🧭</div>
          <div style="font-size:1.4rem; font-weight:700;">بوصلة</div>
          <div style="font-size:0.82rem; color:#888; margin-top:0.15rem;">بوصلة المستثمر</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    # ── 1. Family Wealth Statement ────────────────────────────────────────────
    st.caption("📄 **Family Wealth Statement**")
    st.caption(
        "A professional PDF your family can open and understand — "
        "all assets, values, and account locations in one document."
    )
    _ws_notes = st.text_area(
        "Personal note (optional)",
        key="ws_notes",
        placeholder=(
            "E.g. Accounts are at Al Rajhi Bank. "
            "Contact Ahmed on +966 5X XXX XXXX for access."
        ),
        max_chars=800,
        height=90,
    )
    _ws_base_ccy = st.session_state.get("global_base_ccy", "SAR")
    if _ws_base_ccy == "— Native —":
        _ws_base_ccy = "SAR"
    try:
        from portfolio.wealth_statement import build_wealth_statement as _build_ws
        import datetime as _wdt
        _ws_fname = f"bousala_wealth_{_wdt.date.today().strftime('%Y%m%d')}.pdf"
        _ws_bytes = _build_ws(base_ccy=_ws_base_ccy, notes=_ws_notes or "")
        st.download_button(
            "📥 Download Wealth Statement PDF",
            data=_ws_bytes,
            file_name=_ws_fname,
            mime="application/pdf",
            use_container_width=True,
            key="ws_download_btn",
            help="Downloads a family-friendly Arabic wealth summary PDF.",
        )
    except Exception as _ws_err:
        st.error(f"Could not generate PDF: {_ws_err}", icon="⚠️")

    st.divider()

    # ── 3. Settings (collapsed by default) ───────────────────────────────────
    with st.expander("⚙️ Settings", expanded=False):
        # ── Price Data Provider — shown first so it's visible immediately ─────
        st.caption("📡 **Price Data Provider**")
        _sahmk_key_present = bool(__import__("os").environ.get("SAHMK_API_KEY", "").strip())
        _sahmk_opts = ["SAHMK + Yahoo", "Yahoo only"]
        _sahmk_choice = st.radio(
            "Provider",
            _sahmk_opts,
            index=1,   # Yahoo only by default — SAHMK requires an active subscription
            key="sahmk_provider_mode",
            label_visibility="collapsed",
            help=(
                "**SAHMK + Yahoo** — Saudi stocks fetched from SAHMK (requires active subscription); "
                "all others via Yahoo Finance.\n\n"
                "**Yahoo only** — all tickers via Yahoo Finance. Bare 4-5 digit Saudi symbols "
                "(e.g. 2222) are auto-suffixed to .SR automatically."
            ),
        )
        if _sahmk_key_present and _sahmk_choice == "SAHMK + Yahoo":
            st.caption("✅ SAHMK active.")
        elif not _sahmk_key_present and _sahmk_choice == "SAHMK + Yahoo":
            st.caption("⚠️ SAHMK_API_KEY not set — add it in Secrets.")
        else:
            st.caption("ℹ️ Yahoo only — Discovery Console unavailable.")

        st.divider()
        st.toggle(
            "Live FX Rates",
            value=False,
            key="live_fx_enabled",
            help=(
                "OFF (default): uses static built-in rates — instant, no network call. "
                "SAR/AED/QAR are USD-pegged and rarely change. "
                "ON: fetches live rates from Yahoo Finance (adds ~2–3 s per refresh)."
            ),
        )
        st.divider()
        # ── Auto-refresh ──────────────────────────────────────────────────
        st.caption("⏱ **Auto-refresh Prices**")
        mp_auto_on = st.toggle(
            "Auto-refresh",
            value=False,
            key="mp_auto_on",
            help="Automatically re-fetch live prices at the chosen interval.",
        )
        mp_interval = st.selectbox(
            "Frequency",
            ["1 minute", "5 minutes", "15 minutes"],
            index=1,
            key="mp_interval",
            disabled=not mp_auto_on,
        )
        _sb_last = st.session_state.get("mp_last_refresh")
        if _sb_last:
            st.caption(f"Last refresh: **{_sb_last}**")
        st.button(
            "💱 Refresh FX Rates",
            key="sb_refresh_fx_btn",
            use_container_width=True,
            help="Fetch live exchange rates from Yahoo Finance. FX rates are used to convert holdings to your base currency.",
        )
        st.divider()
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

        # ── Data Backup & Restore ─────────────────────────────────────────────
        st.divider()
        st.caption("💾 **Data Backup & Restore**")
        st.caption(
            "Export your entire portfolio to a file, then import it on any device "
            "or in the published app to keep your data in sync."
        )

        from portfolio.data_backup import export_bundle_bytes, import_bundle

        _bk_bytes, _bk_name = export_bundle_bytes()
        st.download_button(
            "⬇️ Export all data",
            data=_bk_bytes,
            file_name=_bk_name,
            mime="application/json",
            use_container_width=True,
            help="Downloads a single .json file with all your holdings, transactions, accounts, and settings.",
        )

        _uploaded_backup = st.file_uploader(
            "⬆️ Import from backup",
            type=["json"],
            key="backup_upload",
            help="Upload a .json file previously exported from Bousala to restore your data.",
        )
        if _uploaded_backup is not None:
            st.warning(
                "⚠️ This will **overwrite** all current data with the backup. "
                "Make sure you've exported the current data first if you want to keep it.",
                icon="⚠️",
            )
            if st.button("✅ Confirm Restore", type="primary", use_container_width=True, key="confirm_restore"):
                _ok, _msg = import_bundle(_uploaded_backup.read())
                if _ok:
                    st.success(_msg, icon="✅")
                    st.rerun()
                else:
                    st.error(_msg, icon="❌")

        st.divider()
        st.checkbox(
            "🔧 Developer Mode",
            key="dev_mode",
            value=False,
            help="Show technical diagnostics and FX reconciliation tables.",
        )

        _fw_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Bousala_NetWorth_Framework.txt")
        if os.path.exists(_fw_path):
            st.divider()
            st.caption("📄 **Dev Downloads**")
            with open(_fw_path, "rb") as _fw_f:
                st.download_button(
                    "📥 Framework Doc (.txt)",
                    data=_fw_f,
                    file_name="Bousala_NetWorth_Framework.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            _tsx_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "BousalaScreens.tsx")
            if os.path.exists(_tsx_path):
                with open(_tsx_path, "rb") as _tsx_f:
                    st.download_button(
                        "📥 App Screens (.tsx)",
                        data=_tsx_f,
                        file_name="BousalaScreens.tsx",
                        mime="text/plain",
                        use_container_width=True,
                    )

    # ── Help & User Guide ─────────────────────────────────────────────────────
    st.divider()
    if st.button(
        "❓  Help & User Guide",
        key="sidebar_help_btn",
        use_container_width=True,
        help="Open the full beginner-friendly user guide — no finance background needed.",
    ):
        st.session_state["show_help"] = not st.session_state.get("show_help", False)
    if st.session_state.get("show_help", False):
        st.caption("📖 Viewing user guide — tap above to close.")

_analyze_enabled = _ai_ready or demo_mode


# ── Market price auto-refresh logic ──────────────────────────────────────────
# Placed here (top-level, after sidebar) so it runs on every page render
# before any tab content.  AI calls only happen inside explicit button handlers
# lower in this file — auto-refresh reruns will never reach them.

_MP_INTERVAL_MS = {
    "1 minute":   60_000,
    "5 minutes":  300_000,
    "15 minutes": 900_000,
}


def _collect_all_tickers() -> list[str]:
    """Return sorted list of all tickers from watchlist + holdings (no AI calls)."""
    from portfolio import load_portfolio, load_holdings
    try:
        return sorted(
            set(list(load_portfolio().keys())
                + [h.ticker for h in load_holdings().values()])
        )
    except Exception:
        return []


def _normalize_ticker(ticker: str) -> str:
    """
    Normalize exchange suffix for yfinance compatibility.
    Saudi Exchange: .SE is invalid — replace with .SR.
    e.g. 2222.SE → 2222.SR, 1120.SE → 1120.SR
    """
    t = ticker.strip()
    if t.upper().endswith(".SE"):
        return t[:-3] + ".SR"
    return t


def _apply_prices_to_holdings(
    fetched: dict,
    holdings: dict | None = None,
) -> tuple[list[str], list[str]]:
    """
    Immediately write successful fetch results to holdings storage.
    Tickers whose fetch failed keep their previously stored price — untouched.
    Returns (ok_list, fail_list).
    """
    from portfolio import update_current_price, load_holdings as _lh
    _h = holdings if holdings is not None else _lh()
    ok_list:   list[str] = []
    fail_list: list[str] = []
    # Build ticker → [asset_id] reverse-map (holdings are now keyed by asset_id)
    _by_ticker: dict[str, list[str]] = {}
    for _aid, _hld in _h.items():
        _by_ticker.setdefault(_hld.ticker, []).append(_aid)
    for ticker, md in fetched.items():
        _aids = _by_ticker.get(ticker, [])
        if not _aids:
            continue  # watchlist-only ticker — not an actual holding
        for _aid in _aids:
            try:
                if md.is_ok and md.current_price:
                    update_current_price(_aid, float(md.current_price), source="yfinance")
                    ok_list.append(ticker)
                else:
                    fail_list.append(ticker)
            except Exception:
                fail_list.append(ticker)
    return ok_list, fail_list


def _apply_routed_prices(
    routed: dict,
    holdings: dict | None = None,
) -> tuple[list[str], list[str]]:
    """
    Write routed price results (from market_data_router) to holdings storage.
    *routed* is keyed by asset_id (same keys that refresh_holdings_prices received).
    Records the actual provider ("SAHMK", "yfinance", "cached", "manual").
    Returns (ok_list, fail_list).
    """
    from portfolio import update_current_price, load_holdings as _lh
    _h = holdings if holdings is not None else _lh()
    ok_list:   list[str] = []
    fail_list: list[str] = []
    for asset_id, rp in routed.items():
        if asset_id not in _h:
            continue
        try:
            if rp.is_ok and rp.price:
                update_current_price(asset_id, float(rp.price), source=rp.provider)
                ok_list.append(asset_id)
            else:
                fail_list.append(asset_id)
        except Exception:
            fail_list.append(asset_id)
    return ok_list, fail_list


def _run_price_refresh(*, force: bool = True) -> int:
    """
    Refresh market prices for every known ticker using the multi-provider router.

    Holdings with an exchange_symbol go through SAHMK first (unless the user has
    selected "Yahoo only" in Settings); all others fall through to yfinance then
    cached/manual.  Watchlist-only tickers are still fetched via yfinance and
    stored in the session cache for UI display.
    Returns the count of tickers successfully updated.
    """
    from market_prices import refresh_all_prices, save_to_session, MarketData
    from market_data_router import refresh_holdings_prices, PROVIDER_SAHMK
    from portfolio import load_holdings as _lh_inner
    import datetime as _rpr_dt
    try:
        # Read the provider toggle set by the user in sidebar Settings
        _sahmk_on = st.session_state.get("sahmk_provider_mode", "SAHMK + Yahoo") != "Yahoo only"

        # ── Routed refresh for actual holdings ────────────────────────────────
        _holdings_inner = _lh_inner()
        ok_count = 0
        _routed_all: dict = {}
        if _holdings_inner:
            _routed_all = refresh_holdings_prices(
                _holdings_inner, force=force, sahmk_enabled=_sahmk_on
            )
            ok_list, _ = _apply_routed_prices(_routed_all, _holdings_inner)
            ok_count = len(ok_list)

            # ── Collect SAHMK change_pct entries to bridge into session cache ──
            # Saved AFTER yfinance so SAHMK daily_change_pct is not overwritten
            # by a yfinance entry that has daily_change_pct=None for Saudi tickers.
            _sahmk_md: dict[str, MarketData] = {}
            for _aid, _rp in _routed_all.items():
                if (
                    _rp.provider == PROVIDER_SAHMK
                    and _rp.is_ok
                    and _rp.change_pct is not None
                ):
                    _hld = _holdings_inner.get(_aid)
                    if _hld and _hld.ticker:
                        _norm = _normalize_ticker(_hld.ticker)
                        _sahmk_md[_norm] = MarketData(
                            ticker           = _norm,
                            current_price    = _rp.price,
                            price_source     = "SAHMK",
                            price_timestamp  = _rp.updated_at or _rpr_dt.datetime.utcnow().isoformat(),
                            daily_change_pct = _rp.change_pct,
                            currency         = _rp.currency or "SAR",
                        )

        # ── yfinance session cache for watchlist / price-debug UI ─────────────
        raw_tickers = _collect_all_tickers()
        if raw_tickers:
            ticker_map = {_normalize_ticker(t): t for t in raw_tickers}
            results = refresh_all_prices(list(ticker_map.keys()), force=force)
            save_to_session(results)

        # ── Bridge SAHMK change_pct AFTER yfinance so SAHMK wins ─────────────
        # yfinance returns daily_change_pct=None for Saudi tickers; saving SAHMK
        # data last ensures the Holdings table Day % column sees the real value.
        if _sahmk_md:
            save_to_session(_sahmk_md)

        return ok_count
    except Exception:
        return 0


# 1. Skip automatic blocking price fetch on session start — app loads instantly
#    with last-saved prices.  User taps 🔄 Refresh Prices when live data needed.
if "mp_initial_done" not in st.session_state:
    st.session_state["mp_initial_done"] = True

# 2. Periodic auto-refresh via st_autorefresh (hidden component)
if st.session_state.get("mp_auto_on", False):
    try:
        from streamlit_autorefresh import st_autorefresh
        _ar_interval_ms = _MP_INTERVAL_MS.get(
            st.session_state.get("mp_interval", "5 minutes"), 300_000
        )
        _ar_count = st_autorefresh(interval=_ar_interval_ms, key="mp_ar",
                                   debounce=False)
        # st_autorefresh increments its counter each time it fires a rerun.
        # Compare with stored count to detect auto-rerun vs user interaction.
        _prev_ar = st.session_state.get("mp_last_ar_count", -1)
        if _ar_count != _prev_ar:
            st.session_state["mp_last_ar_count"] = _ar_count
            if _ar_count > 0:           # skip count=0 (initial page render)
                _run_price_refresh(force=True)
    except ImportError:
        pass   # streamlit-autorefresh not installed — degrade gracefully


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
    filing: "Filing",
    company_name: str,
    ticker: str,
    index: int,
    previous_filing: "Filing | None" = None,
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
    filings: "list[Filing]",
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


# ── Promote-to-Holding dialog (module-level so any tab can call it) ───────────
@st.dialog("🚀 Promote to Holding", width="large")
def _dlg_promote_holding() -> None:
    """
    Full "Open New Position" dialog pre-filled from watchlist data.
    Caller must store a dict under st.session_state["_promo_prefill"] before calling:
        ticker, name, price, currency, market, sector
    Records a BUY transaction, updates holdings, and debits account cash —
    identical to the Holdings tab "Add New Position" workflow.
    """
    from datetime import date as _dt_cls
    from portfolio import (
        CURRENCIES, MARKETS, DEFAULT_SECTORS,
        record_transaction, upsert_holding, load_holdings, update_current_price,
    )
    from portfolio.accounts import (
        active_accounts      as _promo_active_accts,
        account_display_name as _promo_acct_dn,
        update_account_cash  as _promo_upd_cash,
        load_accounts        as _promo_load_accts,
    )

    # ── Pre-fill on first open (pop so it doesn't override user edits on reruns) ─
    _pf = st.session_state.pop("_promo_prefill", None)
    if _pf:
        st.session_state["promo_tk"]    = _pf.get("ticker",   "")
        st.session_state["promo_name"]  = _pf.get("name",     "")
        st.session_state["promo_price"] = float(_pf.get("price",    0.0))
        st.session_state["promo_cost"]  = float(_pf.get("price",    0.0))
        st.session_state["promo_ccy"]   = _pf.get("currency", "USD")
        st.session_state["promo_mkt"]   = _pf.get("market",   "Other")
        st.session_state["promo_sec"]   = _pf.get("sector",   "Other")
        st.session_state["promo_qty"]   = 1.0

    _ptk = st.session_state.get("promo_tk", "")

    # ── Duplicate guard ───────────────────────────────────────────────────────
    _existing = next(
        (h for h in load_holdings().values()
         if h.ticker == _ptk and h.quantity > 1e-9),
        None,
    )
    if _existing:
        st.info(
            f"**{_ptk}** is already in your Holdings "
            f"({_existing.quantity:,.4f} shares @ {_existing.avg_cost:,.4f}). "
            "Use **Buy More** from the Holdings tab instead.",
            icon="✅",
        )
        return

    st.caption(
        f"Pre-filled from watchlist research on **{_ptk}**. "
        "An opening BUY transaction is recorded — "
        "this position gets full cost-basis history from day one."
    )

    # ── Form fields ───────────────────────────────────────────────────────────
    _pf1, _pf2 = st.columns(2)
    with _pf1:
        st.text_input("Ticker (from watchlist)", key="promo_tk", disabled=True)
        _pname = st.text_input("Company / Asset name", key="promo_name")
        _pmkt  = st.selectbox("Market",  MARKETS,          key="promo_mkt")
        _psec  = st.selectbox("Sector",  DEFAULT_SECTORS,  key="promo_sec")
    with _pf2:
        _pccy   = st.selectbox("Currency", CURRENCIES, key="promo_ccy")
        _pqty   = st.number_input("Opening quantity",       min_value=0.0001, step=1.0,  format="%.4f", key="promo_qty",   value=1.0)
        _pcost  = st.number_input("Opening price per unit", min_value=0.0,    step=0.01, format="%.4f", key="promo_cost",  value=0.0)
        _pprice = st.number_input("Current market price",   min_value=0.0,    step=0.01, format="%.4f", key="promo_price", value=0.0)

    # ── Account (filtered by currency) ────────────────────────────────────────
    _all_accts  = _promo_active_accts()
    _ccy_accts  = [a for a in _all_accts if a.base_currency == _pccy]
    _use_accts  = _ccy_accts or _all_accts
    if not _use_accts:
        st.warning("No active accounts. Add one in the Accounts tab first.", icon="⚠️")
        return
    if not _ccy_accts and _all_accts:
        st.caption(f"ℹ️ No {_pccy} accounts — showing all currencies.")
    _acct_opts = {"": "— no account —"}
    for _a in _use_accts:
        _acct_opts[_a.account_id] = _promo_acct_dn(_a)

    _pa1, _pa2 = st.columns(2)
    with _pa1:
        _paid   = st.selectbox(
            f"Link to account ({_pccy})",
            options=list(_acct_opts.keys()),
            format_func=lambda k: _acct_opts[k],
            key="promo_acct",
        )
        _pfees  = st.number_input("Transaction fees", min_value=0.0, value=0.0, step=0.01, format="%.2f", key="promo_fees")
    with _pa2:
        _pdate  = st.date_input("Trade date",        value=_dt_cls.today(), key="promo_date")
        _pnotes = st.text_input("Notes (optional)",  max_chars=200,         key="promo_notes")

    # ── Cash balance preview ──────────────────────────────────────────────────
    _ptotal   = float(_pqty) * float(_pcost) + float(_pfees)
    _cash_ok  = True
    if _paid:
        try:
            _bal = _promo_load_accts()[_paid].cash_balance
            _rem = _bal - _ptotal
            _cash_ok = _rem >= 0
            _ck1, _ck2, _ck3 = st.columns(3)
            _ck1.metric("Opening Cost",   f"{_ptotal:,.2f} {_pccy}")
            _ck2.metric("Account Cash",   f"{_bal:,.2f} {_pccy}")
            _ck3.metric("Remaining Cash", f"{_rem:,.2f} {_pccy}",
                        delta=f"{_rem:+,.2f}", delta_color="normal" if _cash_ok else "inverse")
            if not _cash_ok:
                st.error("Insufficient cash balance.", icon="🚫")
        except Exception:
            st.caption(f"Opening cost: **{_ptotal:,.2f} {_pccy}**")
    else:
        st.caption(f"Opening cost: **{_ptotal:,.2f} {_pccy}**")

    # ── Submit / Cancel ───────────────────────────────────────────────────────
    _sb1, _sb2 = st.columns(2)
    _PROMO_KEYS = ("promo_tk","promo_name","promo_price","promo_cost","promo_ccy",
                   "promo_mkt","promo_sec","promo_qty","promo_acct","promo_fees",
                   "promo_date","promo_notes")
    with _sb1:
        if st.button(
            "🚀 Promote to Holding", type="primary", use_container_width=True,
            key="promo_submit",
            disabled=(not _ptk or not _cash_ok),
        ):
            try:
                _ptk_clean = _ptk.strip().upper()
                _t, _h, _err = record_transaction(
                    ticker=_ptk_clean, side="BUY",
                    quantity=float(_pqty),
                    price=float(_pcost),
                    txn_date=str(_pdate) if _pdate else None,
                    notes=_pnotes or "Promoted from Watchlist",
                    company_name=_pname.strip() or _ptk_clean,
                    market=_pmkt, sector=_psec,
                    asset_type="Stock", currency=_pccy,
                    has_ticker=True,
                    account_id=_paid, fees=float(_pfees),
                )
                if _err:
                    st.error(_err)
                else:
                    if float(_pprice) > 0 and abs(float(_pprice) - float(_pcost)) > 1e-9:
                        update_current_price(_h.asset_id, float(_pprice), source="yfinance")
                    if _paid:
                        try:
                            _promo_upd_cash(_paid, -_ptotal)
                        except Exception:
                            pass
                    for _dk in _PROMO_KEYS:
                        st.session_state.pop(_dk, None)
                    st.toast(
                        f"**{_ptk_clean}** promoted to Holdings! "
                        f"{float(_pqty):,.4f} shares @ {_pccy} {float(_pcost):,.4f}",
                        icon="🚀",
                    )
                    st.rerun()
            except Exception as _ex:
                st.error(f"Failed to promote — {_ex}")
    with _sb2:
        if st.button("Cancel", key="promo_cancel", use_container_width=True):
            for _dk in _PROMO_KEYS:
                st.session_state.pop(_dk, None)
            st.rerun()


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
        from market_prices import (
            get_all_from_session, market_session_label,
            refresh_all_prices, save_to_session,
        )
        wl_tickers = list(portfolio.keys())
        sess_icon, sess_label = market_session_label()

        wl_r1, wl_r2, wl_r3 = st.columns([1, 2, 3])
        with wl_r1:
            if st.button(
                "🔄 Refresh Market Prices",
                use_container_width=True,
                key="refresh_mp_watchlist",
                help="Force-fetches live prices from yfinance, bypassing cache.",
            ):
                with st.spinner("Fetching live prices…"):
                    fetched = refresh_all_prices(wl_tickers, force=True)
                save_to_session(fetched)
                ok = [t for t, d in fetched.items() if d.is_ok]
                if ok:
                    st.toast(f"Fetched prices for {len(ok)} ticker(s)", icon="📡")
                st.rerun()
        with wl_r2:
            st.caption(f"{sess_icon} {sess_label}")
        with wl_r3:
            last_ref = st.session_state.get("mp_last_refresh")
            if last_ref:
                st.caption(f"Last refreshed at {last_ref}")

        wl_live = get_all_from_session()
        st.caption(f"{len(portfolio)} ticker(s) on watchlist")
        for ticker, entry in sorted(portfolio.items()):
            t_icon = _IMPACT_COLOR.get(entry.thesis_status, "⚪")
            a_icon = _ACTION_COLOR.get(entry.recommended_action, "⚪")
            md     = wl_live.get(ticker)

            with st.container(border=True):
                hcol1, hcol2, hcol3 = st.columns([2, 3, 1])
                with hcol1:
                    st.markdown(f"### {ticker}")
                    st.caption(entry.company_name)
                    if md and md.is_ok:
                        st.caption(
                            f"{md.day_indicator} **{md.current_price:,.4f} {md.currency}**"
                            f"  ·  {md.change_str}"
                        )
                    elif md and not md.is_ok:
                        st.caption("⚪ Market data unavailable")
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

                # ── Promote to Holding (research-only watchlist; full workflow) ──
                _wl_existing = next((h for h in holdings.values() if h.ticker == ticker), None)
                if _wl_existing:
                    st.caption(
                        f"✅ Already held · {_wl_existing.quantity:,.4f} shares @ "
                        f"{_wl_existing.avg_cost:,.4f} · "
                        "Use **Buy More** in the Holdings tab to add more."
                    )
                else:
                    if st.button(
                        "🚀 Promote to Holding",
                        key=f"promo_btn_{ticker}",
                        help=(
                            "Opens a full position with BUY transaction record, "
                            "account linkage, and cost-basis tracking."
                        ),
                    ):
                        _wl_md = wl_live.get(ticker)
                        _wl_pccy = (
                            _wl_md.currency
                            if (_wl_md and _wl_md.is_ok and _wl_md.currency)
                            else "USD"
                        )
                        st.session_state["_promo_prefill"] = {
                            "ticker":   ticker,
                            "name":     entry.company_name or ticker,
                            "price":    float(_wl_md.current_price) if (_wl_md and _wl_md.is_ok) else 0.0,
                            "currency": _wl_pccy,
                            "market": (
                                "US"     if _wl_pccy == "USD" else
                                "Saudi"  if _wl_pccy == "SAR" else
                                "UK"     if _wl_pccy == "GBP" else
                                "Europe" if _wl_pccy in {"EUR","CHF","DKK","SEK","NOK"} else
                                "Asia"   if _wl_pccy in {"JPY","HKD","SGD","CNY","KRW","AUD","NZD"} else
                                "Other"
                            ),
                            "sector": "Other",
                        }
                        _dlg_promote_holding()

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


def _render_valuation_debug(val) -> None:
    """
    Collapsible valuation reconciliation section.
    Only visible when Developer Mode is enabled in the sidebar.
    Pass the PortfolioValuation returned by calculate_portfolio_valuation().
    """
    if not st.session_state.get("dev_mode", False):
        return
    if not val or not val.per_holding:
        return

    import pandas as pd

    with st.expander("🔍 Valuation Reconciliation & FX Debug", expanded=False):

        st.caption(
            f"All values in **{val.base_currency}**. "
            f"Computed at {val.valuation_timestamp[:19]}."
        )

        # ── Per-holding table ──────────────────────────────────────────────────
        st.markdown("**Per-holding breakdown**")
        rows = []
        for r in val.per_holding:
            rows.append({
                "Ticker":         r.ticker,
                "Qty":            r.quantity,
                "Price":          round(r.current_price, 4),
                "Local Ccy":      r.local_currency,
                "Local MV":       round(r.local_market_value, 2),
                "FX Rate":        round(r.fx_rate, 6),
                "FX Src":         r.fx_source,
                f"Base MV ({val.base_currency})":  round(r.base_market_value, 2),
                f"Base P&L ({val.base_currency})": round(r.base_unrealized_pnl, 2),
                "Wt% (invested)": f"{r.invested_weight_pct:.2f}%",
                "Wt% (total)":    f"{r.total_weight_pct:.2f}%",
                "⚠️":             r.warning or "—",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        # ── FX rates table ──────────────────────────────────────────────────────
        st.markdown("**FX rates used**")
        fx_rows = []
        for ccy, fxr in sorted(val.fx_rates_used.items()):
            fx_rows.append({
                "Pair":         f"{ccy}→{val.base_currency}",
                "Rate":         round(fxr.rate, 6),
                "Source":       fxr.source,
                "Fetched":      fxr.fetched_at[:19],
            })
        if fx_rows:
            st.dataframe(pd.DataFrame(fx_rows), hide_index=True, use_container_width=True)
        else:
            st.caption("No FX pairs used (single-currency portfolio).")

        # ── Totals reconciliation ───────────────────────────────────────────────
        st.markdown("**Totals reconciliation**")
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric(f"Holdings ({val.base_currency})", _fmt_money(val.holdings_value_base, val.base_currency, 2))
        rc2.metric(f"Cash ({val.base_currency})",     _fmt_money(val.cash_value_base, val.base_currency, 2))
        rc3.metric("Total Portfolio",                  _fmt_money(val.total_portfolio_value_base, val.base_currency, 2))
        _wt_sum = round(sum(r.invested_weight_pct for r in val.per_holding), 1)
        rc4.metric("Weight Sum Check", f"{_wt_sum}% (should be ≈100%)")

        # ── Warnings ───────────────────────────────────────────────────────────
        if val.warnings:
            st.markdown("**Warnings**")
            for w in val.warnings:
                st.warning(w, icon="⚠️")
        else:
            st.success("✅ No valuation warnings.", icon="✅")


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

    # ── Centralized valuation (for base-currency totals) ──────────────────────
    from portfolio.valuation import calculate_portfolio_valuation
    from portfolio.accounts import load_accounts as _load_accts_risk
    from fx_rates import get_rates_for_holdings as _gfx_risk
    _base_ccy_risk = st.session_state.get("global_base_ccy", "SAR")
    if _base_ccy_risk == "— Native —":
        _base_ccy_risk = "SAR"
    _ccys_risk = list({getattr(h, "currency", "USD") for h in holdings.values()})
    _fx_risk   = _gfx_risk(_ccys_risk, _base_ccy_risk) if _ccys_risk else {}
    _val_risk  = calculate_portfolio_valuation(
        holdings, _load_accts_risk(), _base_ccy_risk, fx_rates=_fx_risk
    )

    # ── Risk score header ─────────────────────────────────────────────────────
    icon, label = RISK_REGIME_BADGE.get(result.risk_regime, ("⚪", result.risk_regime))
    score_cols = st.columns([1, 1, 1, 1, 1])
    with score_cols[0]:
        st.metric("Portfolio Risk Score", f"{result.risk_score}/100")
    with score_cols[1]:
        st.metric("Risk Regime", f"{icon} {label}")
    with score_cols[2]:
        st.metric("Positions", result.n_positions)
    with score_cols[3]:
        st.metric(
            f"Holdings ({_base_ccy_risk})",
            f"{_val_risk.holdings_value_base:,.2f}",
        )
    with score_cols[4]:
        st.metric(
            f"Total Portfolio ({_base_ccy_risk})",
            f"{_val_risk.total_portfolio_value_base:,.2f}",
        )

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
    st.table(cat_df.set_index("Category"))

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
                "Priority":    f"{p.priority_score}/100" if p.priority_score > 0 else "—",
                "Uncertainty": p.uncertainty_level,
                "Mkt Align":   mi_score,
            })
        _detail_df = pd.DataFrame(detail_rows).astype(str)
        st.table(_detail_df.set_index("Ticker"))

    st.caption(f"Computed at {result.computed_at}")

    _render_valuation_debug(_val_risk)


def _render_allocation_section(val, holdings: dict, base_ccy: str) -> None:
    """
    Portfolio Allocation charts — shown at the bottom of the Holdings tab.
    All values come from PortfolioValuation.per_holding (FX-converted, consistent).
    Supports multi-select filters, click-to-filter on pie slices, and PDF/CSV export.
    """
    import io as _io
    import os as _os
    import tempfile as _tmp
    import plotly.graph_objects as go
    import pandas as pd
    from datetime import datetime

    st.subheader("📊 Portfolio Allocation")

    # ── Build allocation rows from valuation engine ───────────────────────────
    # holdings is keyed by asset_id (AST_NNNNNN); build a ticker→holding map
    _h_by_ticker = {h.ticker: h for h in holdings.values()}
    _excluded: list[str] = []
    _rows: list[dict] = []
    for _r in val.per_holding:
        _h = _h_by_ticker.get(_r.ticker)
        if _h is None:
            continue
        if _r.missing_price or _r.missing_fx:
            _excluded.append(_r.ticker)
            continue
        if _r.base_market_value <= 0:
            continue
        _rows.append({
            "Ticker":    _r.ticker,
            "Company":   getattr(_h, "company_name", _r.ticker) or _r.ticker,
            "Market":    getattr(_h, "market",      "Other"),
            "Sector":    getattr(_h, "sector",      "Other"),
            "AssetType": getattr(_h, "asset_type",  "Other") or "Other",
            "CCY":       _r.local_currency,
            "_mv":       _r.base_market_value,
            "_cb":       _r.base_cost_basis,
            "_wt":       _r.invested_weight_pct,
        })

    if _excluded:
        st.caption(
            f"⚠️ Excluded from allocation charts (missing price or FX): "
            f"**{', '.join(_excluded)}** — tap 🔄 to refresh prices. "
            f"Holdings missing only FX are still counted in the unfiltered "
            f"Market Value (fallback rate 1.0), matching the Balance Sheet."
        )

    if not _rows:
        st.info("Add holdings and refresh prices to see allocation charts.", icon="📊")
        return

    _df = pd.DataFrame(_rows)

    # ── Market values (full set — needed for click-to-filter map) ────────────
    _all_markets   = sorted(_df["Market"].unique().tolist())

    # ── Quick market presets — horizontal radio (portrait-safe) ──────────────
    _cur_mkt    = st.session_state.get("alloc_ms_market", [])
    _qp_options = ["🇸🇦 Saudi", "🇺🇸 US", "🌐 All"]
    _qp_default = ("🇸🇦 Saudi" if _cur_mkt == ["Saudi"]
                   else "🇺🇸 US" if _cur_mkt == ["US"]
                   else "🌐 All")
    _qp_choice  = st.radio(
        "Quick Preset",
        _qp_options,
        index=_qp_options.index(_qp_default),
        horizontal=True,
        label_visibility="collapsed",
        key="alloc_qp_radio",
    )
    if _qp_choice == "🇸🇦 Saudi" and _cur_mkt != ["Saudi"]:
        st.session_state["alloc_ms_market"] = ["Saudi"]
        st.rerun()
    elif _qp_choice == "🇺🇸 US" and _cur_mkt != ["US"]:
        st.session_state["alloc_ms_market"] = ["US"]
        st.rerun()
    elif _qp_choice == "🌐 All" and _cur_mkt:
        st.session_state.pop("alloc_ms_market", None)
        st.rerun()

    # ── Market scope (sole source: quick preset radio) ────────────────────────
    if _qp_choice == "🇸🇦 Saudi":
        market_scope: list[str] | None = ["Saudi"]
    elif _qp_choice == "🇺🇸 US":
        market_scope = ["US"]
    else:
        market_scope = None  # All markets — no restriction

    # Market-scoped base DataFrame — child filters operate within this scope
    _mkt_df = _df[_df["Market"].isin(market_scope)] if market_scope else _df

    # Child filter option lists scoped to active market preset
    _all_sectors    = sorted(_mkt_df["Sector"].unique().tolist())
    _all_ccys_u     = sorted(_mkt_df["CCY"].unique().tolist())
    _all_companies  = sorted(_mkt_df["Company"].unique().tolist())
    _all_atypes     = sorted(_mkt_df["AssetType"].unique().tolist())

    # Purge stale child filter state — remove any stored values that no longer
    # exist within the new market scope (prevents false "No holdings match" msg)
    for _k, _valid in [
        ("alloc_ms_sector", _all_sectors),
        ("alloc_ms_ccy",    _all_ccys_u),
        ("alloc_ms_asset",  _all_companies),
        ("alloc_ms_atype",  _all_atypes),
    ]:
        _stored = st.session_state.get(_k)
        if _stored and not all(v in _valid for v in _stored):
            st.session_state.pop(_k, None)

    # ── Chart view ────────────────────────────────────────────────────────────
    _view = st.selectbox(
        "Chart view",
        ["By Market", "By Asset", "By Asset Type", "By Sector", "By Currency"],
        key="alloc_chart_view",
    )
    _grp = {
        "By Asset":      "Company",
        "By Asset Type": "AssetType",
        "By Sector":     "Sector",
        "By Market":     "Market",
        "By Currency":   "CCY",
    }[_view]

    # ── Multi-select filters (collapsible to keep the UI compact) ────────────
    with st.expander("🔍 Filters", expanded=False):
        _fc1, _fc2 = st.columns(2)
        with _fc1:
            _sel_sectors   = st.multiselect(
                "Sector", _all_sectors,
                default=st.session_state.get("alloc_ms_sector", _all_sectors),
                key="alloc_ms_sector",
            )
            _sel_atypes    = st.multiselect(
                "Asset Type", _all_atypes,
                default=st.session_state.get("alloc_ms_atype", _all_atypes),
                key="alloc_ms_atype",
            )

        with _fc2:
            _sel_ccys_u    = st.multiselect(
                "Currency", _all_ccys_u,
                default=st.session_state.get("alloc_ms_ccy", _all_ccys_u),
                key="alloc_ms_ccy",
            )
            _sel_companies = st.multiselect(
                "Assets", _all_companies,
                default=st.session_state.get("alloc_ms_asset", _all_companies),
                key="alloc_ms_asset",
            )
        if st.button("↺ Reset filters", key="alloc_reset_filters"):
            for _k in ("alloc_ms_sector", "alloc_ms_ccy", "alloc_ms_asset", "alloc_ms_atype"):
                st.session_state.pop(_k, None)
            st.rerun()
    # Read current child selections (fall back to all scoped options)
    _sel_sectors   = st.session_state.get("alloc_ms_sector",   _all_sectors)
    _sel_ccys_u    = st.session_state.get("alloc_ms_ccy",      _all_ccys_u)
    _sel_companies = st.session_state.get("alloc_ms_asset",    _all_companies)
    _sel_atypes    = st.session_state.get("alloc_ms_atype",    _all_atypes)

    # ── Apply filters — base is market-scoped; child filters applied on top ───
    _filt = _mkt_df.copy()
    if _sel_sectors   and set(_sel_sectors)   != set(_all_sectors):
        _filt = _filt[_filt["Sector"].isin(_sel_sectors)]
    if _sel_ccys_u    and set(_sel_ccys_u)    != set(_all_ccys_u):
        _filt = _filt[_filt["CCY"].isin(_sel_ccys_u)]
    if _sel_companies and set(_sel_companies) != set(_all_companies):
        _filt = _filt[_filt["Company"].isin(_sel_companies)]
    if _sel_atypes    and set(_sel_atypes)    != set(_all_atypes):
        _filt = _filt[_filt["AssetType"].isin(_sel_atypes)]

    if _filt.empty:
        st.info("No holdings match the selected filters. Use the Reset button to clear.", icon="🔍")
        return

    # ── Filtered Allocation Summary ───────────────────────────────────────────
    # Detect "no filters active" FIRST: in the unfiltered view the Market Value
    # KPI represents the WHOLE portfolio, so it must equal the Balance Sheet
    # tab's "Investment Portfolio" headline (holdings_value_base) and share its
    # live day-Δ. A filtered view keeps its own subtotal (a subset, by design).
    _no_filters = (
        not _cur_mkt                                            # market = All
        and set(_sel_sectors)   == set(_all_sectors)
        and set(_sel_ccys_u)    == set(_all_ccys_u)
        and set(_sel_companies) == set(_all_companies)
        and set(_sel_atypes)    == set(_all_atypes)
    )

    _total_mv_all = getattr(val, "holdings_value_base", _filt["_mv"].sum())

    # Unfiltered → use the shared display helper so the Market Value headline and
    # the live day-Δ are derived from the SAME val.per_holding + session cache as
    # the Balance Sheet tab (identical figures to the cent). Filtered → keep the
    # filtered subtotal.
    _fas_shared_day: tuple | None = None
    if _no_filters:
        try:
            from portfolio.display_metrics import (
                compute_effective_portfolio_mv as _fas_eff_calc,
            )
            from market_prices import get_all_from_session as _fas_get_sess
            _fas_eff_total, _fas_stored, _fas_sda, _fas_sdp, _fas_live_cnt = _fas_eff_calc(
                val.per_holding, _fas_get_sess(), _normalize_ticker
            )
            # Effective live-overlay MV: base_mv × (1+pct/100) per holding when
            # session has daily_change_pct, otherwise stored base_market_value.
            # Equals holdings_value_base on cold-start; moves with the session
            # on the first render after 🔄, guaranteeing Allocation == BS headline.
            _fas_mv = _fas_eff_total
            _fas_cb = getattr(val, "total_cost_basis_base", _filt["_cb"].sum())
            if _fas_live_cnt > 0:
                _fas_shared_day = (_fas_sda, _fas_sdp)
        except Exception:
            _fas_mv = _filt["_mv"].sum()
            _fas_cb = _filt["_cb"].sum()
    else:
        _fas_mv = _filt["_mv"].sum()
        _fas_cb = _filt["_cb"].sum()

    _fas_pnl      = _fas_mv - _fas_cb
    _fas_pnl_pct  = (_fas_pnl / _fas_cb * 100) if _fas_cb > 0 else 0.0
    # When no filters are active every holding is included → weight is 100% by
    # definition.  When a filter is active _fas_mv is the stored filtered subtotal
    # and _total_mv_all is the stored full total — both are on the same basis so
    # the ratio is consistent.  Using effective (live-overlay) _fas_mv against
    # the stored _total_mv_all would produce > 100% on up-days, which is wrong.
    _fas_weight   = 100.0 if _no_filters else ((_fas_mv / _total_mv_all * 100) if _total_mv_all > 0 else 0.0)
    _fas_n        = len(_filt)
    _pnl_color    = "normal" if _fas_pnl >= 0 else "inverse"
    _pnl_sign     = "+" if _fas_pnl >= 0 else ""

    # ── Daily change ──────────────────────────────────────────────────────────
    # Strategy:
    #   · No active filters (All) → shared helper (matches Balance Sheet exactly).
    #   · Any filter active      → per-ticker yfinance cache (approximate, ~).
    _fas_day_abs: float | None = None
    _fas_day_pct: float | None = None
    _fas_day_approx = False  # True when using per-ticker estimate

    # ── Helper: weighted day-Δ from session price cache ──────────────────────
    def _day_from_session(df) -> tuple:
        """Return (day_abs, day_pct) from session cache for the given rows df.
        Returns (None, None) when no tickers have daily_change_pct available."""
        from market_prices import get_all_from_session as _gass
        _sess = _gass()
        if not _sess:
            return None, None
        _dsum, _cmv = 0.0, 0.0
        for _, _row in df.iterrows():
            _tk = str(_row.get("Ticker", "")).strip().upper()
            if not _tk:
                continue
            _md = _sess.get(_tk)
            if _md and _md.daily_change_pct is not None:
                _pct = _md.daily_change_pct
                _mv_h = float(_row["_mv"])
                _dsum += _mv_h * _pct / (100.0 + _pct)
                _cmv  += _mv_h
        if _cmv <= 0:
            return None, None
        _d_abs = _dsum
        _prev = _cmv - _dsum
        _d_pct = _dsum / _prev * 100 if _prev > 0 else None
        return _d_abs, _d_pct

    # ── Portfolio daily Δ — Priority 1: session cache (live, after 🔄) ─────────
    if _no_filters and _fas_shared_day is not None:
        # Unfiltered: shared helper → identical to the Balance Sheet day-Δ.
        _fas_day_abs, _fas_day_pct = _fas_shared_day
        _fas_day_approx = False
    else:
        _fas_day_abs, _fas_day_pct = _day_from_session(_filt)
        if _fas_day_abs is not None:
            _fas_day_approx = True  # per-ticker weighted estimate

    # ── Priority 2: snapshot fallback at startup (unfiltered view only) ─────────
    # The BS snapshot 'port' key = total holdings MV.  This equals _fas_mv exactly
    # when _no_filters is True (no account / sector / asset-type / CCY filter active).
    # Applying the snapshot to a FILTERED _fas_mv would compare different populations
    # and produce a phantom delta proportional to the excluded slice — e.g. an equity-
    # only view vs. the total-portfolio snapshot shows a phantom when prices differ.
    # Guard A: any holding has missing_fx (rate defaulted to 1.0) → skip.
    # Guard B: snapshot older than 4 days (covers Saudi Thu→Sun gap) → skip.
    if _fas_day_abs is None and _no_filters:
        try:
            from portfolio.bs_snapshot import load_bs_snapshots as _alloc_load_snaps
            from datetime import date as _alloc_dt, timedelta as _alloc_td
            _alloc_today   = _alloc_dt.today().isoformat()
            _alloc_cutoff  = (_alloc_dt.today() - _alloc_td(days=4)).isoformat()
            _alloc_snaps   = _alloc_load_snaps()
            _alloc_prev = [
                s for s in _alloc_snaps
                if s.get("ccy") == base_ccy
                and _alloc_cutoff <= s.get("date", "") < _alloc_today
            ]
            if _alloc_prev:
                _alloc_snap     = max(_alloc_prev, key=lambda s: s.get("date", ""))
                _alloc_port_pv  = _alloc_snap.get("port")
                _alloc_miss_fx  = any(
                    getattr(r, "missing_fx", False) for r in val.per_holding
                )
                if _alloc_port_pv and not _alloc_miss_fx and _fas_mv > 0:
                    _alloc_pv_f    = float(_alloc_port_pv)
                    _fas_day_abs   = round(_fas_mv - _alloc_pv_f, 2)
                    _fas_day_pct   = (
                        round(_fas_day_abs / _alloc_pv_f * 100.0, 2)
                        if _alloc_pv_f > 0 else None
                    )
                    _fas_day_approx = False  # snapshot-based: same engine as BS tab
        except Exception:
            pass

    # ── Stale-data badge for allocation KPIs (price-only; FX is user-controlled)
    import time as _alloc_t
    _alloc_ep = st.session_state.get("mp_last_refresh_epoch")
    _alloc_price_stale = (not _alloc_ep) or (_alloc_t.time() - _alloc_ep > 3600)
    _ALLOC_MV_BADGE = (
        '<span title="Prices not refreshed in the last hour — showing last saved values. Tap 🔄 to update." '
        'style="font-size:0.7em;cursor:default;margin-left:3px;">⚠️</span>'
        if _alloc_price_stale else ""
    )

    # ── Build day-change sub-line HTML ────────────────────────────────────────
    if _fas_day_pct is not None:
        _dc_color  = "#22c55e" if _fas_day_abs >= 0 else "#ef4444"
        _dc_sign   = "+" if _fas_day_abs >= 0 else ""
        _dc_arrow  = "▲" if _fas_day_abs >= 0 else "▼"
        _dc_approx = "~" if _fas_day_approx else ""
        _day_html = (
            f'<div style="font-size:0.72em;color:{_dc_color};margin-top:2px;">'
            f'{_dc_arrow} {_dc_approx}{_dc_sign}{_fmt_compact(_fas_day_abs)}'
            f'&nbsp;<span style="opacity:0.85">({_dc_approx}{_dc_sign}{_fas_day_pct:.1f}%)</span>'
            f'</div>'
        )
    else:
        _day_html = '<div style="font-size:0.68em;color:#94a3b8;margin-top:2px;">— refresh prices for day Δ</div>'

    # ── KPI grid — pure HTML flex, portrait-safe ─────────────────────────────
    # _kpi_pc is defined locally (NOT _pc which belongs to render_global_header)
    _kpi_pc = "#22c55e" if _fas_pnl >= 0 else "#ef4444"
    _arrow  = "↑"      if _fas_pnl >= 0 else "↓"
    _pct_bg = "#dcfce7" if _fas_pnl >= 0 else "#fee2e2"
    _pct_fg = "#15803d" if _fas_pnl >= 0 else "#b91c1c"
    st.markdown(f"""
<div class="fas-kpi-grid">
  <div class="fas-kpi-card">
    <div class="fas-kpi-lbl">Market Value ({base_ccy})</div>
    <div class="fas-kpi-val">{_fmt_compact(_fas_mv)}{_ALLOC_MV_BADGE}</div>
    {_day_html}
  </div>
  <div class="fas-kpi-card">
    <div class="fas-kpi-lbl">Cost ({base_ccy})</div>
    <div class="fas-kpi-val">{_fmt_compact(_fas_cb)}</div>
  </div>
  <div class="fas-kpi-card">
    <div class="fas-kpi-lbl">P&amp;L ({base_ccy})</div>
    <div class="fas-kpi-val" style="color:{_kpi_pc};">{_pnl_sign}{_fmt_compact(_fas_pnl)}</div>
    <div><span class="fas-kpi-pct" style="background:{_pct_bg};color:{_pct_fg};">{_arrow} {_pnl_sign}{_fas_pnl_pct:.1f}%</span></div>
  </div>
  <div class="fas-kpi-card">
    <div class="fas-kpi-lbl">Weight</div>
    <div class="fas-kpi-val">{_fas_weight:.1f}%</div>
  </div>
  <div class="fas-kpi-card">
    <div class="fas-kpi-lbl">Holdings</div>
    <div class="fas-kpi-val">{_fas_n}</div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Aggregate for pie ─────────────────────────────────────────────────────
    _agg = (
        _filt[[_grp, "_mv"]]
        .groupby(_grp, as_index=False)["_mv"].sum()
        .sort_values("_mv", ascending=False)
        .reset_index(drop=True)
    )
    _total_mv = _agg["_mv"].sum()

    _PAL = ["#0ea5e9","#f43f5e","#22c55e","#f59e0b","#8b5cf6",
            "#ec4899","#14b8a6","#f97316","#6366f1","#84cc16",
            "#06b6d4","#a855f7","#fb923c","#34d399"]
    _colors = [_PAL[i % len(_PAL)] for i in range(len(_agg))]

    # ── Pie / donut ───────────────────────────────────────────────────────────
    _hov = "<b>%{label}</b><br>MV: %{value:,.2f} " + base_ccy + "<br>Share: %{percent:.1f}<extra></extra>"
    _fig = go.Figure(go.Pie(
        labels=_agg[_grp],
        values=_agg["_mv"],
        textinfo="percent",
        textposition="inside",
        insidetextorientation="radial",
        hovertemplate=_hov,
        marker=dict(colors=_colors, line=dict(color="#ffffff", width=1.5)),
        hole=0.38,
    ))
    _fig.update_layout(
        margin=dict(l=8, r=8, t=28, b=8),
        height=360,
        showlegend=True,
        legend=dict(orientation="v", x=1.01, y=0.5, font=dict(size=11)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(
            text=f"<b>{base_ccy}</b>",
            x=0.5, y=0.5, font_size=13, showarrow=False,
        )],
    )

    # Render with click-to-filter; fall back gracefully on older Streamlit
    _ms_key_map = {
        "By Asset":      "alloc_ms_asset",
        "By Asset Type": "alloc_ms_atype",
        "By Sector":     "alloc_ms_sector",
        "By Market":     "alloc_ms_market",
        "By Currency":   "alloc_ms_ccy",
    }
    _ms_all_map = {
        "By Asset":      _all_companies,
        "By Asset Type": _all_atypes,
        "By Sector":     _all_sectors,
        "By Market":     _all_markets,
        "By Currency":   _all_ccys_u,
    }
    try:
        _chart_ev = st.plotly_chart(
            _fig,
            use_container_width=True,
            key="alloc_pie",
            on_select="rerun",
            selection_mode="points",
        )
        if _chart_ev and getattr(_chart_ev, "selection", None):
            _pts = getattr(_chart_ev.selection, "points", [])
            if _pts:
                _clicked = _pts[0].get("label", "")
                if _clicked and _clicked in _ms_all_map[_view]:
                    st.session_state[_ms_key_map[_view]] = [_clicked]
                    st.rerun()
    except TypeError:
        st.plotly_chart(_fig, use_container_width=True)

    # ── Build filtered display table (weights re-calculated within filtered set)
    _disp = _filt[["Ticker","Company","Market","Sector","CCY","_mv"]].copy()
    _filt_total = _disp["_mv"].sum()
    _disp["Weight %"] = (
        (_disp["_mv"] / _filt_total * 100).round(1) if _filt_total > 0 else 0.0
    )
    _disp = _disp.sort_values("Weight %", ascending=False).reset_index(drop=True)
    _mv_col_label = f"MV ({base_ccy})"
    _disp.rename(columns={"_mv": _mv_col_label}, inplace=True)

    # ── Export Allocation Report ───────────────────────────────────────────────
    _ts         = datetime.now().strftime("%Y-%m-%d %H:%M")
    _ts_file    = datetime.now().strftime("%Y%m%d_%H%M")
    _slug       = _view.replace(" ", "_").lower()
    _active_filters: list[str] = []
    if market_scope:                                _active_filters.append(f"Market: {', '.join(market_scope)}")
    if set(_sel_sectors)   != set(_all_sectors):   _active_filters.append(f"Sector: {', '.join(_sel_sectors)}")
    if set(_sel_ccys_u)    != set(_all_ccys_u):    _active_filters.append(f"CCY: {', '.join(_sel_ccys_u)}")
    if set(_sel_companies) != set(_all_companies): _active_filters.append(f"Assets: {len(_sel_companies)} selected")
    if set(_sel_atypes)    != set(_all_atypes):    _active_filters.append(f"Asset Type: {', '.join(_sel_atypes)}")
    _filter_str = "; ".join(_active_filters) if _active_filters else "All holdings"

    _report_bytes = None
    _report_mime  = "application/pdf"
    _report_name  = f"allocation_report_{_ts_file}.pdf"

    try:
        from fpdf import FPDF
        _chart_png = _fig.to_image(format="png", scale=2)

        class _AllocPDF(FPDF):
            pass

        _pdf = _AllocPDF()
        _pdf.set_margins(14, 14, 14)
        _pdf.add_page()

        # Title block
        _pdf.set_font("Helvetica", "B", 17)
        _pdf.cell(0, 9, "Portfolio Allocation Report", ln=True)
        _pdf.set_font("Helvetica", "", 9)
        _pdf.set_text_color(100, 116, 139)
        _pdf.cell(0, 5, f"Base Currency: {base_ccy}   |   View: {_view}   |   Generated: {_ts}", ln=True)
        _pdf.multi_cell(0, 5, f"Filters: {_filter_str}", ln=True)
        _pdf.set_text_color(0, 0, 0)
        _pdf.ln(3)

        # Chart image
        with _tmp.NamedTemporaryFile(suffix=".png", delete=False) as _tf:
            _tf.write(_chart_png)
            _tf_path = _tf.name
        try:
            _pdf.image(_tf_path, w=182)
        finally:
            _os.unlink(_tf_path)
        _pdf.ln(3)

        # Table header
        _pdf.set_font("Helvetica", "B", 10)
        _pdf.cell(0, 6, f"Allocation Detail — {len(_disp)} holding(s)  ·  {base_ccy} {_total_mv:,.2f} total", ln=True)
        _pdf.ln(1)
        _cols_pdf   = ["Ticker","Company","Market","Sector","CCY", _mv_col_label, "Weight %"]
        _widths_pdf = [18, 54, 22, 32, 12, 28, 16]
        _pdf.set_fill_color(15, 23, 42)
        _pdf.set_text_color(255, 255, 255)
        _pdf.set_font("Helvetica", "B", 8)
        for _col, _w in zip(_cols_pdf, _widths_pdf):
            _pdf.cell(_w, 6, _col, border=0, fill=True)
        _pdf.ln()
        _pdf.set_text_color(0, 0, 0)
        _pdf.set_font("Helvetica", "", 8)
        for _i, (_idx, _row) in enumerate(_disp.iterrows()):
            _pdf.set_fill_color(248, 250, 252 if _i % 2 == 0 else 255)
            _vals_pdf = [
                str(_row["Ticker"]),
                str(_row["Company"])[:28],
                str(_row["Market"]),
                str(_row["Sector"])[:16],
                str(_row["CCY"]),
                f"{_row[_mv_col_label]:,.2f}",
                f"{_row['Weight %']:.1f}%",
            ]
            for _v, _w in zip(_vals_pdf, _widths_pdf):
                _pdf.cell(_w, 5, _v, border=0, fill=True)
            _pdf.ln()

        _report_bytes = bytes(_pdf.output())

    except Exception:
        # Fallback: PNG chart export
        try:
            _report_bytes = _fig.to_image(format="png", scale=2)
            _report_mime  = "image/png"
            _report_name  = f"allocation_chart_{_ts_file}.png"
        except Exception:
            _report_bytes = None

    _exp_c1, _exp_c2 = st.columns(2)
    if _report_bytes:
        _btn_lbl = (
            "⬇️ Export Report (PDF)"
            if _report_mime == "application/pdf"
            else "⬇️ Export Chart (PNG)"
        )
        with _exp_c1:
            st.download_button(
                _btn_lbl,
                data=_report_bytes,
                file_name=_report_name,
                mime=_report_mime,
                key="alloc_dl_report",
                use_container_width=True,
            )
    # CSV export of the filtered allocation table
    _alloc_csv_export = _disp.copy()
    with _exp_c2:
        st.download_button(
            "⬇️ Export Table (CSV)",
            data      = _alloc_csv_export.to_csv(index=False),
            file_name = f"allocation_{_ts_file}.csv",
            mime      = "text/csv",
            key       = "alloc_dl_csv",
            use_container_width = True,
            help      = "Download the filtered allocation table as CSV.",
        )

    # ── Filtered asset table ──────────────────────────────────────────────────
    st.caption(
        f"**{_view}** · {len(_disp)} holding(s) · "
        + (f"Filtered — {_filter_str}" if _active_filters else f"{base_ccy} {_total_mv:,.2f} total")
    )
    # ── Table density (persisted preference) ──────────────────────────────────
    from portfolio.table_prefs import (
        DENSITY_OPTIONS as _D_OPTS,
        allocation_col_widths as _a_col_w,
        load_prefs as _load_tp,
        save_prefs as _save_tp,
    )
    if "table_prefs" not in st.session_state:
        st.session_state["table_prefs"] = _load_tp()
    _tp = st.session_state["table_prefs"]
    _a_dens_saved = _tp.get("allocation_density", "Normal")
    _a_dens = st.radio(
        "Column density",
        _D_OPTS,
        index=_D_OPTS.index(_a_dens_saved),
        horizontal=True,
        key="allocation_density_radio",
        label_visibility="collapsed",
    )
    if _a_dens != _a_dens_saved:
        _tp["allocation_density"] = _a_dens
        _save_tp(_tp)
        st.rerun()
    _aw = _a_col_w(_a_dens)
    st.dataframe(
        _disp,
        hide_index=True,
        use_container_width=True,
        column_config={
            _mv_col_label: st.column_config.NumberColumn(_mv_col_label, format="%,.2f"),
            "Weight %":    st.column_config.NumberColumn("Weight %",    format="%.1f%%", width=_aw.get("Weight %")),
            "Ticker":      st.column_config.TextColumn("Ticker",        width=_aw.get("Ticker")),
            "Company":     st.column_config.TextColumn("Company",       width=_aw.get("Company")),
            "CCY":         st.column_config.TextColumn("CCY",           width=_aw.get("CCY")),
        },
    )


def _load_valuation_bundle(base_ccy: str) -> dict:
    """
    Compute portfolio valuation once per Streamlit re-run and return a shared
    bundle consumed by both render_holdings_tab() and render_allocation_tab().

    Avoids duplicate file I/O, FX lookups, and valuation arithmetic, and
    guarantees both tabs see identical data within the same script run.
    No @st.cache_data needed — Streamlit re-runs the full script on every
    interaction, so computing once at the top level per run is the natural
    and safe pattern.
    """
    from portfolio import load_holdings
    from portfolio.accounts import load_accounts as _bvb_accts
    from fx_rates import get_rates_for_holdings
    from portfolio.valuation import calculate_portfolio_valuation

    holdings  = load_holdings()
    accounts  = _bvb_accts()
    all_ccys  = list({getattr(h, "currency", "USD") for h in holdings.values()}) if holdings else []
    fx        = get_rates_for_holdings(all_ccys, base_ccy) if all_ccys else {}
    manual_fx = [c for c, r in fx.items() if r.source == "default" and c != base_ccy]
    val       = calculate_portfolio_valuation(holdings, accounts, base_ccy, fx_rates=fx)
    wt_map    = {r.asset_id: r.invested_weight_pct for r in val.per_holding}
    return {
        "base_ccy":   base_ccy,
        "holdings":   holdings,
        "accounts":   accounts,
        "fx":         fx,
        "manual_fx":  manual_fx,
        "val":        val,
        "wt_map":     wt_map,
    }


def render_holdings_tab(bundle: dict) -> None:
    """Actual Holdings tab — operational view (table, prices, actions)."""
    from portfolio import (
        ASSET_TYPES, CURRENCIES, DEFAULT_SECTORS, MARKETS,
        delete_holding, soft_delete_holding,
        load_holdings, load_portfolio, load_transactions,
        portfolio_weights, record_transaction,
        total_cost_basis, total_market_value,
        update_current_price, upsert_holding,
    )
    import pandas as pd
    from datetime import date

    # Valuation bundle computed once in the main UI; shared with Allocation tab
    _base_ccy     = bundle["base_ccy"]
    holdings      = bundle["holdings"]
    _all_accounts = bundle["accounts"]
    _fx           = bundle["fx"]
    _manual_fx    = bundle["manual_fx"]
    _val          = bundle["val"]
    _wt_map       = bundle["wt_map"]

    watchlist = load_portfolio()

    from fx_rates import refresh_fx_rates

    def _mv_base(h) -> float:
        ccy  = getattr(h, "currency", _base_ccy)
        rate = _fx[ccy].rate if ccy in _fx else 1.0
        return h.market_value * rate

    def _cb_base(h) -> float:
        ccy  = getattr(h, "currency", _base_ccy)
        rate = _fx[ccy].rate if ccy in _fx else 1.0
        return h.cost_basis * rate

    if not holdings:
        st.info(
            "No holdings yet. Click **➕ Add New Position** below, "
            "upload in bulk, or promote a watchlist ticker.",
            icon="💡",
        )

    # ── Holdings table ────────────────────────────────────────────────────────
    if holdings:
        from market_prices import (
            get_all_from_session, market_session_label,
            refresh_all_prices, save_to_session,
        )
        live_cache = get_all_from_session()

        # ── Authoritative MV maps from the valuation engine ───────────────────
        # Using val.per_holding ensures Holdings row values sum to the SAME total
        # as the Allocation "Market Value" KPI and the Balance Sheet
        # "Investment Portfolio" KPI. Never recompute h.market_value × fx_rate
        # independently — that risks FX-rounding drift from the engine total.
        from portfolio.display_metrics import (
            build_effective_mv_map as _hld_bemv,
        )
        # Map reads from val.per_holding (same engine source as Allocation and
        # Balance Sheet), so Holdings row values sum to holdings_value_base
        # exactly — matching both KPI headlines.
        _val_mv_map = _hld_bemv(_val.per_holding, live_cache, _normalize_ticker)

        # ── Build the holdings table ───────────────────────────────────────────
        _mv_col         = f"MV ({_base_ccy})"
        rows            = []
        _asset_id_order: list[str] = []    # parallel to rows; tracks asset_id per row
        manual_tickers:  list[str] = []    # asset_ids of holdings without live ticker

        for asset_id, h in sorted(holdings.items()):
            if h.quantity <= 1e-9:          # hide fully-closed positions
                continue
            has_tk  = getattr(h, "has_ticker", True)
            ccy     = getattr(h, "currency", "USD")
            fx_r    = _fx.get(ccy)
            fx_rate = fx_r.rate if fx_r else 1.0
            # MV from the engine's per_holding (by asset_id) — same data source as
            # Allocation and Balance Sheet, so Holdings rows sum to the headline exactly.
            mv_base = round(_val_mv_map.get(asset_id, h.market_value * fx_rate), 2)
            pnl_pct = h.unrealized_pnl_pct
            status  = "🟢" if pnl_pct > 0.01 else ("🔴" if pnl_pct < -0.01 else "⚪")

            norm_tk = _normalize_ticker(h.ticker)
            md = live_cache.get(norm_tk) or live_cache.get(h.ticker)

            if not has_tk:
                manual_tickers.append(asset_id)

            _src_raw   = getattr(h, "price_source", "manual") or "manual"
            _src_label = {"SAHMK": "SAHMK", "yfinance": "Yahoo",
                          "cached": "Cached", "manual": "Manual"}.get(
                _src_raw, _src_raw.capitalize())

            _acct_id   = getattr(h, "default_account_id", "") or ""
            _acct_obj  = _all_accounts.get(_acct_id)
            _acct_name = _acct_obj.account_name if _acct_obj else ("Unassigned" if not _acct_id else "Unknown")

            _asset_id_order.append(asset_id)
            _day_pct = (
                round(md.daily_change_pct, 2)
                if (md and md.daily_change_pct is not None)
                else None
            )
            rows.append({
                " ":         status,
                "Company":   h.company_name or h.ticker,
                "Ticker":    h.ticker,
                "Qty":       round(h.quantity, 4),
                "Avg Cost":  round(h.avg_cost, 4),
                "Price":     round(h.current_price, 4),
                _mv_col:     mv_base,
                "P&L %":     round(pnl_pct, 2),
                "Day %":     _day_pct,
                "Wt %":      round(_wt_map.get(asset_id, 0.0), 1),
                "CCY":       ccy,
                "Src":       _src_label,
                "Account":   _acct_name,
                "_asset_id": asset_id,       # hidden; used by CSV export & action bar
            })

        # ── Action pills — native horizontal pill bar, wraps on mobile ─────────
        _active_holdings = {aid: h for aid, h in holdings.items() if h.quantity > 1e-9}
        # Deselect pill BEFORE it renders (Streamlit forbids post-render widget state edits)
        if st.session_state.pop("_reset_action_pill", False):
            st.session_state.pop("holdings_action_pill", None)
        _pill_action = st.pills(
            "Actions",
            options=["➕ New Position", "💰 Buy More", "📤 Sell / Close", "📋 Settlement"],
            selection_mode="single",
            key="holdings_action_pill",
            label_visibility="collapsed",
            default=None,
        )
        _add_new_clicked    = _pill_action == "➕ New Position"
        _quick_buy_clicked  = _pill_action == "💰 Buy More"   and bool(_active_holdings)
        _quick_sell_clicked = _pill_action == "📤 Sell / Close" and bool(_active_holdings)
        _settlement_clicked = _pill_action == "📋 Settlement"
        if _pill_action in ("💰 Buy More", "📤 Sell / Close") and not _active_holdings:
            st.toast("No active holdings to trade.", icon="ℹ️")
        # Schedule deselect for next run (cannot touch widget key after instantiation)
        if _pill_action:
            st.session_state["_reset_action_pill"] = True

        # ── View toggle: Table (desktop) vs Cards (mobile-friendly) ──────────
        _hv_mode = st.radio(
            "Holdings view",
            ["📋 Table", "🃏 Cards"],
            horizontal=True,
            key="holdings_view_mode",
            label_visibility="collapsed",
        )
        _tbl_sel = None    # only the Table view exposes row selection

        if _hv_mode == "🃏 Cards":
            for _r in rows:
                with st.container(border=True):
                    _c_pnl   = _r["P&L %"]
                    _pnl_sym = "+" if _c_pnl >= 0 else ""
                    st.markdown(f"**{_r[' ']} {_r['Company']}**  ·  `{_r['Ticker']}`")
                    _cc1, _cc2, _cc3 = st.columns(3)
                    _cc1.metric(_mv_col, f"{_r[_mv_col]:,.2f}")
                    _cc2.metric("P&L %", f"{_pnl_sym}{_c_pnl:.2f}%")
                    _cc3.metric("Wt %", f"{_r['Wt %']:.1f}%")
                    _card_day = _r.get("Day %")
                    _card_day_str = (
                        f"Day {'+' if _card_day >= 0 else ''}{_card_day:.2f}%  ·  "
                        if _card_day is not None else ""
                    )
                    st.caption(
                        f"Qty {_r['Qty']:,.4f} @ {_r['Avg Cost']:,.4f}  ·  "
                        f"Price {_r['Price']:,.4f} {_r['CCY']}  ·  "
                        f"{_card_day_str}"
                        f"Src {_r['Src']}  ·  {_r['Account']}"
                    )
            st.caption(
                "🃏 Card view  ·  🟢 profit  🔴 loss  ⚪ flat  ·  "
                "use the action bar below for Buy / Sell / Settlement."
            )
        else:
            # ── Table density (persisted preference) ──────────────────────────
            from portfolio.table_prefs import (
                DENSITY_OPTIONS as _D_OPTS,
                holdings_col_widths as _h_col_w,
                load_prefs as _load_tp,
                save_prefs as _save_tp,
            )
            if "table_prefs" not in st.session_state:
                st.session_state["table_prefs"] = _load_tp()
            _tp = st.session_state["table_prefs"]
            _h_dens_saved = _tp.get("holdings_density", "Normal")
            _h_dens = st.radio(
                "Column density",
                _D_OPTS,
                index=_D_OPTS.index(_h_dens_saved),
                horizontal=True,
                key="holdings_density_radio",
                label_visibility="collapsed",
            )
            if _h_dens != _h_dens_saved:
                _tp["holdings_density"] = _h_dens
                _save_tp(_tp)
                st.rerun()
            _hw = _h_col_w(_h_dens)
            _tbl_sel = st.dataframe(
                pd.DataFrame(rows),
                hide_index=True,
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    " ":        st.column_config.TextColumn(" ",        width=_hw.get(" ", "small")),
                    "Company":  st.column_config.TextColumn("Company",  width=_hw.get("Company")),
                    "Ticker":   st.column_config.TextColumn("Ticker",   width=_hw.get("Ticker")),
                    "Qty":      st.column_config.NumberColumn("Qty",    format="%,.4f",   width=_hw.get("Qty")),
                    "Avg Cost": st.column_config.NumberColumn("Avg Cost", format="%,.4f"),
                    "Price":    st.column_config.NumberColumn("Price",  format="%,.4f"),
                    _mv_col:    st.column_config.NumberColumn(_mv_col,  format="%,.2f"),
                    "P&L %":    st.column_config.NumberColumn("P&L %",  format="%+.2f%%", width=_hw.get("P&L %")),
                    "Day %":    st.column_config.NumberColumn("Day %",  format="%+.2f%%", width=_hw.get("Day %")),
                    "Wt %":     st.column_config.NumberColumn("Wt %",   format="%.1f%%",  width=_hw.get("Wt %")),
                    "CCY":      st.column_config.TextColumn("CCY",     width=_hw.get("CCY")),
                    "Src":      st.column_config.TextColumn("Src",     width=_hw.get("Src")),
                    "Account":  st.column_config.TextColumn("Account", width=_hw.get("Account")),
                },
            )
            st.caption("👆 Tap a row for quick actions  ·  🟢 profit  🔴 loss  ⚪ flat")

        # ── Per-currency native breakdown (mixed portfolios only) ──────────────
        # Aggregate local_market_value per local_currency from the engine's
        # per_holding rows — these are exact (no FX conversion involved).
        # Only shown when the portfolio spans more than one currency, so a
        # single-currency portfolio sees no extra noise.
        _ph_ccy_totals: dict[str, float] = {}
        for _ph in _val.per_holding:
            _ph_ccy = getattr(_ph, "local_currency", _base_ccy)
            _ph_lmv = float(getattr(_ph, "local_market_value", 0.0) or 0.0)
            _ph_ccy_totals[_ph_ccy] = _ph_ccy_totals.get(_ph_ccy, 0.0) + _ph_lmv
        if len(_ph_ccy_totals) > 1:
            _ccy_lines = "  ·  ".join(
                f"**{_c}** {_v:,.0f}" for _c, _v in sorted(_ph_ccy_totals.items())
            )
            _fx_note = " *(estimated FX)*" if _manual_fx else " *(current FX)*"
            st.caption(
                f"💱 By currency: {_ccy_lines}  ·  "
                f"Total ({_base_ccy}) {_val.holdings_value_base:,.0f}{_fx_note}"
            )

        # ── Secondary tools row ───────────────────────────────────────────────
        _tb2, _tb3 = st.columns(2)
        with _tb2:
            if st.button("⬆️ Bulk Upload", key="open_bulk_upload_btn",
                         use_container_width=True,
                         help="Upload multiple new positions from a CSV file."):
                _dlg_bulk_upload()
        with _tb3:
            # CSV export — strip the hidden asset_id column and the status emoji column
            import io as _csv_io
            _csv_cols = [c for c in (rows[0].keys() if rows else []) if c not in (" ", "_asset_id")]
            _csv_buf  = _csv_io.StringIO()
            import csv as _csv_mod
            _csv_wr   = _csv_mod.DictWriter(_csv_buf, fieldnames=_csv_cols, extrasaction="ignore")
            _csv_wr.writeheader()
            _csv_wr.writerows(rows)
            st.download_button(
                "⬇️ Download CSV",
                data    = _csv_buf.getvalue(),
                file_name = f"holdings_{datetime.now().strftime('%Y%m%d')}.csv",
                mime    = "text/csv",
                key     = "dl_holdings_csv",
                use_container_width = True,
                help    = "Download the current holdings table as a CSV file.",
            )

        # ── Secondary diagnostics ──────────────────────────────────────────────
        if _manual_fx:
            st.caption(
                f"⚠️ Totals in **{_base_ccy}** use estimated FX for "
                f"**{', '.join(_manual_fx)}** — refresh FX in Settings to update."
            )
        elif _val.warnings:
            for _w in _val.warnings:
                st.caption(f"⚠️ {_w}")
        else:
            _s_icon, _s_lbl2 = market_session_label()
            st.caption(
                f"{_s_icon} {_s_lbl2}  ·  "
                f"Invested {_val.invested_allocation_pct:.1f}%  ·  "
                f"Cash {_val.cash_allocation_pct:.1f}%"
            )


        # Manual assets share the same Edit dialog as all other assets.
        # Price updates for untickered holdings are done via the ✏️ Edit button.

    # ── Account helpers (needed by all dialogs, including Add New) ───────────
    from portfolio.accounts import active_accounts as _active_accts_fn, account_display_name as _acct_dn
    from portfolio.accounts import load_accounts as _load_accts_raw, update_account_cash as _upd_cash

    _ELIGIBLE_ACCT_TYPES = frozenset({"Brokerage", "Crypto", "Other"})

    def _acct_pairs_for(currency: str | None = None, eligible_only: bool = False):
        """Return [(account_id, Account)] for active accounts. Never raises.

        eligible_only=True restricts to investment/brokerage-eligible account
        types (Brokerage, Crypto, Other) — excludes Bank and Cash accounts
        which cannot hold investment positions.
        """
        try:
            pairs = list(_active_accts_fn(currency).items())
            if eligible_only:
                pairs = [(aid, a) for aid, a in pairs
                         if a.account_type in _ELIGIBLE_ACCT_TYPES]
            return pairs
        except Exception:
            return []

    # ── Dialog: Open New Position ─────────────────────────────────────────────
    @st.dialog("➕ Open New Position", width="large")
    def _dlg_add_new():
        from ticker_validator import validate_yahoo_ticker, suggest_saudi_ticker
        from portfolio.holdings import normalize_ticker as _ntk

        # ── Mode selector ─────────────────────────────────────────────────────
        _ad_mode = st.radio(
            "Entry mode",
            options=["Record Existing Holding", "Record New Buy Transaction"],
            index=0,
            horizontal=True,
            key="ahn_mode",
            help=(
                "**Record Existing Holding** — enter a position you already own "
                "(legacy import, transfer, gift). No cash is deducted.  \n"
                "**Record New Buy Transaction** — log a fresh purchase from your "
                "account cash. Cash is deducted and a BUY transaction is recorded."
            ),
        )
        _is_buy_mode = (_ad_mode == "Record New Buy Transaction")

        if _is_buy_mode:
            st.caption(
                "A BUY transaction will be recorded and cash deducted from the "
                "selected account."
            )
        else:
            st.caption(
                "The holding is created/updated as-is. No transaction is recorded "
                "and no cash is deducted."
            )

        # ── Pre-render: flush pending ticker (watchlist / Saudi suggestion) ──
        # Must run before ANY widget renders to avoid the "set after render" crash.
        _pending_tk = st.session_state.pop("_ahn_pending_tk", None)
        _do_val = False
        if _pending_tk:
            st.session_state["ahn_ticker_input"] = _pending_tk
            _do_val = True  # auto-trigger validation this rerun

        # Default quantity = 1 on first open (before the widget renders)
        if "ahn_qty" not in st.session_state:
            st.session_state["ahn_qty"] = 1.0

        # ── Market inference helper ───────────────────────────────────────────
        def _guess_market(vr) -> str:
            exch = (getattr(vr, "exchange", "") or "").upper()
            ccy  = (getattr(vr, "currency",  "") or "").upper()
            _US = {"NMS","NGS","NGM","NCM","NYSE","AMEX","PCX","NYQ",
                   "BATS","NASDAQGS","NASDAQGM","NASDAQCM","CBT","CME","NYB","NYM","CBOE"}
            if exch in _US or ccy == "USD":
                return "US"
            if exch in {"SAU","TAD"} or ccy == "SAR":
                return "Saudi"
            if exch in {"LSE","IOB"} or ccy == "GBP":
                return "UK"
            if ccy in {"EUR","CHF","DKK","SEK","NOK"}:
                return "Europe"
            if ccy in {"JPY","HKD","SGD","CNY","KRW","AUD","NZD"}:
                return "Asia"
            return "Other"

        # ── Ticker input ──────────────────────────────────────────────────────
        _has_tk = st.checkbox("Has a market ticker (Yahoo Finance)", value=True, key="ahn_has_tk")
        if _has_tk:
            _tc1, _tc2 = st.columns([3, 1])
            with _tc1:
                _tk_raw = st.text_input(
                    "Ticker symbol",
                    key="ahn_ticker_input",
                    placeholder="AAPL · 2222.SR · GLD · GC=F",
                )
            with _tc2:
                st.write("")
                if st.button(
                    "🔍 Validate & Fill", key="ahn_val_btn",
                    use_container_width=True,
                    help="Fetch from Yahoo Finance and auto-fill all form fields.",
                ):
                    _do_val = True

            # Saudi shorthand suggestion
            # Uses pending-key so we never set ahn_ticker_input after it rendered.
            _sa_sug = suggest_saudi_ticker(_tk_raw or "")
            if _sa_sug:
                _sas1, _sas2 = st.columns([3, 1])
                with _sas1:
                    st.caption(f"💡 Did you mean **{_sa_sug}**?")
                with _sas2:
                    if st.button(f"Use {_sa_sug}", key="ahn_sa_btn", use_container_width=True):
                        st.session_state["_ahn_pending_tk"] = _sa_sug
                        st.rerun()

            # Watchlist quick-fill — auto-validates on selection, no extra button.
            # on_change fires before the next render, so we store in a pending key
            # and pick it up at the top of the dialog on the following rerun.
            _wl_opts = sorted(watchlist.keys())
            if _wl_opts:
                def _on_wl_change():
                    _sel = st.session_state.get("ahn_wl_pick", "")
                    if _sel:
                        st.session_state["_ahn_pending_tk"] = _sel

                st.selectbox(
                    "Or pick from Watchlist",
                    options=[""] + _wl_opts,
                    format_func=lambda x: "— select a ticker —" if x == "" else x,
                    key="ahn_wl_pick",
                    on_change=_on_wl_change,
                )

            # ── Validation — runs BEFORE form fields so session state is ready ──
            if _do_val:
                _to_check = st.session_state.get("ahn_ticker_input", "").strip().upper()
                if _to_check:
                    with st.spinner(f"Validating **{_to_check}**…"):
                        _vr = validate_yahoo_ticker(_to_check)
                    st.session_state["ahn_validation"] = _vr

                    if _vr.exists:
                        # Write directly into widget session-state keys so the
                        # form fields below pick up the values on THIS render.
                        st.session_state["ahn_tk_confirm"] = _vr.resolved_ticker or _to_check
                        if _vr.company_name:
                            st.session_state["ahn_name"] = _vr.company_name
                        if _vr.current_price and _vr.current_price > 0:
                            _live_p = float(_vr.current_price)
                            st.session_state["ahn_price"] = _live_p
                            # Default opening price = latest market price (spec §6)
                            st.session_state["ahn_cost"]  = _live_p
                        if _vr.currency and _vr.currency in CURRENCIES:
                            st.session_state["ahn_ccy"] = _vr.currency
                            # Reset account selection when currency changes
                            st.session_state.pop("ahn_acct_id", None)
                        if _vr.asset_type and _vr.asset_type in ASSET_TYPES:
                            st.session_state["ahn_type"] = _vr.asset_type
                        _mkt = _guess_market(_vr)
                        if _mkt in MARKETS:
                            st.session_state["ahn_market"] = _mkt
                        # Sector — populated from yfinance info dict (spec §5)
                        _vr_sector = getattr(_vr, "sector", "")
                        if _vr_sector and _vr_sector in DEFAULT_SECTORS:
                            st.session_state["ahn_sector"] = _vr_sector
                        # Quantity default = 1 on fresh validation
                        if "ahn_qty" not in st.session_state:
                            st.session_state["ahn_qty"] = 1.0

            # ── Compact validation badge (shown once fields are populated) ────
            _val = st.session_state.get("ahn_validation")
            if _val:
                if _val.exists:
                    st.success(
                        f"✅ **{_val.resolved_ticker}** — {_val.company_name or '—'}  "
                        f"| {_val.currency}  {_val.current_price:,.4f}"
                        f"  | {_val.exchange}  | {_val.asset_type}"
                    )
                else:
                    st.warning(
                        f"⚠️ **{_val.resolved_ticker}** not found on Yahoo Finance — "
                        "fill details manually; price will be tracked as Manual."
                    )
        else:
            st.info("No ticker — price will be tracked manually.", icon="ℹ️")

        _yahoo_ok = bool(
            _has_tk
            and st.session_state.get("ahn_validation")
            and st.session_state["ahn_validation"].exists
        )

        st.divider()

        # ── Core fields — driven entirely by session state keys ───────────────
        _fc1, _fc2 = st.columns(2)
        with _fc1:
            _ad_tk     = st.text_input("Ticker symbol", key="ahn_tk_confirm",
                                       help="Auto-filled after Validate. Edit if needed.")
            _ad_name   = st.text_input("Asset name", key="ahn_name")
            _ad_type   = st.selectbox("Asset type",  ASSET_TYPES,     key="ahn_type")
            _ad_market = st.selectbox("Market",       MARKETS,         key="ahn_market")
            _ad_sector = st.selectbox("Sector",       DEFAULT_SECTORS, key="ahn_sector")
        with _fc2:
            _ad_ccy  = st.selectbox("Currency", CURRENCIES, key="ahn_ccy")
            _ad_qty  = st.number_input("Opening quantity",
                                       min_value=0.0001, step=1.0, format="%.4f", key="ahn_qty")
            _ad_cost = st.number_input("Opening price per unit",
                                       min_value=0.0, step=0.01, format="%.4f", key="ahn_cost",
                                       help="Price you paid — defaults to latest market price after Validate.")
            _ad_price = st.number_input("Current market price",
                                        min_value=0.0, step=0.01, format="%.4f", key="ahn_price",
                                        help="Live price from Yahoo Finance — auto-filled after Validate.")

        # ── Account (filtered by currency, eligible types only) ──────────────
        # Apply an account created inline on the previous rerun. Must run
        # before the selectbox renders to avoid the "set after render" crash.
        _pending_acct = st.session_state.pop("_ahn_pending_acct", None)
        if _pending_acct:
            st.session_state["ahn_acct_id"] = _pending_acct

        _pairs_ccy = _acct_pairs_for(currency=_ad_ccy, eligible_only=True)
        _pairs_all = _acct_pairs_for(eligible_only=True)
        _use_pairs = _pairs_ccy if _pairs_ccy else _pairs_all
        _acct_opts = {"": "— no account —"}
        for _aid_k, _a_v in _use_pairs:
            _acct_opts[_aid_k] = _acct_dn(_a_v)
        if not _pairs_ccy and _pairs_all:
            st.caption(f"ℹ️ No {_ad_ccy} accounts — showing all currencies.")
        _ad_aid = st.selectbox(
            f"Link to account ({_ad_ccy})",
            options=list(_acct_opts.keys()),
            format_func=lambda k: _acct_opts[k],
            key="ahn_acct_id",
        )

        # ── Inline account creation — no dead-end when none exist ────────────
        with st.expander("➕ Create a new account", expanded=not _pairs_all):
            _na1, _na2 = st.columns(2)
            with _na1:
                _na_name = st.text_input(
                    "Account name", key="ahn_new_acct_name",
                    placeholder="e.g. Al Rajhi Brokerage",
                )
                _na_type = st.selectbox(
                    "Account type", ["Brokerage", "Crypto", "Other"],
                    key="ahn_new_acct_type",
                )
            with _na2:
                _na_inst = st.text_input(
                    "Institution (optional)", key="ahn_new_acct_inst",
                )
                _na_cash = st.number_input(
                    "Opening cash", min_value=0.0, value=0.0, step=100.0,
                    format="%.2f", key="ahn_new_acct_cash",
                    help=f"Initial {_ad_ccy} cash balance for this account.",
                )
            st.caption(f"New account currency: **{_ad_ccy}** (matches this position).")
            if st.button(
                "Create account", key="ahn_new_acct_btn",
                use_container_width=True,
                disabled=not _na_name.strip(),
            ):
                try:
                    from portfolio.accounts import upsert_account as _ins_acct
                    from portfolio.cash_ledger import append_cash_entry as _ins_cash
                    _new_a = _ins_acct(
                        account_name=_na_name.strip(),
                        institution=_na_inst.strip(),
                        account_type=_na_type,
                        base_currency=_ad_ccy,
                        opening_cash=float(_na_cash),
                    )
                    # Mirror the Accounts-tab flow: opening cash MUST create an
                    # INITIAL_BALANCE ledger entry so the cash ledger stays the
                    # single source of truth (performance/XIRR reads contributions
                    # from the ledger — a bare opening_cash would overstate growth).
                    if float(_na_cash) > 0:
                        _ins_cash(
                            account_id=_new_a.account_id,
                            transaction_type="INITIAL_BALANCE",
                            currency=_ad_ccy, amount=float(_na_cash),
                            notes="Opening balance",
                        )
                    for _k in ("ahn_new_acct_name", "ahn_new_acct_inst",
                               "ahn_new_acct_cash", "ahn_new_acct_type"):
                        st.session_state.pop(_k, None)
                    # Pre-select the new account on the next rerun
                    st.session_state["_ahn_pending_acct"] = _new_a.account_id
                    st.toast(f"Account created: {_na_name.strip()}", icon="✅")
                    st.rerun()
                except Exception as _ex:
                    st.error(f"Could not create account — {_ex}")

        if not _ad_aid:
            if not _pairs_all:
                st.warning(
                    "No eligible investment account yet — use **➕ Create a new "
                    "account** above to add one.",
                    icon="⚠️",
                )
            else:
                st.warning("Select an account to continue.", icon="⚠️")

        # ── Fees / Date / Notes / Correction ─────────────────────────────────
        _tf1, _tf2 = st.columns(2)
        with _tf1:
            _ad_fees = st.number_input("Transaction fees", min_value=0.0, value=0.0,
                                       step=0.01, format="%.2f", key="ahn_fees")
        with _tf2:
            _ad_date = st.date_input("Opening date", value=date.today(), key="ahn_date")
        _ad_notes = st.text_input("Notes (optional)", max_chars=200, key="ahn_notes",
                                  placeholder="e.g. bought via Tadawul, rights issue…")
        _ad_exsym = st.text_input(
            "Exchange symbol (optional)",
            max_chars=20, key="ahn_exsym",
            placeholder="e.g. 2222 · 1120 · 7010",
            help=(
                "Local exchange symbol used by regional market data providers (SAHMK).  "
                "Leave blank for US/global holdings — the main ticker is used instead.  "
                "Example: Saudi Aramco → 2222, Al Rajhi Bank → 1120"
            ),
        )

        # ── Duplicate guard (soft warning — duplicate tickers are allowed) ────
        _ad_tk_clean = _ad_tk.strip().replace(" ", "_").upper()
        _ad_tk_norm  = _ntk(_ad_tk_clean) if _ad_tk_clean else ""
        _open_norms  = {_ntk(h.ticker) for h in holdings.values() if h.quantity > 1e-9}
        _is_dup      = bool(_ad_tk_clean and _ad_tk_norm in _open_norms)

        if _is_dup:
            st.warning(
                f"A holding with ticker **{_ad_tk_clean}** already exists.  "
                "You are opening a **separate** asset with the same price ticker — "
                "this is allowed (e.g. Gold Bank Account vs. Physical Gold). "
                "Use the existing row's **Buy More** action to add to an existing position.",
                icon="⚠️",
            )

        # ── Real-time cost / cash calculation ─────────────────────────────────
        _ad_total_cost = float(_ad_qty) * float(_ad_cost) + float(_ad_fees)
        _cash_ok       = True   # always OK for Mode A; checked below for Mode B
        _acct_bal      = None

        if _ad_aid:
            try:
                _ck_accts  = _load_accts_raw()
                _acct_bal  = _ck_accts[_ad_aid].cash_balance if _ad_aid in _ck_accts else None
            except Exception:
                pass

        # Show cost row; add cash columns only for Mode B (buy transaction)
        if _is_buy_mode and _acct_bal is not None:
            _remaining  = _acct_bal - _ad_total_cost
            _cash_ok    = _remaining >= 0
            _rc1, _rc2, _rc3 = st.columns(3)
            _rc1.metric("Opening Cost",  f"{_ad_total_cost:,.2f} {_ad_ccy}")
            _rc2.metric("Account Cash",  f"{_acct_bal:,.2f} {_ad_ccy}")
            _rc3.metric(
                "Remaining Cash",
                f"{_remaining:,.2f} {_ad_ccy}",
                delta=f"{_remaining:+,.2f}",
                delta_color="normal" if _cash_ok else "inverse",
            )
            if not _cash_ok:
                st.error("Insufficient cash balance.", icon="🚫")
        else:
            st.caption(f"Opening cost: **{_ad_total_cost:,.2f} {_ad_ccy}**")

        # ── Submit ────────────────────────────────────────────────────────────
        _xb1, _xb2 = st.columns(2)
        with _xb1:
            _btn_label = "✅ Record Buy Transaction" if _is_buy_mode else "✅ Record Holding"
            # Cash check blocks only Mode B; duplicate tickers now allowed
            _submit_disabled = (
                not _ad_tk_clean
                or not _ad_aid
                or (_is_buy_mode and not _cash_ok)
            )
            if st.button(
                _btn_label, type="primary", use_container_width=True,
                disabled=_submit_disabled,
                key="ahn_submit",
            ):
                try:
                    _sec_linked = bool(
                        _yahoo_ok and _ad_market == "US"
                        and _ad_type in ("Stock", "ETF")
                    )
                    _err = None

                    if _is_buy_mode:
                        # ── Mode B: BUY transaction + cash debit ──────────────
                        _t, _h2, _err = record_transaction(
                            ticker=_ad_tk_clean, side="BUY",
                            quantity=float(_ad_qty),
                            price=float(_ad_cost),
                            txn_date=str(_ad_date) if _ad_date else None,
                            notes=_ad_notes,
                            company_name=_ad_name.strip() or _ad_tk_clean,
                            market=_ad_market, sector=_ad_sector,
                            asset_type=_ad_type, currency=_ad_ccy,
                            has_ticker=_has_tk,
                            account_id=_ad_aid, fees=float(_ad_fees),
                        )
                        if not _err:
                            # Persist extra metadata — target by asset_id to avoid ambiguity
                            upsert_holding(
                                asset_id=_h2.asset_id,
                                sec_linked=_sec_linked,
                                price_source="yfinance" if _yahoo_ok else "manual",
                                price_date=date.today().isoformat(),
                                exchange_symbol=_ad_exsym.strip() or None,
                            )
                            # Debit cash
                            if _ad_aid:
                                try:
                                    _upd_cash(_ad_aid, -_ad_total_cost)
                                except Exception:
                                    pass
                    else:
                        # ── Mode A: Record existing holding — no transaction,
                        #           no cash debit ─────────────────────────────
                        _h2 = upsert_holding(
                            ticker=_ad_tk_clean,
                            company_name=_ad_name.strip() or _ad_tk_clean,
                            market=_ad_market,
                            sector=_ad_sector,
                            quantity=float(_ad_qty),
                            avg_cost=float(_ad_cost),
                            current_price=float(_ad_price) if _ad_price > 0 else float(_ad_cost),
                            asset_type=_ad_type,
                            currency=_ad_ccy,
                            has_ticker=_has_tk,
                            purchase_date=str(_ad_date) if _ad_date else None,
                            notes=_ad_notes,
                            sec_linked=_sec_linked,
                            price_source="yfinance" if _yahoo_ok else "manual",
                            price_date=date.today().isoformat(),
                            exchange_symbol=_ad_exsym.strip() or None,
                            default_account_id=_ad_aid,
                        )

                    if _err:
                        st.error(_err)
                    else:
                        # Apply live price if it differs from the cost basis
                        if _ad_price > 0 and abs(_ad_price - float(_ad_cost)) > 1e-9:
                            update_current_price(
                                _h2.asset_id, _ad_price,
                                source="yfinance" if _yahoo_ok else "manual",
                            )
                        # Clear dialog state
                        _keys_to_clear = [
                            "ahn_validation", "ahn_ticker_input", "ahn_tk_confirm",
                            "ahn_name", "ahn_cost", "ahn_price", "ahn_qty",
                            "ahn_ccy", "ahn_type", "ahn_market", "ahn_sector",
                            "ahn_acct_id", "ahn_has_tk", "ahn_exsym", "ahn_mode",
                        ]
                        for _k in _keys_to_clear:
                            st.session_state.pop(_k, None)
                        _mode_label = "Buy recorded" if _is_buy_mode else "Holding recorded"
                        st.toast(
                            f"{_mode_label}: **{_ad_tk_clean}** · "
                            f"{_ad_qty:,.4f} shares @ {_ad_cost:,.4f} {_ad_ccy}",
                            icon="✅",
                        )
                        st.rerun()
                except Exception as _ex:
                    st.error(f"Failed to save — {_ex}")
        with _xb2:
            if st.button("Cancel", key="ahn_cancel", use_container_width=True):
                for _k in ("ahn_validation", "ahn_ticker_input"):
                    st.session_state.pop(_k, None)
                st.rerun()

    # ── Dialogs + action bar ─────────────────────────────────────────────────
    if holdings:

        # ── Dialog: Buy More ─────────────────────────────────────────────────
        @st.dialog("➕ Buy More")
        def _dlg_buy(dlg_ticker: str, dlg_h):
            _d_ccy   = getattr(dlg_h, "currency", "USD")
            _d_pairs = _acct_pairs_for()
            _d_labels = ["— no account —"] + [_acct_dn(a) for _, a in _d_pairs]
            _d_ids    = [""] + [aid for aid, _ in _d_pairs]
            st.caption(
                f"**{dlg_h.ticker}** · {dlg_h.company_name}  "
                f"| {dlg_h.quantity:,.4f} shares @ avg {dlg_h.avg_cost:,.4f} {_d_ccy}"
            )
            if not _d_pairs:
                st.info("No active accounts — transaction recorded without account link.")
            _d_qty   = st.number_input("Qty to buy", min_value=0.0001, step=1.0, format="%.4f", value=1.0)
            _d_price = st.number_input(
                "Price / share",
                value=float(dlg_h.current_price or dlg_h.avg_cost or 0.0),
                min_value=0.0, step=0.01, format="%.4f",
            )
            _d_acct  = st.selectbox(
                "Account", options=range(len(_d_labels)),
                format_func=lambda i: _d_labels[i],
            )
            _d_fees  = st.number_input("Fees", min_value=0.0, value=0.0, step=0.01, format="%.2f")
            _d_date  = st.date_input("Trade date", value=None)
            _d_notes = st.text_input("Notes", max_chars=200)
            _d_corr  = st.checkbox(
                "Record correction only — skip cash debit",
                help="Use this to adjust the holding without moving any account cash.",
            )
            _d_aid = _d_ids[_d_acct]
            _d_total_cost = float(_d_qty) * float(_d_price) + float(_d_fees)
            # Cash check (actual buy only)
            if not _d_corr and _d_aid:
                try:
                    _ck_accts = _load_accts_raw()
                    _ck_bal   = _ck_accts[_d_aid].cash_balance if _d_aid in _ck_accts else None
                    if _ck_bal is not None:
                        _ck_icon = "🟢" if _ck_bal >= _d_total_cost else "🔴"
                        st.caption(
                            f"{_ck_icon} Account cash: **{_ck_bal:,.2f} {_d_ccy}**  "
                            f"· Cost: **{_d_total_cost:,.2f} {_d_ccy}**"
                        )
                        if _ck_bal < _d_total_cost:
                            st.warning(
                                f"Insufficient cash — available {_ck_bal:,.2f}, "
                                f"needed {_d_total_cost:,.2f} {_d_ccy}. "
                                "Tick 'Record correction only' to bypass.",
                                icon="⚠️",
                            )
                except Exception:
                    pass
            # New avg cost preview
            if (dlg_h.quantity + _d_qty) > 0:
                _new_avg = ((dlg_h.avg_cost * dlg_h.quantity) + (_d_price * _d_qty)) / (dlg_h.quantity + _d_qty)
                st.caption(f"Est. new avg cost: **{_new_avg:,.4f} {_d_ccy}**")
            _db1, _db2 = st.columns(2)
            with _db1:
                # Block actual buy if cash is insufficient
                _cash_ok = True
                if not _d_corr and _d_aid:
                    try:
                        _ck_accts2 = _load_accts_raw()
                        _ck_bal2   = _ck_accts2[_d_aid].cash_balance if _d_aid in _ck_accts2 else None
                        if _ck_bal2 is not None and _ck_bal2 < _d_total_cost:
                            _cash_ok = False
                    except Exception:
                        pass
                if st.button("✅ Confirm Buy", type="primary", use_container_width=True,
                             disabled=not _cash_ok):
                    try:
                        _t, _h2, _e = record_transaction(
                            ticker=dlg_h.ticker, asset_id=dlg_ticker, side="BUY",
                            quantity=float(_d_qty), price=float(_d_price),
                            txn_date=_d_date.isoformat() if _d_date else None,
                            notes=_d_notes,
                            company_name=dlg_h.company_name, market=dlg_h.market,
                            sector=dlg_h.sector,
                            asset_type=getattr(dlg_h, "asset_type", "Stock"),
                            currency=_d_ccy,
                            has_ticker=getattr(dlg_h, "has_ticker", True),
                            account_id=_d_aid, fees=float(_d_fees),
                        )
                        if _e:
                            st.error(_e)
                        else:
                            if not _d_corr and _d_aid:
                                try:
                                    _upd_cash(_d_aid, -_d_total_cost)
                                except Exception:
                                    pass
                            st.toast(
                                f"Bought {_d_qty:,.4f} × {dlg_h.ticker} @ {_d_price:,.4f}  "
                                f"· New avg cost: {_h2.avg_cost:,.4f}",
                                icon="✅",
                            )
                            st.rerun()
                    except Exception as _ex:
                        st.error(f"Buy failed — {_ex}")
            with _db2:
                if st.button("Cancel", use_container_width=True):
                    st.rerun()

        # ── Dialog: Sell / Close ─────────────────────────────────────────────
        @st.dialog("📤 Sell / Close Position")
        def _dlg_sell(dlg_ticker: str, dlg_h):
            from datetime import date as _sell_dt
            _d_ccy   = getattr(dlg_h, "currency", "USD")
            _d_avail = float(dlg_h.quantity)
            _d_pairs = _acct_pairs_for()
            _d_labels = ["— no account —"] + [_acct_dn(a) for _, a in _d_pairs]
            _d_ids    = [""] + [aid for aid, _ in _d_pairs]
            # Pre-select the account the holding was bought from
            _linked_aid = getattr(dlg_h, "default_account_id", "") or ""
            _d_default_idx = _d_ids.index(_linked_aid) if _linked_aid in _d_ids else 0
            st.caption(
                f"**{dlg_h.ticker}** · {dlg_h.company_name}  "
                f"| **{_d_avail:,.4f}** shares available @ avg cost {dlg_h.avg_cost:,.4f} {_d_ccy}"
            )
            # Unique key per dialog open — forces fresh value= every time
            _sk = f"{dlg_ticker}_{st.session_state.get('_sell_oid', 0)}"
            _d_full = st.checkbox("Close full position", value=True,
                                  key=f"sell_full_{_sk}")
            if _d_full:
                _d_qty = _d_avail
                st.info(f"Will sell all {_d_avail:,.4f} shares.")
            else:
                _d_qty = st.number_input(
                    "Qty to sell",
                    min_value=0.0001, max_value=_d_avail + 0.0001,
                    value=min(1.0, _d_avail), step=1.0, format="%.4f",
                    key=f"sell_qty_{_sk}",
                )
            _d_price = st.number_input(
                "Sale price / share",
                value=float(dlg_h.current_price or dlg_h.avg_cost or 0.0),
                min_value=0.0, step=0.01, format="%.4f",
                key=f"sell_price_{_sk}",
            )
            _d_acct  = st.selectbox(
                "Account", options=range(len(_d_labels)),
                format_func=lambda i: _d_labels[i],
                index=_d_default_idx,
                key=f"sell_acct_{_sk}",
            )
            _d_fees  = st.number_input("Fees", min_value=0.0, value=0.0,
                                       step=0.01, format="%.2f",
                                       key=f"sell_fees_{_sk}")
            _d_date  = st.date_input("Trade date", value=_sell_dt.today(),
                                     key=f"sell_date_{_sk}")
            _d_notes = st.text_input("Notes", max_chars=200,
                                     key=f"sell_notes_{_sk}")
            _d_corr  = st.checkbox(
                "Record correction only — skip cash credit",
                help="Use this to reduce the holding without crediting any account cash.",
                key=f"sell_corr_{_sk}",
            )
            # P&L preview
            _sell_qty_preview = _d_avail if _d_full else float(_d_qty)
            _d_pnl = (_d_price - dlg_h.avg_cost) * _sell_qty_preview if dlg_h.avg_cost else 0.0
            _d_pct = (_d_pnl / (dlg_h.avg_cost * _sell_qty_preview) * 100.0) if dlg_h.avg_cost and _sell_qty_preview else 0.0
            _d_sign = "🟢" if _d_pnl >= 0 else "🔴"
            _d_proceeds = _sell_qty_preview * float(_d_price) - float(_d_fees)
            st.info(
                f"{_d_sign} Est. realized P&L: **{_d_pnl:+,.2f} {_d_ccy}** ({_d_pct:+.2f}%)  "
                f"· Net proceeds: **{_d_proceeds:,.2f} {_d_ccy}**"
            )
            _sb1, _sb2 = st.columns(2)
            with _sb1:
                if st.button("✅ Confirm Sell", type="primary", use_container_width=True):
                    try:
                        _final_qty = _d_avail if _d_full else float(_d_qty)
                        _d_aid = _d_ids[_d_acct]
                        _t, _h2, _e = record_transaction(
                            ticker=dlg_h.ticker, asset_id=dlg_ticker, side="SELL",
                            quantity=_final_qty, price=float(_d_price),
                            txn_date=_d_date.isoformat() if _d_date else None,
                            notes=_d_notes,
                            account_id=_d_aid, fees=float(_d_fees),
                        )
                        if _e:
                            st.error(_e)
                        else:
                            if not _d_corr and _d_aid:
                                try:
                                    _proceeds = _final_qty * float(_d_price) - float(_d_fees)
                                    _upd_cash(_d_aid, _proceeds)
                                except Exception:
                                    pass
                            _rpnl = (_d_price - dlg_h.avg_cost) * _final_qty
                            _fully = _h2.quantity <= 1e-9
                            st.toast(
                                f"{'Closed' if _fully else 'Sold'} {_final_qty:,.4f} × {dlg_h.ticker} "
                                f"@ {_d_price:,.4f}  · P&L: {_rpnl:+,.2f} {_d_ccy}",
                                icon="✅",
                            )
                            st.rerun()
                    except Exception as _ex:
                        st.error(f"Sell failed — {_ex}")
            with _sb2:
                if st.button("Cancel", use_container_width=True):
                    st.rerun()

        # ── Open Add New dialog — called directly; Streamlit keeps it open
        #    across widget-interaction reruns automatically. X-close is handled
        #    by Streamlit natively; no persistent flag needed.
        if _add_new_clicked:
            _dlg_add_new()

        # ── Dialog: Quick Buy (top-bar, with holding picker) ─────────────────
        @st.dialog("➕ Quick Buy", width="large")
        def _dlg_quick_buy():
            _qb_active = {aid: h for aid, h in holdings.items() if h.quantity > 1e-9}
            _qb_labels = {aid: f"{h.ticker} — {h.company_name} ({h.quantity:,.4f} shares)"
                          for aid, h in _qb_active.items()}
            _qb_sel = st.selectbox(
                "Select holding to buy more",
                options=list(_qb_labels.keys()),
                format_func=lambda k: _qb_labels[k],
                key="qb_holding_pick",
            )
            if _qb_sel:
                _qb_h = _qb_active[_qb_sel]
                _qb_ccy = getattr(_qb_h, "currency", "USD")
                st.divider()
                st.caption(
                    f"**{_qb_h.ticker}** · {_qb_h.company_name}  "
                    f"| {_qb_h.quantity:,.4f} shares @ avg {_qb_h.avg_cost:,.4f} {_qb_ccy}"
                )
                _qb_c1, _qb_c2 = st.columns(2)
                with _qb_c1:
                    _qb_qty = st.number_input("Qty to buy", min_value=0.0001, step=1.0,
                                              format="%.4f", value=1.0, key="qb_qty")
                    _qb_price = st.number_input(
                        "Price / share",
                        value=float(_qb_h.current_price or _qb_h.avg_cost or 0.0),
                        min_value=0.0, step=0.01, format="%.4f", key="qb_price",
                    )
                with _qb_c2:
                    _qb_d_pairs = _acct_pairs_for()
                    _qb_d_labels = ["— no account —"] + [_acct_dn(a) for _, a in _qb_d_pairs]
                    _qb_d_ids = [""] + [aid for aid, _ in _qb_d_pairs]
                    _qb_acct = st.selectbox("Account", options=range(len(_qb_d_labels)),
                                            format_func=lambda i: _qb_d_labels[i], key="qb_acct")
                    _qb_fees = st.number_input("Fees", min_value=0.0, value=0.0,
                                               step=0.01, format="%.2f", key="qb_fees")
                _qb_date = st.date_input("Trade date", value=None, key="qb_date")
                _qb_notes = st.text_input("Notes", max_chars=200, key="qb_notes")
                _qb_corr = st.checkbox("Record correction only — skip cash debit", key="qb_corr")

                _qb_aid = _qb_d_ids[_qb_acct]
                _qb_total = float(_qb_qty) * float(_qb_price) + float(_qb_fees)

                # Cash check
                _qb_cash_ok = True
                if not _qb_corr and _qb_aid:
                    try:
                        _ck_a = _load_accts_raw()
                        _ck_b = _ck_a[_qb_aid].cash_balance if _qb_aid in _ck_a else None
                        if _ck_b is not None:
                            _ck_i = "🟢" if _ck_b >= _qb_total else "🔴"
                            st.caption(f"{_ck_i} Account cash: **{_ck_b:,.2f} {_qb_ccy}** · Cost: **{_qb_total:,.2f} {_qb_ccy}**")
                            if _ck_b < _qb_total:
                                st.warning(f"Insufficient cash — available {_ck_b:,.2f}, needed {_qb_total:,.2f}.", icon="⚠️")
                                _qb_cash_ok = False
                    except Exception:
                        pass

                # New avg cost preview
                if (_qb_h.quantity + _qb_qty) > 0:
                    _qb_new_avg = ((_qb_h.avg_cost * _qb_h.quantity) + (_qb_price * _qb_qty)) / (_qb_h.quantity + _qb_qty)
                    st.caption(f"Est. new avg cost: **{_qb_new_avg:,.4f} {_qb_ccy}**")

                _qbb1, _qbb2 = st.columns(2)
                with _qbb1:
                    if st.button("✅ Confirm Buy", type="primary", use_container_width=True,
                                 disabled=not _qb_cash_ok, key="qb_submit"):
                        try:
                            _t, _h2, _e = record_transaction(
                                ticker=_qb_h.ticker, asset_id=_qb_sel, side="BUY",
                                quantity=float(_qb_qty), price=float(_qb_price),
                                txn_date=_qb_date.isoformat() if _qb_date else None,
                                notes=_qb_notes, company_name=_qb_h.company_name,
                                market=_qb_h.market, sector=_qb_h.sector,
                                asset_type=getattr(_qb_h, "asset_type", "Stock"),
                                currency=_qb_ccy,
                                has_ticker=getattr(_qb_h, "has_ticker", True),
                                account_id=_qb_aid, fees=float(_qb_fees),
                            )
                            if _e:
                                st.error(_e)
                            else:
                                if not _qb_corr and _qb_aid:
                                    try:
                                        _upd_cash(_qb_aid, -_qb_total)
                                    except Exception:
                                        pass
                                st.toast(f"Bought {_qb_qty:,.4f} × {_qb_h.ticker} @ {_qb_price:,.4f}", icon="✅")
                                st.rerun()
                        except Exception as _ex:
                            st.error(f"Buy failed — {_ex}")
                with _qbb2:
                    if st.button("Cancel", use_container_width=True, key="qb_cancel"):
                        st.rerun()

        if _quick_buy_clicked:
            _dlg_quick_buy()

        # ── Dialog: Quick Sell (top-bar, with holding picker) ────────────────
        @st.dialog("📤 Quick Sell", width="large")
        def _dlg_quick_sell():
            _qs_active = {aid: h for aid, h in holdings.items() if h.quantity > 1e-9}
            _qs_labels = {aid: f"{h.ticker} — {h.company_name} ({h.quantity:,.4f} shares)"
                          for aid, h in _qs_active.items()}
            _qs_sel = st.selectbox(
                "Select holding to sell",
                options=list(_qs_labels.keys()),
                format_func=lambda k: _qs_labels[k],
                key="qs_holding_pick",
            )
            if _qs_sel:
                from datetime import date as _qs_dt
                _qs_h = _qs_active[_qs_sel]
                _qs_ccy = getattr(_qs_h, "currency", "USD")
                _qs_avail = float(_qs_h.quantity)

                # When the selected holding changes, push correct defaults into
                # the per-holding session_state keys so widgets pick them up
                if st.session_state.get("_qs_last_sel") != _qs_sel:
                    st.session_state["_qs_last_sel"] = _qs_sel
                    _qs_p0 = _acct_pairs_for()
                    _qs_i0 = [""] + [aid for aid, _ in _qs_p0]
                    _qs_la = getattr(_qs_h, "default_account_id", "") or ""
                    st.session_state[f"qs_price_{_qs_sel}"] = float(
                        _qs_h.current_price or _qs_h.avg_cost or 0.0)
                    st.session_state[f"qs_acct_{_qs_sel}"] = (
                        _qs_i0.index(_qs_la) if _qs_la in _qs_i0 else 0)
                    st.session_state[f"qs_date_{_qs_sel}"]  = _qs_dt.today()
                    st.session_state[f"qs_full_{_qs_sel}"]  = True
                    st.session_state[f"qs_fees_{_qs_sel}"]  = 0.0
                    st.session_state[f"qs_notes_{_qs_sel}"] = ""

                st.divider()
                st.caption(
                    f"**{_qs_h.ticker}** · {_qs_h.company_name}  "
                    f"| **{_qs_avail:,.4f}** shares @ avg cost {_qs_h.avg_cost:,.4f} {_qs_ccy}"
                )
                _qs_full = st.checkbox("Close full position", value=True,
                                       key=f"qs_full_{_qs_sel}")
                _qs_qty = _qs_avail if _qs_full else st.number_input(
                    "Qty to sell", min_value=0.0001, max_value=_qs_avail,
                    step=1.0, format="%.4f", key=f"qs_qty_{_qs_sel}",
                )
                _qs_price = st.number_input(
                    "Sell price / share",
                    value=float(_qs_h.current_price or _qs_h.avg_cost or 0.0),
                    min_value=0.0, step=0.01, format="%.4f",
                    key=f"qs_price_{_qs_sel}",
                )
                _qs_d_pairs = _acct_pairs_for()
                _qs_d_labels = ["— no account —"] + [_acct_dn(a) for _, a in _qs_d_pairs]
                _qs_d_ids = [""] + [aid for aid, _ in _qs_d_pairs]
                _qs_acct = st.selectbox("Account", options=range(len(_qs_d_labels)),
                                        format_func=lambda i: _qs_d_labels[i],
                                        key=f"qs_acct_{_qs_sel}")
                _qs_fees = st.number_input("Fees", min_value=0.0, value=0.0,
                                           step=0.01, format="%.2f",
                                           key=f"qs_fees_{_qs_sel}")
                _qs_date = st.date_input("Trade date", value=_qs_dt.today(),
                                         key=f"qs_date_{_qs_sel}")
                _qs_notes = st.text_input("Notes", max_chars=200,
                                          key=f"qs_notes_{_qs_sel}")

                # P&L preview
                _qs_gross = float(_qs_qty) * float(_qs_price)
                _qs_cost = float(_qs_qty) * float(_qs_h.avg_cost)
                _qs_rpnl = _qs_gross - _qs_cost - float(_qs_fees)
                _qs_pnl_icon = "🟢" if _qs_rpnl >= 0 else "🔴"
                st.caption(
                    f"{_qs_pnl_icon} Est. realized P&L: **{_qs_rpnl:+,.2f} {_qs_ccy}** "
                    f"| Proceeds: {_qs_gross:,.2f} · Cost basis: {_qs_cost:,.2f}"
                )

                _qs_aid = _qs_d_ids[_qs_acct]
                _qsb1, _qsb2 = st.columns(2)
                with _qsb1:
                    if st.button("📤 Confirm Sell", type="primary", use_container_width=True, key="qs_submit"):
                        try:
                            _t, _h2, _e = record_transaction(
                                ticker=_qs_h.ticker, asset_id=_qs_sel, side="SELL",
                                quantity=float(_qs_qty), price=float(_qs_price),
                                txn_date=_qs_date.isoformat() if _qs_date else None,
                                notes=_qs_notes, company_name=_qs_h.company_name,
                                market=_qs_h.market, sector=_qs_h.sector,
                                asset_type=getattr(_qs_h, "asset_type", "Stock"),
                                currency=_qs_ccy,
                                has_ticker=getattr(_qs_h, "has_ticker", True),
                                account_id=_qs_aid, fees=float(_qs_fees),
                            )
                            if _e:
                                st.error(_e)
                            else:
                                if _qs_aid:
                                    try:
                                        _qs_net = _qs_gross - float(_qs_fees)
                                        _upd_cash(_qs_aid, _qs_net)
                                    except Exception:
                                        pass
                                st.toast(
                                    f"Sold {_qs_qty:,.4f} × {_qs_h.ticker} "
                                    f"@ {_qs_price:,.4f} · P&L: {_qs_rpnl:+,.2f} {_qs_ccy}",
                                    icon="✅",
                                )
                                st.rerun()
                        except Exception as _ex:
                            st.error(f"Sell failed — {_ex}")
                with _qsb2:
                    if st.button("Cancel", use_container_width=True, key="qs_cancel"):
                        st.rerun()

        if _quick_sell_clicked:
            _dlg_quick_sell()

        # ── Dialog: Settlement ────────────────────────────────────────────────
        @st.dialog("📋 Record Settlement", width="large")
        def _dlg_settlement(preselected_asset_id=None, preselected_holding=None):
            from portfolio import (
                SETTLEMENT_CATEGORIES, CURRENCIES,
                record_settlement, load_holdings as _s_load_h,
            )
            from portfolio.accounts import load_accounts as _s_load_a, account_display_name as _s_adn

            _s_holdings = _s_load_h()
            _s_accounts = _s_load_a()

            # ── Scope selector (hidden when called from per-row button) ────────
            if preselected_asset_id is not None:
                _s_scope = "Specific Holding"
                _s_asset_id = preselected_asset_id
                _s_holding  = preselected_holding
            else:
                _s_scope = st.radio(
                    "Settlement scope",
                    ["Specific Holding", "Portfolio Level"],
                    horizontal=True,
                    key="settle_scope",
                )
                _s_asset_id = None
                _s_holding  = None

            # ── Holding picker ─────────────────────────────────────────────────
            if _s_scope == "Specific Holding" and preselected_asset_id is None:
                _s_active = {
                    aid: h for aid, h in _s_holdings.items() if h.quantity > 1e-9
                }
                if not _s_active:
                    st.warning(
                        "No active holdings. Use **Portfolio Level** scope instead.",
                        icon="⚠️",
                    )
                    return
                _s_opts = {
                    f"{h.ticker} — {h.company_name} ({h.quantity:,.4f} sh)": aid
                    for aid, h in sorted(_s_active.items(), key=lambda x: x[1].ticker)
                }
                _s_lbl = st.selectbox(
                    "Holding", list(_s_opts.keys()), key="settle_holding_pick"
                )
                _s_asset_id = _s_opts[_s_lbl]
                _s_holding  = _s_active[_s_asset_id]

            if _s_holding is not None:
                _si1, _si2, _si3 = st.columns(3)
                _si1.caption(f"**Asset ID:** {_s_holding.asset_id}")
                _si2.caption(f"**Type:** {getattr(_s_holding, 'asset_type', 'Stock')}")
                _si3.caption(f"**Currency:** {getattr(_s_holding, 'currency', 'USD')}")

            # ── Category (first) ──────────────────────────────────────────────
            _s_cat = st.selectbox(
                "Category", SETTLEMENT_CATEGORIES,
                index=SETTLEMENT_CATEGORIES.index("Dividend"),
                key="settle_cat",
            )

            # ── Income / Expense direction — auto-locked by category ───────────
            _INCOME_CATS  = {"Dividend"}
            _EXPENSE_CATS = {"Fee", "Tax", "Zakat", "Islamic Purification"}
            if _s_cat in _INCOME_CATS:
                _s_direction = "Income"
                st.info("✅ **Income / Credit** — auto-set for this category", icon="ℹ️")
            elif _s_cat in _EXPENSE_CATS:
                _s_direction = "Expense"
                st.info("💸 **Expense / Debit** — auto-set for this category", icon="ℹ️")
            else:
                _s_direction = st.radio(
                    "Direction", ["Income", "Expense"],
                    horizontal=True,
                    key="settle_direction",
                )

            # ── Date / Amount / Currency ───────────────────────────────────────
            _sd1, _sd2, _sd3 = st.columns(3)
            with _sd1:
                _s_date = st.date_input("Date", value=date.today(), key="settle_date")
            with _sd2:
                _s_amount = st.number_input(
                    "Amount", value=0.0, min_value=0.0, step=0.01, format="%.2f",
                    key="settle_amount",
                    help="Enter the absolute amount — direction is determined by the category above.",
                )
            with _sd3:
                _s_def_ccy = (
                    getattr(_s_holding, "currency", "SAR") if _s_holding else "SAR"
                )
                _s_ccy_idx = CURRENCIES.index(_s_def_ccy) if _s_def_ccy in CURRENCIES else 0
                _s_ccy = st.selectbox(
                    "Currency", CURRENCIES, index=_s_ccy_idx, key="settle_ccy"
                )

            # Final signed amount (negative for expenses)
            _s_signed_amount = _s_amount if _s_direction == "Income" else -_s_amount

            # ── Account ───────────────────────────────────────────────────────
            _s_acct_sorted = sorted(
                _s_accounts.values(), key=lambda a: a.account_name
            )
            _s_acct_labels = ["— no account —"] + [
                _s_adn(a) + (
                    f"  ⚠️ currency mismatch ({a.base_currency} ≠ {_s_ccy})"
                    if a.base_currency != _s_ccy else ""
                )
                for a in _s_acct_sorted
            ]
            _s_acct_ids = [None] + [a.account_id for a in _s_acct_sorted]
            _s_acct_sel_lbl = st.selectbox(
                "Account", _s_acct_labels, key="settle_acct"
            )
            _s_acct_idx = _s_acct_labels.index(_s_acct_sel_lbl)
            _s_acct_id  = _s_acct_ids[_s_acct_idx] or ""
            if _s_acct_id:
                _s_acct_obj = _s_accounts.get(_s_acct_id)
                if _s_acct_obj:
                    st.caption(
                        f"Current balance: **{_s_acct_obj.cash_balance:,.2f}"
                        f" {_s_acct_obj.base_currency}**"
                    )

            # ── Notes ─────────────────────────────────────────────────────────
            _s_notes = st.text_area(
                "Notes (min. 10 characters)", key="settle_notes", max_chars=500
            )
            st.caption(f"{len(_s_notes.strip())} / 10 minimum characters")

            # ── Impact Preview ─────────────────────────────────────────────────
            st.divider()
            st.markdown("**🔍 Impact Preview**")
            _ip1, _ip2 = st.columns(2)
            with _ip1:
                st.markdown("**This settlement WILL:**")
                _sgn = "+" if _s_signed_amount >= 0 else ""
                st.markdown(
                    f"- Record **{_sgn}{_s_signed_amount:,.2f} {_s_ccy}** as **{_s_cat}**"
                )
                if _s_acct_id:
                    _dir = "Credit" if _s_signed_amount >= 0 else "Debit"
                    _acct_disp = _s_acct_labels[_s_acct_idx].split("  ⚠️")[0]
                    st.markdown(f"- {_dir} account **{_acct_disp}**")
                if _s_asset_id:
                    _linked = _s_holdings.get(_s_asset_id)
                    if _linked:
                        st.markdown(
                            f"- Count toward **{_linked.ticker}** holding return"
                        )
                else:
                    st.markdown("- Count toward portfolio-level return")
            with _ip2:
                st.markdown("**This settlement will NOT:**")
                st.markdown("- ~~Change cost basis or average cost~~")
                st.markdown("- ~~Change FIFO realized P&L~~")
                st.markdown("- ~~Change share quantity~~")

            # ── Buttons ───────────────────────────────────────────────────────
            st.divider()
            _sb1, _sb2 = st.columns(2)
            with _sb1:
                if st.button(
                    "✅ Save Settlement", type="primary",
                    use_container_width=True, key="settle_save"
                ):
                    _s_txn, _s_err = record_settlement(
                        amount=_s_signed_amount,
                        category=_s_cat,
                        currency=_s_ccy,
                        settlement_date=_s_date.isoformat(),
                        notes=_s_notes,
                        asset_id=_s_asset_id or "",
                        account_id=_s_acct_id,
                    )
                    if _s_err:
                        st.error(_s_err)
                    else:
                        _sgn2 = "+" if _s_signed_amount >= 0 else ""
                        st.toast(
                            f"Settlement recorded: {_s_cat} "
                            f"{_sgn2}{_s_signed_amount:,.2f} {_s_ccy}",
                            icon="✅",
                        )
                        st.rerun()
            with _sb2:
                if st.button(
                    "Cancel", use_container_width=True, key="settle_cancel"
                ):
                    st.rerun()

        if _settlement_clicked:
            _dlg_settlement()

        # ── Dialog: Edit ─────────────────────────────────────────────────────
        @st.dialog("✏️ Edit Holding")
        def _dlg_edit(dlg_ticker: str, dlg_h):
            from portfolio.accounts import load_accounts as _ed_load_accts, account_display_name as _ed_acct_dn
            st.caption(
                f"**{dlg_h.ticker}** — direct field correction.  "
                "Transaction history is not affected."
            )

            # ── Numeric / text fields ─────────────────────────────────────────
            _e_name  = st.text_input("Company name", value=dlg_h.company_name or "")
            _en1, _en2, _en3 = st.columns(3)
            with _en1:
                _e_qty   = st.number_input(
                    "Quantity (correction)", value=float(dlg_h.quantity),
                    min_value=0.0, step=1.0, format="%.4f",
                )
            with _en2:
                _e_avg   = st.number_input(
                    "Avg cost (correction)", value=float(dlg_h.avg_cost),
                    min_value=0.0, step=0.01, format="%.4f",
                )
            with _en3:
                _e_price = st.number_input(
                    "Current price", value=float(dlg_h.current_price),
                    min_value=0.0, step=0.01, format="%.4f",
                )

            # ── Classification fields ─────────────────────────────────────────
            _ec1, _ec2 = st.columns(2)
            with _ec1:
                _mkt_val = getattr(dlg_h, "market", "US") or "US"
                _e_market = st.selectbox(
                    "Market",
                    options=MARKETS,
                    index=MARKETS.index(_mkt_val) if _mkt_val in MARKETS else 0,
                    key=f"dlg_edit_market_{dlg_ticker}",
                )
                _at_val = getattr(dlg_h, "asset_type", "Stock") or "Stock"
                _e_type = st.selectbox(
                    "Asset type",
                    options=ASSET_TYPES,
                    index=ASSET_TYPES.index(_at_val) if _at_val in ASSET_TYPES else ASSET_TYPES.index("Other"),
                    key=f"dlg_edit_type_{dlg_ticker}",
                )
            with _ec2:
                _sec_val = getattr(dlg_h, "sector", "Other") or "Other"
                _e_sector = st.selectbox(
                    "Sector",
                    options=DEFAULT_SECTORS,
                    index=DEFAULT_SECTORS.index(_sec_val) if _sec_val in DEFAULT_SECTORS else 0,
                    key=f"dlg_edit_sector_{dlg_ticker}",
                )
                _ccy_val = getattr(dlg_h, "currency", "USD") or "USD"
                _e_ccy = st.selectbox(
                    "Currency",
                    options=CURRENCIES,
                    index=CURRENCIES.index(_ccy_val) if _ccy_val in CURRENCIES else 0,
                    key=f"dlg_edit_ccy_{dlg_ticker}",
                )

            # ── Notes / Exchange symbol ───────────────────────────────────────
            _e_notes  = st.text_input("Notes", value=dlg_h.notes or "", max_chars=200)
            _e_exsym  = st.text_input(
                "Exchange symbol",
                value=getattr(dlg_h, "exchange_symbol", "") or "",
                max_chars=20,
                placeholder="e.g. 2222 · 1120 · 7010",
                help=(
                    "Local exchange symbol for regional data providers (SAHMK).  "
                    "Leave blank for US/global holdings.  "
                    "Example: Saudi Aramco → 2222, Al Rajhi Bank → 1120"
                ),
            )

            # ── Account selector ──────────────────────────────────────────────
            _ed_accts   = {aid: a for aid, a in _ed_load_accts().items() if a.active}
            _cur_aid    = getattr(dlg_h, "default_account_id", "") or ""
            _ed_opts    = [""] + list(_ed_accts.keys())
            _ed_labels  = {
                "": "— Select account —",
                **{aid: _ed_acct_dn(a) for aid, a in _ed_accts.items()},
            }
            _ed_default = _cur_aid if _cur_aid in _ed_accts else ""
            _e_aid      = st.selectbox(
                "Account *",
                options=_ed_opts,
                format_func=lambda k: _ed_labels[k],
                index=_ed_opts.index(_ed_default),
                key=f"dlg_edit_acct_{dlg_ticker}",
                help="Every holding must be linked to an account.",
            )
            if not _e_aid:
                st.warning("Account is required for every holding.", icon="⚠️")

            _eb1, _eb2 = st.columns(2)
            with _eb1:
                if st.button(
                    "💾 Save Changes", type="primary",
                    use_container_width=True,
                    disabled=not _e_aid,
                ):
                    try:
                        upsert_holding(
                            asset_id=dlg_ticker,
                            company_name=_e_name or None,
                            quantity=float(_e_qty),
                            avg_cost=float(_e_avg),
                            current_price=float(_e_price),
                            market=_e_market,
                            sector=_e_sector,
                            asset_type=_e_type,
                            currency=_e_ccy,
                            notes=_e_notes or None,
                            exchange_symbol=_e_exsym.strip() or None,
                            default_account_id=_e_aid,
                        )
                        st.toast(f"{dlg_h.ticker} updated", icon="💾")
                        st.rerun()
                    except Exception as _ex:
                        st.error(f"Edit failed — {_ex}")
            with _eb2:
                if st.button("Cancel", use_container_width=True):
                    st.rerun()

        # ── Dialog: Delete ───────────────────────────────────────────────────
        @st.dialog("🗑️ Delete Holding")
        def _dlg_delete(dlg_ticker: str, dlg_h):
            st.warning(
                f"Remove **{dlg_h.ticker}** ({dlg_h.company_name}) from your holdings?  "
                "Transaction history is preserved. This only removes the active position.",
                icon="⚠️",
            )
            _conf_check = st.checkbox("I understand — this cannot be undone")
            _conf_text  = st.text_input(f"Type `{dlg_h.ticker}` to confirm")
            _ready = _conf_check and _conf_text.strip().upper() == dlg_h.ticker.upper()
            _xb1, _xb2 = st.columns(2)
            with _xb1:
                if st.button(
                    "🗑️ Delete", type="primary",
                    use_container_width=True, disabled=not _ready,
                ):
                    try:
                        soft_delete_holding(dlg_ticker)
                        st.toast(f"{dlg_h.ticker} removed from holdings", icon="🗑️")
                        st.rerun()
                    except Exception as _ex:
                        st.error(f"Delete failed — {_ex}")
            with _xb2:
                if st.button("Cancel", use_container_width=True):
                    st.rerun()

        # ── Dialog: Bulk Upload New Holdings ─────────────────────────────────
        @st.dialog("⬆️ Bulk Upload New Holdings", width="large")
        def _dlg_bulk_upload():
            import csv, io as _bio
            from datetime import datetime as _dt
            from portfolio.holdings import normalize_ticker as _ntk_bu

            REQUIRED_COLS = [
                "ticker", "company_name", "asset_type", "market", "sector",
                "currency", "account_name", "opening_quantity", "opening_price",
                "current_market_price", "fees", "opening_date", "notes",
            ]
            ALLOWED_ASSET_TYPES = set(ASSET_TYPES)
            ALLOWED_CURRENCIES = set(CURRENCIES)
            DATE_FMT = "%Y/%m/%d"

            TEMPLATE_ROW = (
                "MSFT,Microsoft Corporation,Stock,US,Technology,"
                "USD,US Brokerage,1,426.99,426.99,0,2026/05/29,Initial position"
            )

            st.caption(
                "Upload new positions in bulk. Each row creates an opening BUY transaction. "
                "Existing open holdings are never modified by bulk upload."
            )

            # Template download
            _tmpl = ",".join(REQUIRED_COLS) + "\n" + TEMPLATE_ROW
            _tcol, _hcol = st.columns([1, 3])
            with _tcol:
                st.download_button(
                    "⬇️ Download Template",
                    data=_tmpl,
                    file_name="holdings_upload_template.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="bulk_dl_template",
                )
            with _hcol:
                with st.expander("ℹ️ Format guide"):
                    st.markdown(
                        f"**Required columns (exact names):**  \n"
                        f"`{', '.join(REQUIRED_COLS)}`\n\n"
                        f"**Date format:** `YYYY/MM/DD`  \n"
                        f"**Asset types:** {', '.join(sorted(ALLOWED_ASSET_TYPES))}  \n"
                        f"**Currencies:** {', '.join(sorted(ALLOWED_CURRENCIES))}  \n"
                        f"**notes:** optional — can be blank\n\n"
                        f"**Example row:**  \n`{TEMPLATE_ROW}`"
                    )

            st.divider()
            _uploaded = st.file_uploader(
                "Select CSV file", type=["csv"], key="bulk_upload_file"
            )
            if not _uploaded:
                return

            # ── Parse ─────────────────────────────────────────────────────────
            try:
                _content = _uploaded.read().decode("utf-8-sig")
                _reader  = csv.DictReader(_bio.StringIO(_content))
                _bu_rows = list(_reader)
                _file_cols = list(_reader.fieldnames or [])
            except Exception as _pe:
                st.error(
                    f"Bulk upload rejected. No records were imported.\n\n"
                    f"Could not parse CSV: {_pe}"
                )
                return

            # ── Column check ──────────────────────────────────────────────────
            _missing_cols = [c for c in REQUIRED_COLS if c not in _file_cols]
            if _missing_cols:
                st.error(
                    "Bulk upload rejected. No records were imported.\n\n"
                    f"**Missing columns:** {', '.join(_missing_cols)}  \n"
                    f"**Expected:** `{', '.join(REQUIRED_COLS)}`"
                )
                return
            if not _bu_rows:
                st.warning("The uploaded file contains no data rows.")
                return

            # ── Load context for validation ───────────────────────────────────
            _ex_holdings = load_holdings()
            _open_norms  = {_ntk_bu(h.ticker) for h in _ex_holdings.values() if h.quantity > 1e-9}
            _accts_raw   = _load_accts_raw()
            _acct_by_name = {
                a.account_name: (aid, a)
                for aid, a in _accts_raw.items() if a.active
            }

            # ── Row validation ────────────────────────────────────────────────
            _errors:    list[tuple[int, list[str]]] = []
            _validated: list[dict] = []
            _seen_norms: set[str]  = set()

            for _ri, _row in enumerate(_bu_rows, start=2):
                _re: list[str] = []

                # ticker
                _raw_tk = str(_row.get("ticker", "")).strip()
                _norm_tk = ""
                if not _raw_tk:
                    _re.append("ticker is required")
                else:
                    _norm_tk = _ntk_bu(_raw_tk.upper())
                    if _norm_tk in _open_norms:
                        # Soft warning only — duplicate tickers now allowed
                        # (e.g. two GC=F holdings: Gold Bank Account + Physical Gold)
                        pass
                    if _norm_tk in _seen_norms:
                        _re.append(
                            f"ticker '{_raw_tk}' appears more than once in this file"
                        )
                    _seen_norms.add(_norm_tk)

                # company_name
                if not str(_row.get("company_name", "")).strip():
                    _re.append("company_name is required")

                # asset_type
                _at = str(_row.get("asset_type", "")).strip()
                if _at not in ALLOWED_ASSET_TYPES:
                    _re.append(
                        f"asset_type '{_at}' is not valid. "
                        f"Allowed: {', '.join(sorted(ALLOWED_ASSET_TYPES))}"
                    )

                # market
                if not str(_row.get("market", "")).strip():
                    _re.append("market is required")

                # sector
                if not str(_row.get("sector", "")).strip():
                    _re.append("sector is required (use 'Unknown' if not applicable)")

                # currency
                _ccy = str(_row.get("currency", "")).strip()
                if _ccy not in ALLOWED_CURRENCIES:
                    _re.append(
                        f"currency '{_ccy}' is not valid. "
                        f"Allowed: {', '.join(sorted(ALLOWED_CURRENCIES))}"
                    )

                # account_name + currency match
                _acct_name = str(_row.get("account_name", "")).strip()
                _acct_aid  = ""
                if not _acct_name:
                    _re.append("account_name is required")
                elif _acct_name not in _acct_by_name:
                    _re.append(
                        f"account '{_acct_name}' does not match any active account"
                    )
                else:
                    _acct_aid, _acct_obj = _acct_by_name[_acct_name]
                    if _acct_obj.base_currency != _ccy:
                        _re.append(
                            f"currency '{_ccy}' does not match account "
                            f"'{_acct_name}' currency '{_acct_obj.base_currency}'"
                        )

                # opening_quantity
                _qty = None
                try:
                    _qty = float(_row.get("opening_quantity", ""))
                    if _qty <= 0:
                        _re.append("opening_quantity must be > 0")
                except (ValueError, TypeError):
                    _re.append("opening_quantity must be a number")

                # opening_price
                _op = None
                try:
                    _op = float(_row.get("opening_price", ""))
                    if _op < 0:
                        _re.append("opening_price must be >= 0")
                except (ValueError, TypeError):
                    _re.append("opening_price must be a number")

                # current_market_price
                _cmp = None
                try:
                    _cmp = float(_row.get("current_market_price", ""))
                    if _cmp < 0:
                        _re.append("current_market_price must be >= 0")
                except (ValueError, TypeError):
                    _re.append("current_market_price must be a number")

                # fees
                _fees = 0.0
                try:
                    _fees = float(_row.get("fees", "0") or "0")
                    if _fees < 0:
                        _re.append("fees must be >= 0")
                except (ValueError, TypeError):
                    _re.append("fees must be a number")

                # opening_date
                _date_str = str(_row.get("opening_date", "")).strip()
                _parsed_dt = None
                try:
                    _parsed_dt = _dt.strptime(_date_str, DATE_FMT).date()
                except ValueError:
                    _re.append(
                        f"opening_date '{_date_str}' must be in YYYY/MM/DD format "
                        "(e.g. 2026/05/29)"
                    )

                if _re:
                    _errors.append((_ri, _re))
                elif _qty is not None and _op is not None and _cmp is not None:
                    _total_cost = _qty * _op + _fees
                    _validated.append({
                        "ticker":         _norm_tk,
                        "company_name":   str(_row["company_name"]).strip(),
                        "asset_type":     _at,
                        "market":         str(_row["market"]).strip(),
                        "sector":         str(_row["sector"]).strip(),
                        "currency":       _ccy,
                        "account_name":   _acct_name,
                        "account_id":     _acct_aid,
                        "opening_quantity": _qty,
                        "opening_price":  _op,
                        "current_market_price": _cmp,
                        "fees":           _fees,
                        "opening_date":   _parsed_dt.isoformat() if _parsed_dt else None,
                        "notes":          str(_row.get("notes", "")).strip(),
                        "total_cost":     _total_cost,
                    })

            if _errors:
                st.error("Bulk upload rejected. No records were imported.")
                for _row_num, _row_errs in _errors:
                    for _err in _row_errs:
                        st.markdown(f"- **Row {_row_num}:** {_err}")
                return

            # ── Cash validation ───────────────────────────────────────────────
            _acct_costs: dict[str, float] = {}
            for _v in _validated:
                _aid_k = _v["account_id"]
                _acct_costs[_aid_k] = _acct_costs.get(_aid_k, 0.0) + _v["total_cost"]

            _cash_errors: list[str] = []
            for _aid_k, _needed in _acct_costs.items():
                _a = _accts_raw.get(_aid_k)
                if _a and _a.cash_balance < _needed:
                    _cash_errors.append(
                        f"Insufficient cash in account **{_a.account_name}**. "
                        f"Required: {_needed:,.2f} {_a.base_currency}, "
                        f"Available: {_a.cash_balance:,.2f} {_a.base_currency}."
                    )

            if _cash_errors:
                st.error("Bulk upload rejected. No records were imported.")
                for _ce in _cash_errors:
                    st.markdown(f"- {_ce}")
                return

            # ── Preview ───────────────────────────────────────────────────────
            st.success(f"✅ {len(_validated)} rows validated — ready to import.")
            _prev_df = pd.DataFrame([{
                "Ticker":   _v["ticker"],
                "Company":  _v["company_name"],
                "Qty":      _v["opening_quantity"],
                "Price":    _v["opening_price"],
                "Fees":     _v["fees"],
                "Cost":     _v["total_cost"],
                "Account":  _v["account_name"],
                "CCY":      _v["currency"],
                "Date":     _v["opening_date"],
            } for _v in _validated])
            st.dataframe(_prev_df, hide_index=True, use_container_width=True)

            # ── Confirm import ────────────────────────────────────────────────
            _cb1, _cb2 = st.columns(2)
            with _cb1:
                if st.button("✅ Import All", type="primary",
                             use_container_width=True, key="bulk_confirm_btn"):
                    # Re-read cash for optimistic check
                    _accts_fresh = _load_accts_raw()
                    _abort = []
                    for _aid_k, _needed in _acct_costs.items():
                        _a2 = _accts_fresh.get(_aid_k)
                        if _a2 and _a2.cash_balance < _needed:
                            _abort.append(
                                f"Cash changed for '{_a2.account_name}' — aborting."
                            )
                    if _abort:
                        st.error("\n".join(_abort))
                        return

                    _imported = 0
                    _imp_errors: list[str] = []
                    for _v in _validated:
                        try:
                            _t2, _h2, _err2 = record_transaction(
                                ticker=_v["ticker"], side="BUY",
                                quantity=_v["opening_quantity"],
                                price=_v["opening_price"],
                                txn_date=_v["opening_date"],
                                notes=_v["notes"],
                                company_name=_v["company_name"],
                                market=_v["market"],
                                sector=_v["sector"],
                                asset_type=_v["asset_type"],
                                currency=_v["currency"],
                                has_ticker=True,
                                account_id=_v["account_id"],
                                fees=_v["fees"],
                            )
                            if _err2:
                                _imp_errors.append(f"{_v['ticker']}: {_err2}")
                            else:
                                if _v["current_market_price"] > 0:
                                    update_current_price(
                                        _h2.asset_id,
                                        _v["current_market_price"],
                                        source="upload",
                                    )
                                _upd_cash(_v["account_id"], -_v["total_cost"])
                                _imported += 1
                        except Exception as _ex2:
                            _imp_errors.append(f"{_v['ticker']}: {_ex2}")

                    if _imp_errors:
                        st.error(
                            f"Partially imported {_imported}/{len(_validated)}:\n"
                            + "\n".join(_imp_errors)
                        )
                    else:
                        st.toast(
                            f"Imported {_imported} holding(s) successfully.",
                            icon="✅",
                        )
                        st.rerun()
            with _cb2:
                if st.button("Cancel", use_container_width=True, key="bulk_cancel_btn"):
                    st.rerun()

        # ── Action bar — shown when a table row is selected ───────────────────
        _sel_rows = getattr(getattr(_tbl_sel, "selection", None), "rows", [])
        if _sel_rows:
            _si = _sel_rows[0]
            _st = _asset_id_order[_si] if _si < len(_asset_id_order) else None
            _sh = holdings.get(_st) if _st else None
            if _st and _sh:
                with st.container(border=True):
                    _abar_info, _ab1, _ab2, _ab3, _ab4, _ab5 = st.columns([3, 1, 1, 1, 1, 1])
                    with _abar_info:
                        _ab_ccy = getattr(_sh, "currency", "USD")
                        st.markdown(
                            f"**{_sh.ticker}** · {_sh.company_name}  "
                            f"| {_sh.quantity:,.4f} shares · "
                            f"{_sh.unrealized_pnl_pct:+.1f}%"
                        )
                    with _ab1:
                        if st.button("➕ Buy", key="tbl_buy_btn",
                                     use_container_width=True, type="primary"):
                            _dlg_buy(_st, _sh)
                    with _ab2:
                        if st.button("📤 Sell", key="tbl_sell_btn",
                                     use_container_width=True, type="primary",
                                     disabled=(_sh.quantity <= 1e-9)):
                            import random as _rnd
                            # New random open-ID → all widget keys are brand-new
                            # → Streamlit has no cached state → value= always wins
                            st.session_state["_sell_oid"] = _rnd.randint(0, 9_999_999)
                            _dlg_sell(_st, _sh)
                    with _ab3:
                        if st.button("📋 Settle", key="tbl_settle_btn",
                                     use_container_width=True):
                            _dlg_settlement(_st, _sh)
                    with _ab4:
                        if st.button("✏️ Edit", key="tbl_edit_btn",
                                     use_container_width=True):
                            _dlg_edit(_st, _sh)
                    with _ab5:
                        if st.button("🗑️ Del", key="tbl_del_btn",
                                     use_container_width=True):
                            _dlg_delete(_st, _sh)

    # ── Bulk Upload button when portfolio is empty ────────────────────────────
    if not holdings:
        _ec1, _ec2 = st.columns(2)
        with _ec1:
            if st.button("⬆️ Bulk Upload", key="open_bulk_upload_empty_btn",
                         use_container_width=True,
                         help="Upload multiple new positions from a CSV file."):
                _dlg_bulk_upload()
        with _ec2:
            if st.button("➕ Add New Position", key="open_add_new_empty_btn",
                         type="primary", use_container_width=True):
                _dlg_add_new()


def render_allocation_tab(bundle: dict) -> None:
    """
    📊 Allocation tab — analytical view of portfolio allocation.

    Uses the shared valuation bundle computed once per re-run in the main UI.
    Renders the full _render_allocation_section (chart view selector, filters,
    filtered summary, chart, export CSV, filtered table) without calling any
    external API or mutating any portfolio state.
    """
    holdings = bundle["holdings"]
    val      = bundle["val"]
    base_ccy = bundle["base_ccy"]

    if not holdings:
        st.info(
            "No holdings yet. Add a position in **💼 Holdings** first.",
            icon="💡",
        )
        return

    _render_allocation_section(val, holdings, base_ccy)


def render_accounts_tab() -> None:
    """Investment Accounts — manage accounts and cash balances."""
    from portfolio.accounts import (
        load_accounts, upsert_account, update_account_cash,
        account_display_name, ACCOUNT_TYPES,
    )
    from portfolio.cash_ledger import append_cash_entry
    from portfolio import CURRENCIES
    from fx_rates import get_rates_for_holdings
    import pandas as pd
    from datetime import date as _date_cls

    st.header("💳 Accounts")
    st.caption(
        "Manage your investment accounts, bank accounts, and cash wallets. "
        "Each account tracks its own cash balance independently."
    )

    accounts = load_accounts()
    active   = {aid: a for aid, a in accounts.items() if a.active}

    # ── Summary ───────────────────────────────────────────────────────────────
    _ab_ccy = st.session_state.get("global_base_ccy", "SAR")
    _ab_ccys = list({a.base_currency for a in active.values()})
    _ab_fx   = get_rates_for_holdings(_ab_ccys, _ab_ccy) if _ab_ccys else {}
    from portfolio.valuation import calculate_portfolio_valuation as _calc_acct_val
    _acct_val   = _calc_acct_val({}, accounts, _ab_ccy, fx_rates=_ab_fx)
    _total_cash = _acct_val.cash_value_base

    if accounts:
        _n_ccy = len({a.base_currency for a in active.values()})
        st.markdown(
            f'<div class="acct-summary-row">'
            f'  <div class="acct-kpi">'
            f'    <div class="acct-kpi-lbl">Accounts</div>'
            f'    <div class="acct-kpi-val">{len(active)}</div>'
            f'  </div>'
            f'  <div class="acct-kpi">'
            f'    <div class="acct-kpi-lbl">Total Cash ({_ab_ccy})</div>'
            f'    <div class="acct-kpi-val">{_total_cash:,.2f}</div>'
            f'  </div>'
            f'  <div class="acct-kpi">'
            f'    <div class="acct-kpi-lbl">Currencies</div>'
            f'    <div class="acct-kpi-val">{_n_ccy}</div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Account cards ─────────────────────────────────────────────────────────
    if active:
        st.subheader("📂 Your Accounts")
        for aid, a in sorted(active.items(), key=lambda x: x[1].account_name):
            with st.container(border=True):
                ac1, ac2, ac3 = st.columns([3, 2, 2])
                with ac1:
                    st.markdown(f"**{a.account_name}**")
                    if a.institution:
                        st.caption(a.institution)
                    st.caption(f"{a.account_type} · {a.base_currency}")
                with ac2:
                    st.metric(f"Cash ({a.base_currency})", f"{a.cash_balance:,.2f}")
                with ac3:
                    if st.button("+ Deposit",  key=f"dep_btn_{aid}"):
                        st.session_state[f"dep_open_{aid}"] = not st.session_state.get(f"dep_open_{aid}", False)
                    if st.button("− Withdraw", key=f"wdr_btn_{aid}"):
                        st.session_state[f"wdr_open_{aid}"] = not st.session_state.get(f"wdr_open_{aid}", False)

                if st.session_state.get(f"dep_open_{aid}"):
                    with st.form(f"dep_form_{aid}"):
                        _d1, _d2 = st.columns(2)
                        with _d1:
                            _d_amt  = st.number_input("Amount", min_value=0.01, step=100.0, format="%.2f")
                            _d_dt   = st.date_input("Date", value=_date_cls.today())
                        with _d2:
                            _d_note = st.text_input("Note (optional)")
                        if st.form_submit_button("✅ Confirm Deposit", type="primary"):
                            update_account_cash(aid, _d_amt)
                            append_cash_entry(
                                account_id=aid, transaction_type="DEPOSIT",
                                currency=a.base_currency, amount=_d_amt,
                                notes=_d_note or "Manual deposit", entry_date=_d_dt.isoformat(),
                            )
                            st.session_state.pop(f"dep_open_{aid}", None)
                            st.toast(f"Deposited {a.base_currency} {_d_amt:,.2f}", icon="💰")
                            st.rerun()

                if st.session_state.get(f"wdr_open_{aid}"):
                    with st.form(f"wdr_form_{aid}"):
                        _w1, _w2 = st.columns(2)
                        with _w1:
                            _w_amt  = st.number_input("Amount", min_value=0.01, step=100.0, format="%.2f")
                            _w_dt   = st.date_input("Date", value=_date_cls.today())
                        with _w2:
                            _w_note = st.text_input("Note (optional)")
                        if st.form_submit_button("✅ Confirm Withdrawal", type="primary"):
                            update_account_cash(aid, -_w_amt)
                            append_cash_entry(
                                account_id=aid, transaction_type="WITHDRAWAL",
                                currency=a.base_currency, amount=-_w_amt,
                                notes=_w_note or "Manual withdrawal", entry_date=_w_dt.isoformat(),
                            )
                            st.session_state.pop(f"wdr_open_{aid}", None)
                            st.toast(f"Withdrew {a.base_currency} {_w_amt:,.2f}", icon="💸")
                            st.rerun()

    elif not accounts:
        st.info("No accounts yet — add your first account below.", icon="💡")

    # ── Inactive accounts ─────────────────────────────────────────────────────
    inactive = {aid: a for aid, a in accounts.items() if not a.active}
    if inactive:
        with st.expander(f"💤 Inactive Accounts ({len(inactive)})", expanded=False):
            for aid, a in inactive.items():
                ic1, ic2 = st.columns([4, 1])
                ic1.caption(
                    f"**{a.account_name}** · {a.institution or '—'} · "
                    f"{a.base_currency} {a.cash_balance:,.2f}"
                )
                with ic2:
                    if st.button("Reactivate", key=f"react_{aid}"):
                        upsert_account(
                            account_id=aid,
                            account_name=a.account_name,
                            institution=a.institution,
                            account_type=a.account_type,
                            base_currency=a.base_currency,
                            notes=a.notes,
                            active=True,
                        )
                        st.rerun()

    # ── Add Account form ──────────────────────────────────────────────────────
    st.divider()
    with st.expander("➕ Add Account", expanded=not accounts):
        with st.form("add_account_form"):
            fa1, fa2 = st.columns(2)
            with fa1:
                na_name = st.text_input("Account name *", placeholder="e.g. Derayah USD")
                na_inst = st.text_input("Institution",    placeholder="e.g. Derayah")
                na_type = st.selectbox("Account type", ACCOUNT_TYPES)
            with fa2:
                na_ccy  = st.selectbox("Base currency", CURRENCIES)
                na_bal  = st.number_input(
                    "Opening cash balance", min_value=0.0, step=100.0, format="%.2f",
                    help="Leave 0 to add cash via + Deposit later.",
                )
                na_note = st.text_input("Notes (optional)")
            if st.form_submit_button("➕ Add Account", type="primary"):
                if not na_name.strip():
                    st.error("Account name is required.")
                else:
                    new_a = upsert_account(
                        account_name  = na_name.strip(),
                        institution   = na_inst.strip(),
                        account_type  = na_type,
                        base_currency = na_ccy,
                        opening_cash  = na_bal,
                        notes         = na_note.strip(),
                    )
                    if na_bal > 0:
                        append_cash_entry(
                            account_id=new_a.account_id,
                            transaction_type="INITIAL_BALANCE",
                            currency=na_ccy, amount=na_bal,
                            notes="Opening balance",
                        )
                    st.toast(f"Account '{na_name}' created.", icon="✅")
                    st.rerun()

    # ── Edit / Deactivate ─────────────────────────────────────────────────────
    if active:
        st.divider()
        with st.expander("✏️ Edit Account", expanded=False):
            _ea_opts = {account_display_name(a): aid for aid, a in active.items()}
            _ea_lbl  = st.selectbox("Select account to edit", list(_ea_opts.keys()))
            _ea_id   = _ea_opts[_ea_lbl]
            _ea      = active[_ea_id]
            with st.form("edit_account_form"):
                ee1, ee2 = st.columns(2)
                with ee1:
                    ea_name = st.text_input("Account name", value=_ea.account_name)
                    ea_inst = st.text_input("Institution",  value=_ea.institution)
                    ea_type = st.selectbox("Account type", ACCOUNT_TYPES,
                                           index=ACCOUNT_TYPES.index(_ea.account_type)
                                           if _ea.account_type in ACCOUNT_TYPES else 0)
                with ee2:
                    ea_ccy  = st.selectbox("Base currency", CURRENCIES,
                                           index=CURRENCIES.index(_ea.base_currency)
                                           if _ea.base_currency in CURRENCIES else 0)
                    ea_note = st.text_input("Notes", value=_ea.notes)
                    ea_act  = st.checkbox("Active", value=_ea.active)
                ea_sub1, ea_sub2 = st.columns(2)
                with ea_sub1:
                    if st.form_submit_button("💾 Save", type="primary"):
                        upsert_account(
                            account_id=_ea_id,
                            account_name=ea_name.strip() or _ea.account_name,
                            institution=ea_inst.strip(),
                            account_type=ea_type,
                            base_currency=ea_ccy,
                            notes=ea_note.strip(),
                            active=ea_act,
                        )
                        st.toast("Account updated.", icon="💾")
                        st.rerun()


def render_transactions_tab() -> None:
    """Transaction History — audit log of all buy/sell/settlement activity."""
    from portfolio import (
        load_transactions,
        SETTLEMENT_CATEGORIES, CURRENCIES,
        edit_settlement as _rt_edit_settle,
        delete_settlement as _rt_del_settle,
    )
    from portfolio.accounts import load_accounts, account_display_name as _rt_adn
    import pandas as pd

    # ── Dialog: Edit Settlement ──────────────────────────────────────────────
    @st.dialog("✏️ Edit Settlement")
    def _dlg_edit_settlement(txn):
        from portfolio.accounts import load_accounts as _es_la
        st.caption(
            f"ID **{txn.transaction_id[:8]}…** · recorded {txn.date}  \n"
            "Cash reversal is handled automatically — audit trail preserved."
        )

        # Category
        _orig_cat = txn.settlement_category or "Dividend"
        _cat_idx  = SETTLEMENT_CATEGORIES.index(_orig_cat) if _orig_cat in SETTLEMENT_CATEGORIES else 0
        _es_cat   = st.selectbox(
            "Category", SETTLEMENT_CATEGORIES,
            index=_cat_idx,
            key=f"es_edit_cat_{txn.transaction_id}",
        )

        # Direction — auto-locked by category
        _INCOME_CATS  = {"Dividend"}
        _EXPENSE_CATS = {"Fee", "Tax", "Zakat", "Islamic Purification"}
        _orig_amt     = txn.settlement_amount
        if _es_cat in _INCOME_CATS:
            _es_dir = "Income"
            st.info("✅ **Income / Credit** — auto-set for this category", icon="ℹ️")
        elif _es_cat in _EXPENSE_CATS:
            _es_dir = "Expense"
            st.info("💸 **Expense / Debit** — auto-set for this category", icon="ℹ️")
        else:
            _init_dir = "Income" if _orig_amt >= 0 else "Expense"
            _es_dir = st.radio(
                "Direction", ["Income", "Expense"],
                index=["Income", "Expense"].index(_init_dir),
                horizontal=True,
                key=f"es_edit_dir_{txn.transaction_id}",
            )

        # Date / Amount / Currency
        _esd1, _esd2, _esd3 = st.columns(3)
        with _esd1:
            _es_date = st.date_input(
                "Date", value=date.fromisoformat(txn.date),
                key=f"es_edit_date_{txn.transaction_id}",
            )
        with _esd2:
            _es_abs = st.number_input(
                "Amount", value=abs(_orig_amt),
                min_value=0.0, step=0.01, format="%.2f",
                key=f"es_edit_amt_{txn.transaction_id}",
                help="Enter the absolute amount — direction is determined above.",
            )
        with _esd3:
            _es_def_ccy = txn.settlement_currency or "SAR"
            _es_ccy_idx = CURRENCIES.index(_es_def_ccy) if _es_def_ccy in CURRENCIES else 0
            _es_ccy = st.selectbox(
                "Currency", CURRENCIES, index=_es_ccy_idx,
                key=f"es_edit_ccy_{txn.transaction_id}",
            )

        _es_signed = _es_abs if _es_dir == "Income" else -_es_abs

        # Account
        _es_accounts  = _es_la()
        _es_acct_sort = sorted(_es_accounts.values(), key=lambda a: a.account_name)
        _es_acct_lbls = ["— no account —"] + [
            _rt_adn(a) + (f"  ⚠️ ({a.base_currency} ≠ {_es_ccy})" if a.base_currency != _es_ccy else "")
            for a in _es_acct_sort
        ]
        _es_acct_ids  = [None] + [a.account_id for a in _es_acct_sort]
        _cur_idx      = next((i for i, aid in enumerate(_es_acct_ids) if aid == (txn.account_id or "")), 0)
        _es_acct_sel  = st.selectbox(
            "Account", _es_acct_lbls, index=_cur_idx,
            key=f"es_edit_acct_{txn.transaction_id}",
        )
        _es_acct_id   = _es_acct_ids[_es_acct_lbls.index(_es_acct_sel)] or ""
        if _es_acct_id and _es_accounts.get(_es_acct_id):
            _ao = _es_accounts[_es_acct_id]
            st.caption(f"Balance: **{_ao.cash_balance:,.2f} {_ao.base_currency}**")

        # Notes
        _es_notes = st.text_area(
            "Notes (min. 10 characters)", value=txn.notes or "",
            max_chars=500, key=f"es_edit_notes_{txn.transaction_id}",
        )
        st.caption(f"{len(_es_notes.strip())} / 10 minimum characters")

        st.divider()
        _eb1, _eb2 = st.columns(2)
        with _eb1:
            if st.button(
                "💾 Save Changes", type="primary",
                use_container_width=True,
                key=f"es_edit_save_{txn.transaction_id}",
            ):
                _upd, _err = _rt_edit_settle(
                    transaction_id=txn.transaction_id,
                    amount=_es_signed,
                    category=_es_cat,
                    currency=_es_ccy,
                    settlement_date=_es_date.isoformat(),
                    notes=_es_notes,
                    account_id=_es_acct_id,
                )
                if _err:
                    st.error(_err)
                else:
                    _sgn2 = "+" if _es_signed >= 0 else ""
                    st.toast(
                        f"Settlement updated: {_es_cat} {_sgn2}{_es_signed:,.2f} {_es_ccy}",
                        icon="💾",
                    )
                    st.rerun()
        with _eb2:
            if st.button("Cancel", use_container_width=True,
                         key=f"es_edit_cancel_{txn.transaction_id}"):
                st.rerun()

    # ── Dialog: Delete Settlement ─────────────────────────────────────────────
    @st.dialog("🗑️ Delete Settlement")
    def _dlg_delete_settlement(txn):
        _cat = txn.settlement_category or "Settlement"
        _amt = txn.settlement_amount
        _ccy = txn.settlement_currency or ""
        _sgn = "+" if _amt >= 0 else ""
        st.warning(
            f"Delete this **{_cat}** of **{_sgn}{_amt:,.2f} {_ccy}** on **{txn.date}**?  \n\n"
            "The cash effect will be **reversed** via a negating ledger entry "
            "(audit trail preserved).",
            icon="⚠️",
        )
        _ds_conf = st.checkbox(
            "I understand — the settlement and its cash effect will be reversed",
            key=f"ds_conf_{txn.transaction_id}",
        )
        _db1, _db2 = st.columns(2)
        with _db1:
            if st.button(
                "🗑️ Delete", type="primary",
                use_container_width=True, disabled=not _ds_conf,
                key=f"ds_del_{txn.transaction_id}",
            ):
                _err = _rt_del_settle(txn.transaction_id)
                if _err:
                    st.error(_err)
                else:
                    st.toast(f"{_cat} settlement deleted", icon="🗑️")
                    st.rerun()
        with _db2:
            if st.button("Cancel", use_container_width=True,
                         key=f"ds_cancel_{txn.transaction_id}"):
                st.rerun()

    st.header("📜 Transaction History")
    st.caption(
        "Complete audit trail of all trades and settlement transactions. "
        "Record trades via **➕ Buy More** or **📤 Sell / Close** on the **💼 Holdings** tab. "
        "Record dividends, fees, and other settlements via **📋 Settlement**."
    )

    accounts = load_accounts()
    txns = load_transactions()

    if not txns:
        st.info(
            "No transactions recorded yet. "
            "Use **➕ Add New Position** or **Buy More / Sell / Settlement** "
            "on the **💼 Holdings** tab to get started.",
            icon="💡",
        )
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    _fc1, _fc2, _fc3, _fc4 = st.columns(4)
    with _fc1:
        _type_filter = st.selectbox(
            "Type", ["All", "Trades", "Settlements"], key="txh_type"
        )
    with _fc2:
        _side_filter = st.selectbox("Side", ["All", "BUY", "SELL"], key="txh_side")
    with _fc3:
        _all_tickers = sorted({t.ticker for t in txns if t.ticker})
        _tk_filter = st.selectbox("Ticker", ["All"] + _all_tickers, key="txh_ticker")
    with _fc4:
        _acct_names = {aid: a.account_name for aid, a in accounts.items()}
        _all_accts_used = sorted({
            _acct_names.get(getattr(t, "account_id", ""), "—") or "—"
            for t in txns
        })
        _acct_filter = st.selectbox(
            "Account", ["All"] + _all_accts_used, key="txh_acct"
        )

    # ── Apply filters ─────────────────────────────────────────────────────────
    _filtered = txns
    if _type_filter == "Trades":
        _filtered = [t for t in _filtered if t.side in ("BUY", "SELL")]
    elif _type_filter == "Settlements":
        _filtered = [t for t in _filtered if t.side == "SETTLEMENT"]
    if _side_filter != "All":
        _filtered = [t for t in _filtered if t.side == _side_filter]
    if _tk_filter != "All":
        _filtered = [t for t in _filtered if t.ticker == _tk_filter]
    if _acct_filter != "All":
        _filtered = [
            t for t in _filtered
            if (_acct_names.get(getattr(t, "account_id", ""), "—") or "—") == _acct_filter
        ]

    _sorted = sorted(_filtered, key=lambda t: (t.date, t.recorded_at), reverse=True)

    if _sorted:
        rows = []
        for _t in _sorted:
            _is_settle = _t.side == "SETTLEMENT"
            _s_amt     = getattr(_t, "settlement_amount", 0.0)
            _s_cat     = getattr(_t, "settlement_category", "")
            _s_cur     = getattr(_t, "settlement_currency", "")
            _display_ticker = _t.ticker if _t.ticker else ("Portfolio" if _is_settle else "—")
            if _is_settle:
                _detail = f"{_s_amt:+,.2f} {_s_cur}" if _s_cur else f"{_s_amt:+,.2f}"
                _val    = _s_amt
            else:
                _detail = f"{_t.quantity:,.4f} × {_t.price:,.4f}"
                _val    = round(_t.quantity * _t.price, 2)
            rows.append({
                "Date":     _t.date,
                "Ticker":   _display_ticker,
                "Type":     _t.side,
                "Detail":   _detail,
                "Value":    _val,
                "Category": _s_cat if _is_settle else "—",
                "Fees":     getattr(_t, "fees", 0.0),
                "Account":  _acct_names.get(getattr(_t, "account_id", ""), "—") or "—",
                "Notes":    _t.notes,
            })
        _txn_df = pd.DataFrame(rows)
        _txn_df.index = range(1, len(_txn_df) + 1)
        st.dataframe(_txn_df, use_container_width=True)

        # ── Settlement action rows (edit / delete per settlement) ─────────────
        _settle_in_view = [t for t in _sorted if t.side == "SETTLEMENT"]
        if _settle_in_view:
            with st.expander(
                f"✏️ Edit / Delete Settlements ({len(_settle_in_view)})",
                expanded=False,
            ):
                for _es_t in _settle_in_view:
                    _sgn_s = "+" if _es_t.settlement_amount >= 0 else ""
                    _ea1, _ea2, _ea3 = st.columns([5, 1, 1])
                    with _ea1:
                        st.caption(
                            f"**{_es_t.date}** · {_es_t.settlement_category or '—'} · "
                            f"{_sgn_s}{_es_t.settlement_amount:,.2f} "
                            f"{_es_t.settlement_currency or ''}"
                            + (f" · {_es_t.ticker}" if _es_t.ticker else " · Portfolio")
                        )
                    with _ea2:
                        if st.button(
                            "✏️ Edit",
                            key=f"txh_es_edit_{_es_t.transaction_id}",
                            use_container_width=True,
                        ):
                            _dlg_edit_settlement(_es_t)
                    with _ea3:
                        if st.button(
                            "🗑️ Del",
                            key=f"txh_es_del_{_es_t.transaction_id}",
                            use_container_width=True,
                        ):
                            _dlg_delete_settlement(_es_t)

        # ── Summary metrics ───────────────────────────────────────────────────
        _buys    = [t for t in _sorted if t.side == "BUY"]
        _sells   = [t for t in _sorted if t.side == "SELL"]
        _settles = [t for t in _sorted if t.side == "SETTLEMENT"]
        _net_settle = sum(getattr(t, "settlement_amount", 0.0) for t in _settles)
        _m1, _m2, _m3, _m4, _m5, _m6 = st.columns(6)
        _m1.metric("Total",       len(_sorted))
        _m2.metric("Buys",        len(_buys))
        _m3.metric("Sells",       len(_sells))
        _m4.metric("Settlements", len(_settles))
        _m5.metric("Net Settlement", f"{_net_settle:+,.2f}")
        _m6.metric("Total Fees",  f"{sum(getattr(t,'fees',0.0) for t in _sorted):,.2f}")
    else:
        st.info("No transactions match the current filters.", icon="🔍")


def render_cash_ledger_tab() -> None:
    """Cash Ledger — full audit trail of all cash movements."""
    from portfolio.cash_ledger import load_ledger, txn_icon, CASH_TXN_TYPES
    from portfolio.accounts import load_accounts
    import pandas as pd

    st.header("💵 Cash Ledger")
    st.caption("Complete history of cash movements across all accounts.")

    accounts = load_accounts()
    entries  = load_ledger()

    if not entries:
        st.info(
            "No cash entries yet. "
            "Record a transaction in **🔁 Transactions** or add an account in **💳 Accounts**.",
            icon="💡",
        )
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    fc1, fc2 = st.columns(2)
    with fc1:
        _acct_opts = {"All accounts": None}
        _acct_opts.update({
            f"{a.account_name} ({a.base_currency})": aid
            for aid, a in sorted(accounts.items(), key=lambda x: x[1].account_name)
        })
        _sel_acct = st.selectbox("Filter by account", list(_acct_opts.keys()), key="cl_acct")
        _sel_aid  = _acct_opts[_sel_acct]
    with fc2:
        _type_opts = ["All types"] + CASH_TXN_TYPES
        _sel_type  = st.selectbox("Filter by type", _type_opts, key="cl_type")

    filtered = [
        e for e in entries
        if (_sel_aid is None or e.account_id == _sel_aid)
        and (_sel_type == "All types" or e.transaction_type == _sel_type)
    ]
    filtered.sort(key=lambda e: (e.date, e.recorded_at), reverse=True)

    if not filtered:
        st.info("No entries match the current filters.", icon="ℹ️")
        return

    rows = []
    for e in filtered:
        _an = accounts[e.account_id].account_name if e.account_id in accounts else (e.account_id or "—")
        rows.append({
            "":         txn_icon(e.transaction_type),
            "Date":     e.date,
            "Account":  _an,
            "Type":     e.transaction_type,
            "Amount":   round(e.amount, 2),
            "Ccy":      e.currency,
            "Ticker":   e.linked_ticker or "—",
            "Notes":    e.notes or "—",
        })

    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(f"{len(filtered)} of {len(entries)} entries shown.")

    # ── Running balance per account (if filtered) ─────────────────────────────
    if _sel_aid and _sel_aid in accounts:
        _acct_entries = sorted(
            [e for e in entries if e.account_id == _sel_aid],
            key=lambda e: (e.date, e.recorded_at),
        )
        running = 0.0
        bal_rows = []
        for e in _acct_entries:
            running = round(running + e.amount, 8)
            bal_rows.append({
                "Date":    e.date,
                "Type":    e.transaction_type,
                "Amount":  round(e.amount, 2),
                "Balance": running,
                "Notes":   e.notes or "—",
            })
        with st.expander("📊 Running balance for this account", expanded=False):
            st.dataframe(pd.DataFrame(bal_rows), hide_index=True, use_container_width=True)


def render_cashflow_tab() -> None:
    """Investment Cashflow — actual cash generated/consumed by portfolio activity."""
    from portfolio.cash_ledger import load_ledger
    from fx_rates import get_rates_for_holdings
    from collections import defaultdict
    import plotly.graph_objects as go
    import pandas as pd
    from datetime import datetime as _cf_dt

    base_ccy = st.session_state.get("global_base_ccy", "SAR")

    st.header("💹 Investment Cashflow")
    st.caption(
        "Actual cash generated and consumed by portfolio activity — "
        "SELL proceeds, dividends received, BUY settlements, and fees. "
        "Personal deposits and withdrawals are excluded."
    )

    entries = load_ledger()
    _INVEST_TYPES = {"BUY", "SELL", "DIVIDEND", "FEE"}
    inv_entries = [e for e in entries if e.transaction_type in _INVEST_TYPES]

    if not inv_entries:
        st.info(
            "No investment cashflow entries yet. "
            "Record BUY / SELL / Dividend transactions to see cashflow trends here.",
            icon="💡",
        )
        return

    # ── FX conversion — convert each entry to base_ccy ──────────────────────
    _ccys = list({e.currency for e in inv_entries})
    _fx   = get_rates_for_holdings(_ccys, base_ccy) if _ccys else {}

    def _to_base(amount: float, ccy: str) -> float:
        if ccy == base_ccy:
            return amount
        return amount * _fx.get(ccy, 1.0)

    # ── Aggregate by month ───────────────────────────────────────────────────
    _m_in:      dict[str, float] = defaultdict(float)
    _m_out:     dict[str, float] = defaultdict(float)
    _m_by_type: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for e in inv_entries:
        ym  = e.date[:7]
        amt = _to_base(e.amount, e.currency)
        if amt >= 0:
            _m_in[ym]  += amt
        else:
            _m_out[ym] += abs(amt)
        _m_by_type[ym][e.transaction_type] += amt

    _all_months = sorted(set(_m_in) | set(_m_out))
    _last6      = _all_months[-6:] if len(_all_months) >= 6 else _all_months

    def _mlabel(ym: str) -> str:
        try:
            return _cf_dt.strptime(ym, "%Y-%m").strftime("%b %Y")
        except ValueError:
            return ym

    # ── Summary metrics (latest month) ──────────────────────────────────────
    _latest = _last6[-1] if _last6 else None
    if _latest:
        _in  = _m_in.get(_latest, 0.0)
        _out = _m_out.get(_latest, 0.0)
        _net = _in - _out
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric(
            f"Cash In · {_mlabel(_latest)}",
            f"{_in:,.2f} {base_ccy}",
            help="SELL proceeds + dividends received",
        )
        mc2.metric(
            f"Cash Out · {_mlabel(_latest)}",
            f"{_out:,.2f} {base_ccy}",
            help="BUY settlements + fees paid",
        )
        mc3.metric(
            f"Net · {_mlabel(_latest)}",
            f"{_net:,.2f} {base_ccy}",
            delta=f"{_net:+,.2f}" if _net != 0 else None,
            help="Positive = portfolio generated more cash than it consumed",
        )

    st.divider()

    # ── Grouped bar chart ────────────────────────────────────────────────────
    _labels   = [_mlabel(m) for m in _last6]
    _in_vals  = [_m_in.get(m,  0.0) for m in _last6]
    _out_vals = [_m_out.get(m, 0.0) for m in _last6]

    _cf_fig = go.Figure()
    _cf_fig.add_trace(go.Bar(
        name="Cash In",
        x=_labels, y=_in_vals,
        marker_color="#22c55e",
        marker_line_width=0,
        text=[f"{v:,.2f}" if v > 0 else "" for v in _in_vals],
        textposition="outside",
        textfont=dict(size=10),
    ))
    _cf_fig.add_trace(go.Bar(
        name="Cash Out",
        x=_labels, y=_out_vals,
        marker_color="#ef4444",
        marker_line_width=0,
        text=[f"{v:,.2f}" if v > 0 else "" for v in _out_vals],
        textposition="outside",
        textfont=dict(size=10),
    ))
    _cf_fig.update_layout(
        barmode="group",
        height=280,
        margin=dict(l=40, r=10, t=30, b=50),
        bargap=0.25,
        bargroupgap=0.05,
        legend=dict(
            orientation="h", yanchor="top", y=-0.12,
            xanchor="left", x=0, font=dict(size=11),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(128,128,128,0.15)",
            tickformat=",.0f",
            tickfont=dict(size=11),
            ticksuffix=f" {base_ccy}",
        ),
        xaxis=dict(tickfont=dict(size=11)),
    )
    st.caption(f"📊 **Investment Cashflow — last {len(_last6)} months** · {base_ccy} · BUY/SELL/Dividend/Fee only")
    st.plotly_chart(_cf_fig, use_container_width=True, config={"displayModeBar": False})

    # ── Monthly summary table ────────────────────────────────────────────────
    st.subheader("Monthly Breakdown")
    _rows = []
    for m in reversed(_all_months):
        _i   = _m_in.get(m,  0.0)
        _o   = _m_out.get(m, 0.0)
        _n   = _i - _o
        _t   = _m_by_type.get(m, {})
        _rows.append({
            "Month":               _mlabel(m),
            f"In ({base_ccy})":    round(_i, 2),
            f"Out ({base_ccy})":   round(_o, 2),
            f"Net ({base_ccy})":   round(_n, 2),
            "Flow":                "▲" if _n >= 0 else "▼",
            "Dividends":           round(_t.get("DIVIDEND", 0.0), 2),
            "Sell Proceeds":       round(_t.get("SELL",     0.0), 2),
            "Buys":                round(abs(_t.get("BUY", 0.0)), 2),
            "Fees":                round(abs(_t.get("FEE", 0.0)), 2),
        })
    if _rows:
        st.dataframe(pd.DataFrame(_rows), hide_index=True, use_container_width=True)
        st.caption(
            "Amounts in base currency. "
            "Buys and Fees show the amount paid (positive for readability). "
            "▲ = net cash positive month · ▼ = net cash consumed month."
        )


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
    for h in holdings.values():
        c = theses.get(h.ticker)
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
        asset_id, h = item
        c = theses.get(h.ticker)
        if c is None:
            return (5, h.ticker)  # unauthored at bottom
        return (_STATUS_ORDER.get(c.thesis_status, 4),
                0 if c.drift_detected else 1,
                h.ticker)

    for asset_id, h in sorted(holdings.items(), key=_sort_key):
        c = theses.get(h.ticker)
        with st.container(border=True):
            # ── Header row: identity · status · conviction trend ─────────────
            hc1, hc2, hc3 = st.columns([2.5, 2, 2])
            with hc1:
                st.markdown(f"### {h.ticker}")
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
                    .get("ticker") == h.ticker
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
                    h.ticker, h, c,
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
                        h.ticker, c,
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
            # holdings keyed by asset_id; build ticker→asset_id map for display
            _imp_aid_by_ticker = {(h.ticker or aid): aid for aid, h in holdings.items()}
            tickers = sorted(_imp_aid_by_ticker.keys())
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
                holding    = holdings[_imp_aid_by_ticker[ticker_sel]]
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
                st.table(df.set_index("Signal"))

    st.caption(f"Computed at {result.computed_at}")


def render_closed_holdings_tab() -> None:
    """📁 Closed Holdings — fully-sold positions with FIFO realized P&L."""
    from portfolio import (
        load_closed_holdings,
        compute_realized_summary,
        void_lots_for_ticker,
        upsert_holding,
        load_holdings,
    )
    from portfolio.accounts import load_accounts
    from portfolio.accounts import account_display_name
    import pandas as pd

    st.header("📁 Closed Holdings")
    st.caption(
        "Positions you have fully or partially sold. "
        "Realized P&L is calculated using **FIFO** cost basis."
    )

    closed = load_closed_holdings()
    summary = compute_realized_summary(closed)

    # ── Summary metrics ────────────────────────────────────────────────────────
    sm1, sm2, sm3, sm4, sm5 = st.columns(5)
    _sign = "+" if summary.total_realized_pnl >= 0 else ""
    sm1.metric("Closed Positions",   summary.n_closed)
    sm2.metric("Total Realized P&L", f"{_sign}{summary.total_realized_pnl:,.2f}")
    sm3.metric("Win Rate",           f"{summary.win_rate_pct:.1f}%" if summary.n_closed else "—")
    sm4.metric("Winners / Losers",   f"{summary.n_winners} / {summary.n_losers}" if summary.n_closed else "—")
    sm5.metric("Avg Return",         f"{summary.avg_return_pct:+.2f}%" if summary.n_closed else "—")

    if not closed:
        st.info(
            "No closed positions yet. When you record a **SELL** transaction in the "
            "**💼 Holdings** tab, the realized P&L will appear here automatically.",
            icon="💡",
        )
        return

    st.divider()

    # ── Per-ticker closed holding cards ────────────────────────────────────────
    for ticker, ch in sorted(closed.items()):
        pnl_color = "🟢" if ch.realized_pnl > 0 else ("🔴" if ch.realized_pnl < 0 else "⚪")
        _sign2 = "+" if ch.realized_pnl >= 0 else ""
        with st.expander(
            f"{pnl_color}  **{ticker}**  ·  {ch.company_name}  ·  "
            f"P&L: **{_sign2}{ch.realized_pnl:,.2f} {ch.currency}** "
            f"({ch.realized_pnl_pct:+.2f}%)  ·  "
            f"{ch.total_quantity:,.4f} shares  ·  held {ch.holding_period_label}",
            expanded=False,
        ):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Avg Buy Price",  f"{ch.avg_buy_price:,.4f}")
            c2.metric("Avg Sell Price", f"{ch.avg_sell_price:,.4f}")
            c3.metric("Total Buy",      f"{ch.total_buy_value:,.2f}")
            c4.metric("Total Sell",     f"{ch.total_sell_value:,.2f}")
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Fees",           f"{ch.total_fees:,.2f}")
            c6.metric("Realized P&L",   f"{_sign2}{ch.realized_pnl:,.2f}")
            c7.metric("Return %",       f"{ch.realized_pnl_pct:+.2f}%")
            c8.metric("Holding Period", ch.holding_period_label)
            st.caption(
                f"First opened: {ch.first_open_date or '—'}  ·  "
                f"Last closed: {ch.last_close_date or '—'}  ·  "
                f"Currency: {ch.currency}  ·  FIFO lots: {len(ch.lots)}"
            )

            # Lot detail table
            lot_rows = []
            for lot in ch.lots:
                lot_rows.append({
                    "Buy Date":   lot.open_date,
                    "Sell Date":  lot.close_date,
                    "Qty":        round(lot.quantity, 4),
                    "Buy Price":  round(lot.buy_price, 4),
                    "Sell Price": round(lot.sell_price, 4),
                    "Buy Value":  round(lot.buy_value, 4),
                    "Sell Value": round(lot.sell_value, 4),
                    "Fees":       round(lot.sell_fees, 4),
                    "P&L":        round(lot.realized_pnl, 4),
                    "P&L %":      round(lot.realized_pnl_pct, 2),
                    "Held":       lot.holding_period_label,
                })
            if lot_rows:
                st.dataframe(pd.DataFrame(lot_rows), hide_index=True, use_container_width=True)



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


# ── Wealth & Performance — read-only money-weighted analytics ────────────────
def render_performance_tab() -> None:
    """Read-only Wealth & Performance dashboard.

    Surfaces money-weighted return (XIRR), net contributions vs. growth,
    dividend income, a Zakat estimate, realized gains by period, and a
    data-integrity reconciliation check. Everything is derived from the
    existing holdings / transactions / cash ledger — nothing is mutated.
    """
    from portfolio import load_holdings, load_transactions
    from portfolio.accounts import load_accounts as _perf_load_accts
    from portfolio.cash_ledger import load_ledger
    from portfolio.closed_holdings import load_closed_lots
    from portfolio.valuation import calculate_portfolio_valuation
    from fx_rates import get_rates_for_holdings
    from portfolio.performance import compute_performance
    from portfolio.income import dividend_summary
    from portfolio.zakat import (
        compute_zakat, zakat_paid_to_date, RATE_LUNAR, RATE_GREGORIAN,
    )
    from portfolio.tax_report import realized_report
    from portfolio.reconciliation import reconcile_holdings
    import pandas as pd

    st.header("📈 Wealth & Performance")
    st.caption(
        "Read-only analytics derived from your holdings, transactions, and cash "
        "ledger. Nothing here changes your data."
    )

    base_ccy = st.session_state.get("global_base_ccy", "SAR")
    if base_ccy == "— Native —":
        base_ccy = "SAR"   # analytics engine always needs a real ISO currency
    holdings = load_holdings()
    accounts = _perf_load_accts()
    txns     = load_transactions()
    ledger   = load_ledger()
    closed   = load_closed_lots()

    if not holdings and not txns and not closed:
        st.info(
            "Add holdings and record transactions to see performance analytics.",
            icon="💡",
        )
        return

    _ccys = {getattr(h, "currency", base_ccy) for h in holdings.values()} if holdings else set()
    _fx   = get_rates_for_holdings(list(_ccys), base_ccy) if _ccys else {}
    val   = calculate_portfolio_valuation(holdings, accounts, base_ccy, fx_rates=_fx)
    _fxu  = val.fx_rates_used

    # ── T8: FX source warnings + price freshness ─────────────────────────────
    if val.warnings:
        for _vw in val.warnings:
            st.warning(_vw, icon="⚠️")

    # Price freshness indicator — reads the same epoch the 🔄 button writes
    import time as _pf_t
    _pf_ep = st.session_state.get("mp_last_refresh_epoch")
    if _pf_ep:
        _pf_age_s = _pf_t.time() - _pf_ep
        if _pf_age_s < 60:
            _pf_label = "just now"
        elif _pf_age_s < 3600:
            _pf_label = f"{int(_pf_age_s // 60)} min ago"
        else:
            _pf_label = "> 60 min ago"
        if _pf_age_s > 3600:
            st.caption(
                f"⚠️ Prices last refreshed {_pf_label} — market values may be "
                f"outdated. Tap 🔄 in the sidebar to update."
            )
        else:
            st.caption(f"Prices refreshed {_pf_label}.")
    else:
        st.caption(
            "⚠️ No price refresh on record — tap 🔄 in the sidebar to fetch "
            "current prices. Values shown use last-saved prices."
        )

    _cur_val   = val.total_portfolio_value_base
    _mv_base   = val.holdings_value_base
    _cash_base = val.cash_value_base
    _cost_base = val.total_cost_basis_base

    # ── Money-weighted return ───────────────────────────────────────────────
    st.subheader("Money-Weighted Return")
    _perf = compute_performance(holdings, txns, ledger, _cur_val, base_ccy, _fxu)
    _p1, _p2, _p3, _p4 = st.columns(4)
    _p1.metric("Current Value",     _fmt_money(_cur_val, base_ccy))
    _p2.metric("Net Contributions", _fmt_money(_perf.net_contributions_base, base_ccy))
    _p3.metric(
        "Growth",
        _fmt_money(_perf.growth_base, base_ccy),
        _fmt_pct(_perf.growth_pct) if _perf.growth_pct is not None else None,
    )
    _p4.metric(
        "Annualized (XIRR)",
        _fmt_pct(_perf.xirr_pct) if _perf.xirr_pct is not None else "—",
        help="Money-weighted annualized return. Approximate — historical FX is "
             "converted at current rates.",
    )
    for _n in _perf.notes:
        st.caption("ℹ️ " + _n)

    st.divider()

    # ── Dividend income ─────────────────────────────────────────────────────
    st.subheader("Dividend Income")
    _inc = dividend_summary(
        txns, base_ccy, _fxu,
        cost_basis_base=_cost_base, market_value_base=_mv_base,
    )
    if _inc.n_payments == 0:
        st.caption("No dividend settlements recorded yet.")
    else:
        _d1, _d2, _d3, _d4 = st.columns(4)
        _d1.metric("Lifetime",      _fmt_money(_inc.total_base, base_ccy))
        _d2.metric("Year-to-Date",  _fmt_money(_inc.ytd_base,   base_ccy))
        _d3.metric("Trailing 12m",  _fmt_money(_inc.ttm_base,   base_ccy))
        _d4.metric(
            "Yield on Cost",
            _fmt_pct(_inc.yield_on_cost_pct, 2) if _inc.yield_on_cost_pct is not None else "—",
        )
        if _inc.by_ticker:
            st.dataframe(
                pd.DataFrame(
                    [{"Ticker": _k, f"Income ({base_ccy})": round(_v, 2)}
                     for _k, _v in sorted(_inc.by_ticker.items(), key=lambda x: -x[1])]
                ),
                hide_index=True, use_container_width=True,
            )
        for _n in _inc.notes:
            st.caption("ℹ️ " + _n)

    st.divider()

    # ── Zakat estimate ──────────────────────────────────────────────────────
    st.subheader("Zakat Estimate")
    _rate_lbl = st.radio(
        "Zakat year basis",
        ["Lunar (2.5%)", "Gregorian (2.5775%)"],
        horizontal=True, key="zakat_rate_choice",
    )
    _z_rate = RATE_GREGORIAN if _rate_lbl.startswith("Gregorian") else RATE_LUNAR
    _z = compute_zakat(_mv_base, _cash_base, 0.0, rate=_z_rate)
    _z_paid = zakat_paid_to_date(txns, base_ccy, _fxu)
    _z1, _z2, _z3 = st.columns(3)
    _z1.metric("Zakatable Base",          _fmt_money(_z.zakatable_base, base_ccy))
    _z2.metric(f"Zakat Due ({_z.rate_label})", _fmt_money(_z.zakat_due, base_ccy))
    _z3.metric(
        "Zakat Paid to Date", _fmt_money(_z_paid, base_ccy),
        help="Informational only — already deducted from your cash, never "
             "subtracted from the base again.",
    )
    st.caption("⚠️ " + _z.note)

    st.divider()

    # ── Realized gains (tax report) ─────────────────────────────────────────
    st.subheader("Realized Gains by Period")
    _period_lbl = st.radio(
        "Group by", ["Year", "Month"], horizontal=True, key="tax_period_choice",
    )
    _rep = realized_report(
        closed, base_ccy, _fxu,
        period="month" if _period_lbl == "Month" else "year",
    )
    if not _rep.rows:
        st.caption("No closed positions yet.")
    else:
        st.dataframe(
            pd.DataFrame([
                {
                    "Period": _r.period, "CCY": _r.currency,
                    "Proceeds": round(_r.proceeds, 2), "Cost": round(_r.cost, 2),
                    "Realized P&L": round(_r.realized_pnl, 2),
                    "Fees": round(_r.fees, 2), "Lots": _r.n_lots,
                } for _r in _rep.rows
            ]),
            hide_index=True, use_container_width=True,
        )
        st.caption(
            f"Native per-currency totals above are exact. Base-converted realized "
            f"P&L (approximate, current FX): **{_fmt_money(_rep.base_total_approx, base_ccy)}**"
        )
        for _n in _rep.notes:
            st.caption("ℹ️ " + _n)

    st.divider()

    # ── Data integrity (reconciliation, C3-lite) ────────────────────────────
    _rr = reconcile_holdings(holdings, txns)
    _rr_label = (
        "✅ Data Integrity — holdings reconcile with transactions"
        if _rr.n_error == 0 else
        f"⚠️ Data Integrity — {_rr.n_error} discrepancy(ies) need review"
    )
    with st.expander(_rr_label, expanded=_rr.n_error > 0):
        if not _rr.records:
            st.success("All holdings match their transaction history.")
        else:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Ticker": _r.ticker, "Stored Qty": round(_r.stored_qty, 4),
                        "Txn Qty": round(_r.txn_qty, 4), "Drift": round(_r.drift, 4),
                        "Severity": _r.severity, "Note": _r.message,
                    } for _r in _rr.records
                ]),
                hide_index=True, use_container_width=True,
            )
        st.caption(
            "Read-only check. Bousala never auto-edits quantities — investigate "
            "any discrepancy and correct it via a transaction."
        )


# ── Global header — brand (left) · KPIs (center) · controls (right) ──────────
def render_global_header() -> str:
    """
    Professional three-zone app bar rendered above all tabs.
    LEFT : compass SVG + بوصلة المستثمر (inline, ~48 px logo)
    CENTER: Net Worth · This Month trend · Invested · Refresh — horizontal flex
    RIGHT : CCY selector + 🔄 price refresh button
    Returns the selected base currency string.
    Sticky behaviour via CSS  :has(.bousala-appbar) on the parent stHorizontalBlock.
    """
    from portfolio import load_holdings
    from portfolio.accounts import load_accounts as _gh_accts
    from fx_rates import get_rates_for_holdings, refresh_fx_rates
    from portfolio.valuation import calculate_portfolio_valuation
    from portfolio.alt_investments import load_igi_investments as _gh_load_igi
    from portfolio.crowdfunding import load_cf_accounts as _gh_load_cf
    from portfolio.fixed_assets import load_fixed_assets as _gh_load_fa
    from portfolio.liabilities import (
        load_liabilities as _gh_load_libs,
        compute_liabilities_base as _gh_clib,
    )
    from portfolio.net_worth import (
        compute_extra_assets_base,
        record_nw_snapshot_if_needed,
        get_monthly_trend,
    )

    # ── Compass SVG — 48 × 48 px, two-tone needle, $ centre ──────────────
    _SVG = (
        '<svg viewBox="0 0 32 32" width="48" height="48"'
        ' xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0">'
        '<circle cx="16" cy="16" r="13.5"'
        ' fill="none" stroke="#334155" stroke-width="1.3"/>'
        # Cardinal tick marks (N bold, others thin)
        '<line x1="16" y1="3.2" x2="16" y2="7"'
        ' stroke="#334155" stroke-width="2" stroke-linecap="round"/>'
        '<line x1="16" y1="25" x2="16" y2="28.8"'
        ' stroke="#334155" stroke-width="1" stroke-linecap="round"/>'
        '<line x1="3.2" y1="16" x2="7" y2="16"'
        ' stroke="#334155" stroke-width="1" stroke-linecap="round"/>'
        '<line x1="25" y1="16" x2="28.8" y2="16"'
        ' stroke="#334155" stroke-width="1" stroke-linecap="round"/>'
        # Needle: north = sky-blue, south = rose
        '<polygon points="16,5.5 18.5,15.5 16,18.8 13.5,15.5" fill="#0ea5e9"/>'
        '<polygon points="16,26.5 18.5,16.5 16,13.2 13.5,16.5" fill="#f43f5e"/>'
        # Centre hub + $ symbol
        '<circle cx="16" cy="16" r="4"'
        ' fill="white" stroke="#334155" stroke-width="0.8"/>'
        '<text x="16" y="16" font-size="5.2" font-family="Arial,sans-serif"'
        ' font-weight="bold" text-anchor="middle"'
        ' dominant-baseline="central" fill="#334155">$</text>'
        '</svg>'
    )

    # Brand block — carries marker class for sticky CSS selector
    _BRAND = (
        f'<div class="bousala-appbar">'
        f'  {_SVG}'
        f'  <div>'
        f'    <div class="ba-name">بوصلة المستثمر</div>'
        f'  </div>'
        f'</div>'
    )

    # ── Three-zone columns ─────────────────────────────────────────────────
    # LEFT brand | CENTER KPIs (most space) | RIGHT controls
    _cL, _cM, _cR = st.columns([1.1, 5.5, 1.2])

    # LEFT — brand (pure HTML, no Streamlit widget)
    with _cL:
        st.markdown(_BRAND, unsafe_allow_html=True)

    # RIGHT — compact inline controls: currency selector · price refresh
    with _cR:
        _hc1, _hc2 = st.columns([3, 1])
        with _hc1:
            _selected_ccy = st.selectbox(
                "Currency",
                options=["SAR", "USD", "EUR", "GBP"],
                key="global_base_ccy",
                label_visibility="collapsed",
                help=(
                    "Base currency for portfolio totals and KPIs. "
                    "Each holding's own currency is shown in the CCY column."
                ),
            )
            # Safety guard: stale session state from an older app version
            if _selected_ccy == "— Native —":
                _selected_ccy = "SAR"
            _base_ccy = _selected_ccy
            st.session_state["_native_mode"] = False   # legacy flag — retired
        with _hc2:
            _do_refresh_prices = st.button(
                "🔄",
                key="global_refresh_prices_btn",
                use_container_width=True,
                help="Refresh live prices for all holdings.",
            )

    # ── Load all asset classes ─────────────────────────────────────────────
    _gh_hld  = load_holdings()
    _gh_igi  = _gh_load_igi()
    _gh_cf   = _gh_load_cf()
    _gh_fa   = _gh_load_fa()
    _gh_libs = _gh_load_libs()

    # Collect currencies from ALL sources so one FX call covers everything
    _gh_ccys = list({
        *({getattr(h, "currency", "USD") for h in _gh_hld.values()} if _gh_hld else set()),
        *(inv.currency for inv in _gh_igi.values() if inv.status != "Closed"),
        *(acct.currency for acct in _gh_cf.values() if acct.status == "Active"),
        *(a.currency for a in _gh_fa.values() if a.status != "Sold"),
        *(lib.currency for lib in _gh_libs.values() if lib.status == "Active"),
    })
    _gh_fx  = get_rates_for_holdings(_gh_ccys, _base_ccy) if _gh_ccys else {}
    _gh_val = calculate_portfolio_valuation(_gh_hld, _gh_accts(), _base_ccy, fx_rates=_gh_fx)
    _gh_ref = st.session_state.get("mp_last_refresh") or "—"

    # ── Net worth = portfolio + alt investments + CF + fixed assets − liabilities
    _gh_extra = compute_extra_assets_base(
        _gh_igi, _gh_cf, _base_ccy, _gh_val.fx_rates_used,
        fixed_assets=_gh_fa,
    )
    _gh_liab  = _gh_clib(_gh_libs, _base_ccy, _gh_val.fx_rates_used)
    _gh_nw    = _gh_val.total_portfolio_value_base + _gh_extra - _gh_liab

    # ── Monthly trend ──────────────────────────────────────────────────────
    _gh_snaps          = record_nw_snapshot_if_needed(_gh_nw, _base_ccy)
    _gh_delta_abs, _gh_delta_pct = get_monthly_trend(_gh_nw, _base_ccy, _gh_snaps)

    # ── Invested (holdings MV only) P&L colour ─────────────────────────────
    _gh_inv_pc = "#22c55e" if _gh_val.unrealized_pnl_base >= 0 else "#ef4444"
    _gh_inv_ps = "+" if _gh_val.unrealized_pnl_base >= 0 else ""

    # ── Trend colour & symbol ──────────────────────────────────────────────
    _gh_tc = (
        "#22c55e" if (_gh_delta_abs or 0) >= 0 else "#ef4444"
    )

    def _gh_fmt(v: float) -> str:
        av = abs(v)
        if av >= 1_000_000:
            return f"{v / 1_000_000:.2f}M"
        if av >= 10_000:
            return f"{v / 1_000:.0f}K"
        return f"{v:,.2f}"

    _has_any = bool(_gh_hld) or bool(_gh_igi) or bool(_gh_cf) or bool(_gh_fa) or bool(_gh_libs) or _gh_val.cash_value_base > 0

    # ── Stale-data flags — computed before KPI HTML so badges render inline ───
    # On first render after restart, restore epoch from the persisted file
    # so the 60-min freshness window survives app restarts.
    _prices_stale = False
    if _has_any:
        if not st.session_state.get("mp_last_refresh_epoch"):
            from market_prices import load_refresh_ts as _lrts, load_price_cache as _lpc
            _persisted_ep = _lrts()
            if _persisted_ep:
                st.session_state["mp_last_refresh_epoch"] = _persisted_ep
                if not st.session_state.get("mp_last_refresh"):
                    from datetime import datetime as _dt2
                    # Always label as UTC so the display is unambiguous regardless of server TZ
                    st.session_state["mp_last_refresh"] = (
                        _dt2.utcfromtimestamp(_persisted_ep).strftime("%H:%M") + " UTC"
                    )
                _gh_ref = st.session_state.get("mp_last_refresh") or "—"
                # Restore persisted price cache so daily-Δ shows on cold start.
                # Only load when within the 60-min freshness window — stale data
                # would show a misleading delta badge.
                import time as _t_cold
                if (_t_cold.time() - _persisted_ep) < 3600:
                    if not st.session_state.get("mp_price_cache"):
                        _cold_cache = _lpc()
                        if _cold_cache:
                            st.session_state["mp_price_cache"] = _cold_cache
        import time as _t_stale
        _ref_ep = st.session_state.get("mp_last_refresh_epoch")
        _prices_stale = (not _ref_ep) or (_t_stale.time() - _ref_ep > 3600)

    # ── Inline badge helper (price only — FX freshness is user-controlled) ────
    _PRICE_BADGE = (
        '<span title="Prices not refreshed in the last hour — showing last saved values. '
        'Tap 🔄 to update." '
        'style="font-size:0.75em;cursor:default;margin-left:3px;">⚠️</span>'
        if _prices_stale else ""
    )

    # ── Relative-time label for the Refresh KPI tile (timezone-agnostic) ──────
    # Using age-based label avoids server-TZ vs user-TZ mismatch entirely.
    import time as _t_rel
    _ref_ep_rel = st.session_state.get("mp_last_refresh_epoch")
    if _ref_ep_rel:
        _age_s = _t_rel.time() - _ref_ep_rel
        if _age_s < 60:
            _gh_ref_display = "just now"
        elif _age_s < 3600:
            _gh_ref_display = f"{int(_age_s // 60)} min ago"
        else:
            _gh_ref_display = "> 60 min ago"
    else:
        _gh_ref_display = _gh_ref  # "—" when never refreshed

    # CENTER — horizontal KPI flex row (all four metrics in one HTML block)
    with _cM:
        if _has_any:
            # ── Monthly trend KPI ─────────────────────────────────────────
            if _gh_delta_pct is not None:
                _trend_arrow = "▲" if (_gh_delta_abs or 0) >= 0 else "▼"
                _trend_sign  = "+" if (_gh_delta_abs or 0) >= 0 else ""
                _trend_html  = (
                    f'<span style="color:{_gh_tc};font-size:0.85em">'
                    f'{_trend_arrow} {_trend_sign}{_gh_delta_pct:.1f}%'
                    f'</span>'
                    f'<span style="color:#94a3b8;font-size:0.72em;margin-left:4px">'
                    f'({_trend_sign}{_gh_fmt(_gh_delta_abs or 0)})'
                    f'</span>'
                )
            else:
                _trend_html = '<span style="color:#94a3b8;font-size:0.82em">tracking…</span>'

            # ── Invested (holdings MV) label ──────────────────────────────
            _pnl_pct_html = (
                f'<span class="gh-pct">'
                f'({_gh_inv_ps}{_gh_val.unrealized_pnl_pct:.1f}%)'
                f'</span>'
            )

            _gh_liab_html = (
                f'<div style="color:#ef4444;font-size:0.65em;margin-top:1px">'
                f'−{_gh_fmt(_gh_liab)} liabilities</div>'
                if _gh_liab > 0 else ""
            )
            st.markdown(
                f'<div class="gh-kpi-row">'
                # Net Worth — ⚠️ when FX is stale
                f'  <div class="gh-kpi">'
                f'    <div class="gh-lbl">Net Worth ({_base_ccy})</div>'
                f'    <div class="gh-val-big">{_gh_fmt(_gh_nw)}</div>'
                f'    {_gh_liab_html}'
                f'  </div>'
                # This Month
                f'  <div class="gh-kpi">'
                f'    <div class="gh-lbl">This Month</div>'
                f'    <div class="gh-val-med">{_trend_html}</div>'
                f'  </div>'
                # Invested — ⚠️ when prices are stale
                f'  <div class="gh-kpi">'
                f'    <div class="gh-lbl">Invested ({_base_ccy})</div>'
                f'    <div class="gh-val-sm" style="color:{_gh_inv_pc}">'
                f'      {_gh_inv_ps}{_gh_fmt(_gh_val.holdings_value_base)}{_PRICE_BADGE} {_pnl_pct_html}'
                f'    </div>'
                f'  </div>'
                # Last refresh
                f'  <div class="gh-kpi">'
                f'    <div class="gh-lbl">Refresh</div>'
                f'    <div class="gh-val-xs">{_gh_ref_display}</div>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="gh-kpi-row">'
                f'  <div class="gh-kpi">'
                f'    <div class="gh-lbl">Net Worth ({_base_ccy})</div>'
                f'    <div class="gh-val-xs" style="color:#94a3b8;margin-top:4px">'
                f'      No assets yet — add one below</div>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Handle actions from header / Settings sidebar ─────────────────────────
    # FX refresh — triggered from the 💱 button in Settings sidebar
    if st.session_state.get("sb_refresh_fx_btn") and _gh_hld:
        with st.spinner("Fetching rates…"):
            refresh_fx_rates(_gh_ccys, _base_ccy)
        st.toast("FX rates updated", icon="💱")
        st.rerun()

    # Price refresh
    if _do_refresh_prices:
        with st.spinner("Fetching prices…"):
            _n_ok = _run_price_refresh(force=True)
        st.toast(f"Prices updated for {_n_ok} holding(s)", icon="✅" if _n_ok else "⚠️")
        st.rerun()

    # Auto-refresh timer (runs every render regardless of active tab)
    _mp_auto = st.session_state.get("mp_auto_on", False)
    if _mp_auto:
        import time as _t_ar
        _ivl_map = {"1 minute": 60, "5 minutes": 300, "15 minutes": 900}
        _ivl_s   = _ivl_map.get(st.session_state.get("mp_interval", "5 minutes"), 300)
        _ep_ar   = st.session_state.get("mp_last_refresh_epoch", 0.0)
        if _t_ar.time() - _ep_ar >= _ivl_s:
            _run_price_refresh(force=True)
            st.rerun()

    return _base_ccy


# ── Developer Mode: Pre-Release Test Runner ──────────────────────────────────

def render_test_runner_tab() -> None:
    """Developer Mode — Pre-Release Test Runner tab."""
    import io
    import pandas as pd

    if not st.session_state.get("dev_mode", False):
        st.info(
            "🔒 **Test Runner is only available in Developer Mode.**  \n"
            "Enable **🔧 Developer Mode** in the sidebar to access pre-release testing.",
            icon="🔧",
        )
        return

    st.header("🧪 Pre-Release Test Runner")
    st.caption(
        "Executes automated financial integrity, currency conversion, valuation "
        "consistency, and data validation tests against the live calculation engines "
        "using **synthetic sandbox data only** — never reads or writes real portfolio files."
    )

    col_btn, col_ts = st.columns([2, 3])
    with col_btn:
        run_clicked = st.button(
            "▶️ Run Pre-Release Tests",
            type="primary",
            key="run_tests_btn",
            use_container_width=True,
        )

    if run_clicked:
        import sys, os
        _ea = os.path.join(os.path.dirname(__file__))
        if _ea not in sys.path:
            sys.path.insert(0, _ea)
        with st.spinner("Running tests across 14 categories…"):
            from dev_test_runner import run_all_tests
            report = run_all_tests()
        st.session_state["_test_report"] = report
        from report_store import save_test_report, save_punch_list_report
        save_test_report(report)
        save_punch_list_report(report)

    # ── Local helper: render persisted report history from disk ──────────────
    def _show_history(key_prefix: str = "") -> None:
        from report_store import (
            list_test_reports, list_punch_list_reports,
            read_bytes, label_from_path,
        )
        st.divider()
        st.subheader("📁 Report History")
        st.caption(
            "Latest 3 reports of each type are kept automatically. "
            "Oldest file is removed when a 4th is generated."
        )
        _h1, _h2 = st.columns(2)
        with _h1:
            st.markdown("**🧪 Test Runner Reports**")
            _tr_files = list(reversed(list_test_reports()))
            if _tr_files:
                for _idx, _fp in enumerate(_tr_files):
                    _lbl = label_from_path(_fp)
                    st.download_button(
                        label=f"⬇️ #{_idx + 1} — {_lbl}",
                        data=read_bytes(_fp),
                        file_name=f"{_lbl.replace(' ', '_').replace(':', '-')}_test_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"{key_prefix}dl_tr_hist_{_idx}",
                        use_container_width=True,
                    )
            else:
                st.info("No saved test reports yet. Run tests to generate one.", icon="📭")
        with _h2:
            st.markdown("**🔴 Punch List Reports**")
            _pl_files = list(reversed(list_punch_list_reports()))
            if _pl_files:
                for _idx, _fp in enumerate(_pl_files):
                    _lbl = label_from_path(_fp)
                    st.download_button(
                        label=f"⬇️ #{_idx + 1} — {_lbl}",
                        data=read_bytes(_fp),
                        file_name=f"{_lbl.replace(' ', '_').replace(':', '-')}_punch_list.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"{key_prefix}dl_pl_hist_{_idx}",
                        use_container_width=True,
                    )
            else:
                st.info("No saved punch list reports yet. Run tests to generate one.", icon="📭")

    report = st.session_state.get("_test_report")

    if not report:
        st.info("Click **▶️ Run Pre-Release Tests** to begin.", icon="🧪")
        _show_history()   # persisted files survive session/mode changes
        return

    with col_ts:
        st.caption(f"Last run: {report.timestamp[:19].replace('T', ' ')}")

    # ── Release Readiness Summary ─────────────────────────────────────────────
    st.divider()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Tests",        report.total)
    m2.metric("✅ Passed",           report.passed)
    m3.metric(
        "❌ Failed",
        report.failed,
        delta=f"-{report.failed}" if report.failed else None,
        delta_color="inverse" if report.failed else "off",
    )
    m4.metric("🚨 Release Blockers", report.release_blockers)
    with m5:
        if report.release_ready:
            st.success("✅ Release Ready", icon="🚀")
        else:
            st.error("❌ Not Release Ready", icon="🚨")

    # ── Severity legend ───────────────────────────────────────────────────────
    with st.expander("Severity guide", expanded=False):
        st.markdown(
            "| Code | Meaning |\n"
            "|------|---------|\n"
            "| **P0** | Data integrity issue — Release Blocker |\n"
            "| **P1** | Workflow issue |\n"
            "| **P2** | Usability issue |\n"
            "| **P3** | Cosmetic issue |"
        )

    # ── Test Results Table ────────────────────────────────────────────────────
    st.divider()
    st.subheader("📋 Test Results")

    _status_filter = st.selectbox(
        "Filter by status",
        ["All", "FAIL / ERROR", "PASS"],
        key="test_filter_sel",
    )

    _STATUS_EMOJI = {"PASS": "✅", "FAIL": "❌", "ERROR": "⚠️"}

    rows = []
    for r in report.results:
        if _status_filter == "FAIL / ERROR" and r.status not in ("FAIL", "ERROR"):
            continue
        if _status_filter == "PASS" and r.status != "PASS":
            continue
        rows.append({
            "ID":              r.test_id,
            "Test Name":       r.test_name,
            "Category":        r.category,
            "Status":          f"{_STATUS_EMOJI.get(r.status, '')} {r.status}",
            "Expected":        r.expected,
            "Actual":          r.actual,
            "Module":          r.module,
            "Severity":        r.severity,
            "Blocker":         "🚨 Yes" if r.is_release_blocker else "No",
        })

    if rows:
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Status":   st.column_config.TextColumn("Status",   width="small"),
                "Severity": st.column_config.TextColumn("Severity", width="small"),
                "Blocker":  st.column_config.TextColumn("Blocker",  width="small"),
            },
        )
    else:
        st.info("No results match the selected filter.")

    # ── Punch List ────────────────────────────────────────────────────────────
    st.divider()
    if report.punch_list:
        st.subheader(f"🔴 Punch List — {len(report.punch_list)} open item(s)")
        for item in report.punch_list:
            with st.expander(f"{item.item_id} · {item.bug_title}", expanded=False):
                _c1, _c2 = st.columns(2)
                with _c1:
                    st.markdown(f"**Status:** `{item.status}`")
                    st.markdown(f"**Severity:** `{item.severity}`")
                with _c2:
                    st.markdown(f"**Expected:** {item.expected}")
                    st.markdown(f"**Actual:** {item.actual}")
                st.markdown(f"**Description:**  \n{item.description}")
                st.markdown(f"**Reproduction Steps:**")
                st.code(item.repro_steps, language=None)
    else:
        st.success("🎉 All tests passed — punch list is empty.", icon="✅")

    # ── Export ────────────────────────────────────────────────────────────────
    st.divider()
    _dl1, _dl2 = st.columns(2)

    with _dl1:
        _rpt_csv = io.StringIO()
        pd.DataFrame([{
            "Test ID":        r.test_id,
            "Test Name":      r.test_name,
            "Category":       r.category,
            "Status":         r.status,
            "Expected":       r.expected,
            "Actual":         r.actual,
            "Module":         r.module,
            "Severity":       r.severity,
            "Release Blocker": "Yes" if r.is_release_blocker else "No",
        } for r in report.results]).to_csv(_rpt_csv, index=False)
        st.download_button(
            "⬇️ Export Test Report (CSV)",
            data=_rpt_csv.getvalue(),
            file_name=f"test_report_{report.timestamp[:10]}.csv",
            mime="text/csv",
            key="dl_test_report_csv",
            use_container_width=True,
        )

    with _dl2:
        if report.punch_list:
            _pl_csv = io.StringIO()
            pd.DataFrame([{
                "Item ID":    p.item_id,
                "Bug Title":  p.bug_title,
                "Severity":   p.severity,
                "Status":     p.status,
                "Expected":   p.expected,
                "Actual":     p.actual,
                "Description": p.description,
                "Repro Steps": p.repro_steps,
            } for p in report.punch_list]).to_csv(_pl_csv, index=False)
            st.download_button(
                "⬇️ Export Punch List (CSV)",
                data=_pl_csv.getvalue(),
                file_name=f"punch_list_{report.timestamp[:10]}.csv",
                mime="text/csv",
                key="dl_punch_list_csv",
                use_container_width=True,
            )
        else:
            st.button("⬇️ Export Punch List (CSV)", disabled=True,
                      key="dl_punch_list_empty", use_container_width=True)

    _show_history()


# ── Alternative Investments Tab ───────────────────────────────────────────────

def render_alt_investments_tab() -> None:
    """Alternative Investments — Investment Grade Income and Crowdfunding."""
    from portfolio.alt_investments import (
        SHARIA_STRUCTURES, SHARIA_COMPLIANCE_STATUSES,
        PROFIT_PAYMENT_STRUCTURES, LIQUIDITY_TYPES, IGI_STATUSES,
        MATURITY_INSTRUCTIONS, IGI_TRANSACTION_TYPES,
        load_igi_investments, load_igi_transactions,
        add_igi_investment, edit_igi_investment, delete_igi_investment,
        record_igi_transaction, edit_igi_transaction,
        process_maturity, process_early_withdrawal,
        compute_igi_metrics,
    )
    from portfolio.crowdfunding import (
        CROWDFUNDING_TYPES, CF_STATUSES, CF_TRANSACTION_TYPES,
        load_cf_accounts, load_cf_transactions, load_cf_snapshots,
        add_cf_account, edit_cf_account,
        record_cf_transaction, add_cf_snapshot,
        compute_cf_metrics, compute_cf_reconciliation,
    )
    from portfolio import CURRENCIES
    from datetime import date
    import pandas as pd

    st.header("🏦 Alternative Investments")
    st.caption(
        "Track Investment Grade Income (Sukuk, deposits, savings accounts) "
        "and Crowdfunding platform accounts — without modifying the Holdings engine."
    )

    _alt_type = st.pills(
        "Investment Type",
        ["Investment Grade Income", "Crowdfunding"],
        default="Investment Grade Income",
        label_visibility="collapsed",
        key="alt_inv_type",
    )
    st.divider()

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION A — INVESTMENT GRADE INCOME
    # ═══════════════════════════════════════════════════════════════════════
    if _alt_type == "Investment Grade Income":

        # ── Dialogs ───────────────────────────────────────────────────────

        @st.dialog("➕ Add Investment Grade Income")
        def _dlg_igi_add():
            _ai1, _ai2 = st.columns(2)
            with _ai1:
                _n  = st.text_input("Investment Name *", key="igi_add_name")
                _in = st.text_input("Institution *", key="igi_add_inst")
                _cur = st.selectbox("Currency", CURRENCIES,
                                    index=CURRENCIES.index("SAR") if "SAR" in CURRENCIES else 0,
                                    key="igi_add_ccy")
                _pa = st.number_input("Principal Amount *", min_value=0.01, step=100.0, format="%.2f", key="igi_add_pa")
                _cv = st.number_input("Current Value", min_value=0.0, step=100.0, format="%.2f", key="igi_add_cv")
            with _ai2:
                _sd  = st.date_input("Start Date", value=date.today(), key="igi_add_sd")
                _md  = st.date_input("Maturity Date", value=date.today(), key="igi_add_md")
                _yld = st.number_input("Expected Yield %", min_value=0.0, max_value=100.0, step=0.1, format="%.2f", key="igi_add_yld")
                _pps = st.selectbox("Profit Payment Structure", PROFIT_PAYMENT_STRUCTURES, key="igi_add_pps")
                _liq = st.selectbox("Liquidity Type", LIQUIDITY_TYPES, key="igi_add_liq")
            _mi  = st.selectbox("Maturity Instruction", MATURITY_INSTRUCTIONS, key="igi_add_mi")
            _stat = st.selectbox("Status", IGI_STATUSES[:2], key="igi_add_stat")
            with st.expander("Sharia Metadata (optional)"):
                _sstr = st.selectbox("Sharia Structure", SHARIA_STRUCTURES, key="igi_add_sstr")
                _sstat = st.selectbox("Sharia Compliance Status", SHARIA_COMPLIANCE_STATUSES,
                                      index=SHARIA_COMPLIANCE_STATUSES.index("Not Applicable"),
                                      key="igi_add_sstat")
                _snotes = st.text_area("Sharia Notes", key="igi_add_snotes", max_chars=300)
            _notes = st.text_area("Notes", key="igi_add_notes", max_chars=500)
            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button("💾 Save", type="primary", use_container_width=True, key="igi_add_save"):
                    _inv, _err = add_igi_investment(
                        investment_name=_n, institution=_in, currency=_cur,
                        principal_amount=_pa, current_value=_cv or _pa,
                        start_date=_sd.isoformat(), maturity_date=_md.isoformat(),
                        expected_yield_pct=_yld, profit_payment_structure=_pps,
                        liquidity_type=_liq, maturity_instruction=_mi,
                        notes=_notes, sharia_structure=_sstr,
                        sharia_status=_sstat, sharia_notes=_snotes, status=_stat,
                    )
                    if _err:
                        st.error(_err)
                    else:
                        st.toast(f"Investment added: {_inv.investment_name}", icon="✅")
                        st.rerun()
            with _b2:
                if st.button("Cancel", use_container_width=True, key="igi_add_cancel"):
                    st.rerun()

        @st.dialog("✏️ Edit Investment")
        def _dlg_igi_edit(inv):
            _ei1, _ei2 = st.columns(2)
            with _ei1:
                _n  = st.text_input("Investment Name", value=inv.investment_name, key=f"igi_e_n_{inv.investment_id}")
                _in = st.text_input("Institution", value=inv.institution, key=f"igi_e_in_{inv.investment_id}")
                _pa = st.number_input("Principal Amount", value=float(inv.principal_amount), min_value=0.01, step=100.0, format="%.2f", key=f"igi_e_pa_{inv.investment_id}")
                _cv = st.number_input("Current Value", value=float(inv.current_value), min_value=0.0, step=100.0, format="%.2f", key=f"igi_e_cv_{inv.investment_id}")
                _yld = st.number_input("Expected Yield %", value=float(inv.expected_yield_pct), min_value=0.0, max_value=100.0, step=0.1, format="%.2f", key=f"igi_e_yld_{inv.investment_id}")
            with _ei2:
                _md  = st.date_input("Maturity Date", value=date.fromisoformat(inv.maturity_date) if inv.maturity_date else date.today(), key=f"igi_e_md_{inv.investment_id}")
                _pps = st.selectbox("Profit Payment Structure", PROFIT_PAYMENT_STRUCTURES,
                                    index=PROFIT_PAYMENT_STRUCTURES.index(inv.profit_payment_structure) if inv.profit_payment_structure in PROFIT_PAYMENT_STRUCTURES else 0,
                                    key=f"igi_e_pps_{inv.investment_id}")
                _liq = st.selectbox("Liquidity Type", LIQUIDITY_TYPES,
                                    index=LIQUIDITY_TYPES.index(inv.liquidity_type) if inv.liquidity_type in LIQUIDITY_TYPES else 0,
                                    key=f"igi_e_liq_{inv.investment_id}")
                _mi  = st.selectbox("Maturity Instruction", MATURITY_INSTRUCTIONS,
                                    index=MATURITY_INSTRUCTIONS.index(inv.maturity_instruction) if inv.maturity_instruction in MATURITY_INSTRUCTIONS else 0,
                                    key=f"igi_e_mi_{inv.investment_id}")
            _notes = st.text_area("Notes", value=inv.notes, max_chars=500, key=f"igi_e_notes_{inv.investment_id}")
            with st.expander("Sharia Metadata"):
                _sstr  = st.selectbox("Structure", SHARIA_STRUCTURES,
                                      index=SHARIA_STRUCTURES.index(inv.sharia_structure) if inv.sharia_structure in SHARIA_STRUCTURES else 0,
                                      key=f"igi_e_sstr_{inv.investment_id}")
                _sstat = st.selectbox("Compliance Status", SHARIA_COMPLIANCE_STATUSES,
                                      index=SHARIA_COMPLIANCE_STATUSES.index(inv.sharia_status) if inv.sharia_status in SHARIA_COMPLIANCE_STATUSES else 0,
                                      key=f"igi_e_sstat_{inv.investment_id}")
                _snotes = st.text_area("Sharia Notes", value=inv.sharia_notes, max_chars=300, key=f"igi_e_snotes_{inv.investment_id}")
            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button("💾 Save", type="primary", use_container_width=True, key=f"igi_e_save_{inv.investment_id}"):
                    _, _err = edit_igi_investment(
                        inv.investment_id,
                        investment_name=_n, institution=_in,
                        principal_amount=_pa, current_value=_cv,
                        expected_yield_pct=_yld, maturity_date=_md.isoformat(),
                        profit_payment_structure=_pps, liquidity_type=_liq,
                        maturity_instruction=_mi, notes=_notes,
                        sharia_structure=_sstr, sharia_status=_sstat, sharia_notes=_snotes,
                    )
                    if _err:
                        st.error(_err)
                    else:
                        st.toast("Investment updated", icon="💾")
                        st.rerun()
            with _b2:
                if st.button("Cancel", use_container_width=True, key=f"igi_e_cancel_{inv.investment_id}"):
                    st.rerun()

        @st.dialog("🗑️ Delete Investment")
        def _dlg_igi_del_inv(inv):
            st.warning(
                f"Permanently delete **{inv.investment_name}**"
                f" ({inv.institution})?\n\n"
                "All associated transactions will also be removed. "
                "This cannot be undone.",
                icon="⚠️",
            )
            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button(
                    "🗑️ Confirm Delete", type="primary",
                    use_container_width=True,
                    key=f"igi_del_inv_ok_{inv.investment_id}",
                ):
                    _ok, _err = delete_igi_investment(inv.investment_id)
                    if _err:
                        st.error(_err)
                    else:
                        st.toast(f"'{inv.investment_name}' deleted", icon="🗑️")
                        st.rerun()
            with _b2:
                if st.button(
                    "Cancel", use_container_width=True,
                    key=f"igi_del_inv_cancel_{inv.investment_id}",
                ):
                    st.rerun()

        @st.dialog("💰 Add Transaction")
        def _dlg_igi_txn(inv):
            st.caption(f"**{inv.investment_name}** · {inv.institution} · {inv.currency}")
            _t1, _t2, _t3 = st.columns(3)
            with _t1:
                _tt  = st.selectbox("Type", IGI_TRANSACTION_TYPES, key=f"igi_t_type_{inv.investment_id}")
            with _t2:
                _amt = st.number_input("Amount", min_value=0.01, step=100.0, format="%.2f", key=f"igi_t_amt_{inv.investment_id}")
            with _t3:
                _dt  = st.date_input("Date", value=date.today(), key=f"igi_t_dt_{inv.investment_id}")
            _notes = st.text_area("Notes *", key=f"igi_t_notes_{inv.investment_id}", max_chars=300)
            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button("💾 Save", type="primary", use_container_width=True, key=f"igi_t_save_{inv.investment_id}"):
                    _, _err = record_igi_transaction(
                        investment_id=inv.investment_id, txn_type=_tt,
                        amount=_amt, txn_date=_dt.isoformat(), notes=_notes,
                    )
                    if _err:
                        st.error(_err)
                    else:
                        st.toast(f"{_tt}: {_amt:,.2f} {inv.currency}", icon="✅")
                        st.rerun()
            with _b2:
                if st.button("Cancel", use_container_width=True, key=f"igi_t_cancel_{inv.investment_id}"):
                    st.rerun()

        @st.dialog("✏️ Edit Transaction")
        def _dlg_igi_edit_txn(txn):
            st.caption(
                f"Editing: **{txn.txn_type}** · {txn.date} · **{txn.amount:,.2f}**"
            )
            _et1, _et2, _et3 = st.columns(3)
            with _et1:
                _ett = st.selectbox(
                    "Type", IGI_TRANSACTION_TYPES,
                    index=IGI_TRANSACTION_TYPES.index(txn.txn_type)
                          if txn.txn_type in IGI_TRANSACTION_TYPES else 0,
                    key=f"igi_et_type_{txn.txn_id}",
                )
            with _et2:
                _eta = st.number_input(
                    "Amount", value=float(txn.amount), min_value=0.01,
                    step=100.0, format="%.2f", key=f"igi_et_amt_{txn.txn_id}",
                )
            with _et3:
                _etd = st.date_input(
                    "Date", value=date.fromisoformat(txn.date),
                    key=f"igi_et_dt_{txn.txn_id}",
                )
            _etn = st.text_area(
                "Notes", value=txn.notes, key=f"igi_et_notes_{txn.txn_id}",
                max_chars=300,
            )
            _eb1, _eb2 = st.columns(2)
            with _eb1:
                if st.button("💾 Save", type="primary", use_container_width=True,
                             key=f"igi_et_save_{txn.txn_id}"):
                    _, _err = edit_igi_transaction(
                        txn_id=txn.txn_id, txn_type=_ett, amount=_eta,
                        txn_date=_etd.isoformat(), notes=_etn,
                    )
                    if _err:
                        st.error(_err)
                    else:
                        st.toast("Transaction updated", icon="✅")
                        st.rerun()
            with _eb2:
                if st.button("Cancel", use_container_width=True,
                             key=f"igi_et_cancel_{txn.txn_id}"):
                    st.rerun()

        @st.dialog("🔔 Process Maturity")
        def _dlg_igi_maturity(inv):
            st.caption(
                f"**{inv.investment_name}** · Principal: **{inv.principal_amount:,.2f} {inv.currency}**  \n"
                "Enter the actual amount received. The system calculates the split."
            )
            _actual = st.number_input(
                "Actual Total Amount Received", min_value=0.0,
                value=float(inv.principal_amount), step=100.0, format="%.2f",
                key=f"igi_mat_act_{inv.investment_id}",
            )
            _act_date = st.date_input("Actual Maturity Date", value=date.today(), key=f"igi_mat_dt_{inv.investment_id}")
            _notes    = st.text_area("Notes (min. 10 characters)", key=f"igi_mat_notes_{inv.investment_id}", max_chars=500)
            st.caption(f"{len(_notes.strip())} / 10 minimum characters")

            # Show split preview
            from portfolio.alt_investments import compute_maturity_split
            _split = compute_maturity_split(inv.principal_amount, _actual)
            _final_action = inv.maturity_instruction
            if inv.maturity_instruction == "Manual Decision At Maturity":
                _final_action = st.selectbox(
                    "Final Action *",
                    [m for m in MATURITY_INSTRUCTIONS if m != "Manual Decision At Maturity"],
                    key=f"igi_mat_fa_{inv.investment_id}",
                )
            st.divider()
            st.markdown("**📊 Calculated Split**")
            _ms1, _ms2, _ms3 = st.columns(3)
            _ms1.metric("Principal Returned", f"{_split['principal_returned']:,.2f}")
            _ms2.metric("Profit Received",    f"{_split['profit_received']:,.2f}")
            _ms3.metric("Principal Loss",     f"{_split['principal_loss']:,.2f}")
            if _split["principal_loss"] > 0:
                st.warning("⚠️ Actual amount is less than principal — a loss will be recorded.", icon="⚠️")
            st.caption(f"Action: **{_final_action}**")

            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button("✅ Confirm Maturity", type="primary", use_container_width=True, key=f"igi_mat_save_{inv.investment_id}"):
                    _res, _err = process_maturity(
                        investment_id=inv.investment_id,
                        actual_total_received=_actual,
                        actual_maturity_date=_act_date.isoformat(),
                        notes=_notes,
                        final_action=_final_action if inv.maturity_instruction == "Manual Decision At Maturity" else None,
                    )
                    if _err:
                        st.error(_err)
                    else:
                        _child_msg = f" · New draft: {_res['child_investment_id']}" if _res.get("child_investment_id") else ""
                        st.toast(f"Maturity processed: {_res['action_taken']}{_child_msg}", icon="✅")
                        st.rerun()
            with _b2:
                if st.button("Cancel", use_container_width=True, key=f"igi_mat_cancel_{inv.investment_id}"):
                    st.rerun()

        @st.dialog("📤 Early Withdrawal")
        def _dlg_igi_withdraw(inv):
            st.caption(
                f"**{inv.investment_name}** · Principal: **{inv.principal_amount:,.2f} {inv.currency}**  \n"
                "Full early withdrawal only (MVP). Enter actual amount received after any penalties."
            )
            _wd   = st.date_input("Withdrawal Date", value=date.today(), key=f"igi_wd_dt_{inv.investment_id}")
            _tot  = st.number_input("Actual Total Amount Received", min_value=0.0,
                                    value=float(inv.principal_amount), step=100.0, format="%.2f",
                                    key=f"igi_wd_tot_{inv.investment_id}")
            _cost = st.number_input("Early Withdrawal Cost (penalty/fee)", min_value=0.0,
                                    step=10.0, format="%.2f", key=f"igi_wd_cost_{inv.investment_id}")
            _notes = st.text_area("Notes", key=f"igi_wd_notes_{inv.investment_id}", max_chars=500)

            from portfolio.alt_investments import compute_maturity_split
            _split = compute_maturity_split(inv.principal_amount, _tot)
            st.divider()
            _ws1, _ws2, _ws3 = st.columns(3)
            _ws1.metric("Principal Returned",    f"{_split['principal_returned']:,.2f}")
            _ws2.metric("Profit Received",       f"{_split['profit_received']:,.2f}")
            _ws3.metric("Withdrawal Cost",       f"{_cost:,.2f}")
            if _split["principal_loss"] > 0:
                st.warning(f"⚠️ Principal loss: {_split['principal_loss']:,.2f}", icon="⚠️")

            st.caption("⚠️ This action is permanent — the investment will be marked Closed.")
            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button("✅ Confirm Withdrawal", type="primary", use_container_width=True,
                             key=f"igi_wd_save_{inv.investment_id}"):
                    _res, _err = process_early_withdrawal(
                        investment_id=inv.investment_id, withdrawal_date=_wd.isoformat(),
                        actual_total=_tot, early_withdrawal_cost=_cost, notes=_notes or "Early withdrawal",
                    )
                    if _err:
                        st.error(_err)
                    else:
                        st.toast("Early withdrawal processed — investment closed", icon="✅")
                        st.rerun()
            with _b2:
                if st.button("Cancel", use_container_width=True, key=f"igi_wd_cancel_{inv.investment_id}"):
                    st.rerun()

        # ── Load data ─────────────────────────────────────────────────────
        _igi_investments = load_igi_investments()
        _igi_txns        = load_igi_transactions()

        # ── Display currency + FX rate (all IGI amounts are SAR) ──────────
        from fx_rates import get_rates_for_holdings as _igi_get_fx
        _igi_disp_ccy = st.session_state.get("global_base_ccy", "SAR")
        if _igi_disp_ccy != "SAR":
            _igi_fx_map = _igi_get_fx(["SAR"], _igi_disp_ccy)
            _igi_rate   = _igi_fx_map["SAR"].rate if "SAR" in _igi_fx_map else 1.0
        else:
            _igi_rate = 1.0

        # ── Summary metrics ────────────────────────────────────────────────
        _igi_all  = list(_igi_investments.values())
        _igi_open = [i for i in _igi_all if i.status not in ("Closed",)]
        _total_cv = sum(i.current_value for i in _igi_open)
        _total_pa = sum(i.principal_amount for i in _igi_open)
        _total_pr = sum(t.amount for t in _igi_txns if t.txn_type == "Profit Received")
        _maturity_due = [i for i in _igi_all if i.status == "Maturity Action Required"]

        _sm1, _sm2, _sm3, _sm4, _sm5 = st.columns(5)
        _sm1.metric("Total Investments",     len(_igi_all))
        _sm2.metric("Open",                  len(_igi_open))
        _sm3.metric(f"Total Principal (open) · {_igi_disp_ccy}", f"{_total_pa * _igi_rate:,.2f}")
        _sm4.metric(f"Total Current Value · {_igi_disp_ccy}",    f"{_total_cv * _igi_rate:,.2f}")
        _sm5.metric(f"Total Profit Received · {_igi_disp_ccy}",  f"{_total_pr * _igi_rate:,.2f}")

        # ── Yield summary — Tier 2 (portfolio-level projection) ───────────
        from datetime import date as _dt_cls
        _ys_active = {"Active", "Maturity Action Required"}
        _ys_proj   = 0.0
        _ys_acc    = 0.0
        _ys_recv   = 0.0
        _ys_wnum   = 0.0   # weighted-avg numerator  (principal × rate)
        _ys_wden   = 0.0   # weighted-avg denominator (principal)
        _ys_count  = 0

        for _si in _igi_all:
            if _si.status not in _ys_active:
                continue
            if not _si.start_date or not _si.maturity_date:
                continue
            _si_s = _dt_cls.fromisoformat(_si.start_date)
            _si_m = _dt_cls.fromisoformat(_si.maturity_date)
            _si_t = max(0, (_si_m - _si_s).days)
            if _si_t == 0:
                continue
            _si_proj = _si.principal_amount * (_si.expected_yield_pct / 100) * (_si_t / 365)
            _si_end  = min(_dt_cls.today(), _si_m)
            _si_ela  = max(0, (_si_end - _si_s).days)
            _si_acc  = _si.principal_amount * (_si.expected_yield_pct / 100) * (_si_ela / 365)
            _si_recv = sum(
                t.amount for t in _igi_txns
                if t.investment_id == _si.investment_id and t.txn_type == "Profit Received"
            )
            _ys_proj  += _si_proj
            _ys_acc   += _si_acc
            _ys_recv  += _si_recv
            _ys_wnum  += _si.principal_amount * _si.expected_yield_pct
            _ys_wden  += _si.principal_amount
            _ys_count += 1

        if _ys_count > 0:
            _ys_out  = round(_ys_proj - _ys_recv, 2)
            _ys_wavg = round(_ys_wnum / _ys_wden, 2) if _ys_wden > 0 else 0.0
            st.caption(
                "📈 **Yield Summary** — active investments · "
                "projected from expected rates · *informational only*"
            )
            _ts1, _ts2, _ts3, _ts4, _ts5 = st.columns(5)
            _ts1.metric(f"Projected Total · {_igi_disp_ccy}",  f"{_ys_proj * _igi_rate:,.2f}")
            _ts2.metric(f"Accrued to Date · {_igi_disp_ccy}", f"{_ys_acc * _igi_rate:,.2f}")
            _ts3.metric(
                f"Received · {_igi_disp_ccy}",
                f"{_ys_recv * _igi_rate:,.2f}",
                delta=(
                    f"{(_ys_recv - _ys_acc) * _igi_rate:+,.2f} vs accrued"
                    if _ys_acc > 0 else None
                ),
            )
            _ts4.metric(f"Outstanding · {_igi_disp_ccy}",     f"{_ys_out * _igi_rate:,.2f}")
            _ts5.metric("Wtd Avg Yield",    f"{_ys_wavg:.2f}%")

        if _maturity_due:
            st.warning(
                f"⏰ **{len(_maturity_due)} investment(s) require maturity action.** "
                "See 🔔 Process Maturity below.",
                icon="⏰",
            )

        # ── Build option lists + purge stale state ────────────────────────
        _igi_institutions = sorted({i.institution for i in _igi_all}) if _igi_all else []
        _igi_sharia_opts  = sorted({
            i.sharia_structure for i in _igi_all
            if i.sharia_structure and i.sharia_structure != "Not Specified"
        }) if _igi_all else []

        for _fk, _fvalid in [("igi_f_inst", _igi_institutions),
                              ("igi_f_sharia", _igi_sharia_opts)]:
            _stored = st.session_state.get(_fk)
            if _stored and not all(v in _fvalid for v in _stored):
                st.session_state.pop(_fk, None)

        # ── Read filter state BEFORE widgets (chart renders first) ─────────
        _f_inst     = st.session_state.get("igi_f_inst",   _igi_institutions)
        _f_sharia   = st.session_state.get("igi_f_sharia", _igi_sharia_opts)
        _f_mat_from = st.session_state.get("igi_f_mat_from")
        _f_mat_to   = st.session_state.get("igi_f_mat_to")

        # Apply all filters (AND logic)
        _filtered_igi = _igi_all
        if _f_inst and set(_f_inst) != set(_igi_institutions):
            _filtered_igi = [i for i in _filtered_igi if i.institution in _f_inst]
        if _f_sharia and set(_f_sharia) != set(_igi_sharia_opts):
            _filtered_igi = [i for i in _filtered_igi
                             if i.sharia_structure in _f_sharia]
        if _f_mat_from:
            _s = _f_mat_from.isoformat()
            _filtered_igi = [i for i in _filtered_igi
                             if i.maturity_date and i.maturity_date >= _s]
        if _f_mat_to:
            _e = _f_mat_to.isoformat()
            _filtered_igi = [i for i in _filtered_igi
                             if i.maturity_date and i.maturity_date <= _e]
        _filtered_igi = sorted(_filtered_igi, key=lambda x: (x.institution, x.start_date or ""))

        # ── Maturity Ladder — chart FIRST ──────────────────────────────────
        _ladder_inv = [i for i in _filtered_igi if i.status != "Closed" and i.maturity_date]
        if _ladder_inv:
            import plotly.graph_objects as go
            import plotly.express as px
            from collections import defaultdict

            _CALM = [
                "#4E8FA8",  # muted steel blue
                "#6A9E76",  # muted sage green
                "#B87A56",  # muted terracotta
                "#7B7BAB",  # muted slate purple
                "#A89B50",  # muted warm gold
                "#5A9E96",  # muted teal
                "#8A7060",  # muted brown
            ]

            # Monthly buckets by institution (thousands)
            _mdata: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
            for _li in _ladder_inv:
                _mdata[_li.maturity_date[:7]][_li.institution] += _li.principal_amount * _igi_rate / 1_000

            _months     = sorted(_mdata.keys())
            _inst_order = sorted({i.institution for i in _ladder_inv})
            _mon_totals = {m: sum(_mdata[m].values()) for m in _months}

            def _fmt_amount(v_thousands: float) -> str:
                """Format a value (stored in thousands) as a readable amount label."""
                v = v_thousands * 1_000
                if v >= 1_000_000:
                    return f"{v / 1_000_000:,.2f}M"
                rounded = round(v, -3)
                return f"{rounded:,.2f}"

            _ladder_fig = go.Figure()
            for _idx, _inst in enumerate(_inst_order):
                _clr    = _CALM[_idx % len(_CALM)]
                _vals_k = [_mdata[m].get(_inst, 0) for m in _months]
                _labels: list[str] = []
                _hovers: list[str] = []
                for _m, _v in zip(_months, _vals_k):
                    if _v > 0:
                        _labels.append(_fmt_amount(_v))
                        _hovers.append(f"{_v * 1_000:,.2f}")
                    else:
                        _labels.append("")
                        _hovers.append("")
                if any(v > 0 for v in _vals_k):
                    _ladder_fig.add_trace(go.Bar(
                        name=_inst,
                        x=_months,
                        y=_vals_k,
                        marker_color=_clr,
                        marker_line_width=0,
                        text=_labels,
                        textposition="inside",
                        insidetextanchor="middle",
                        textfont=dict(size=13, color="white"),
                        customdata=_hovers,
                        hovertemplate=(
                            "<b>%{x}</b><br>"
                            + _inst + ": %{customdata}"
                            + "<extra></extra>"
                        ),
                    ))

            _ladder_fig.update_layout(
                barmode="stack",
                dragmode="pan",
                height=280,
                bargap=0.35,
                margin=dict(l=40, r=10, t=10, b=50),
                legend=dict(
                    orientation="h",
                    yanchor="top", y=-0.15,
                    xanchor="left", x=0,
                    font=dict(size=11),
                ),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(
                    type="category",
                    tickfont=dict(size=11),
                ),
            )
            _ladder_fig.update_yaxes(
                showgrid=True,
                gridcolor="rgba(128,128,128,0.15)",
                ticksuffix=f"K {_igi_disp_ccy}",
                tickformat=",.0f",
                tickfont=dict(size=11),
            )
            st.caption(
                f"📅 **Maturity Ladder** — principal per month · {_igi_disp_ccy} · "
                "drag to pan · scroll to zoom · double-click to reset"
            )
            st.plotly_chart(
                _ladder_fig,
                use_container_width=True,
                config={"displayModeBar": False, "scrollZoom": True},
            )

        # ── Add button + filter expander (below chart) ─────────────────────
        _fab_c1, _fab_c2 = st.columns([5, 1])
        with _fab_c2:
            if st.button("➕ Add Investment", use_container_width=True,
                         type="primary", key="igi_open_add"):
                _dlg_igi_add()

        with st.expander("🔍 Filters", expanded=False):
            _fc1, _fc2, _fc3 = st.columns(3)
            with _fc1:
                st.multiselect(
                    "Institution", _igi_institutions,
                    default=st.session_state.get("igi_f_inst", _igi_institutions),
                    key="igi_f_inst",
                )
            with _fc2:
                st.multiselect(
                    "Sharia Structure", _igi_sharia_opts,
                    default=st.session_state.get("igi_f_sharia", _igi_sharia_opts),
                    key="igi_f_sharia",
                )
            with _fc3:
                st.date_input("Maturity From", value=None, key="igi_f_mat_from")
                st.date_input("Maturity To",   value=None, key="igi_f_mat_to")
            if st.button("↺ Reset filters", key="igi_reset_filters"):
                for _k in ("igi_f_inst", "igi_f_sharia", "igi_f_mat_from", "igi_f_mat_to"):
                    st.session_state.pop(_k, None)
                st.rerun()

        if not _igi_all:
            st.info(
                "No investments yet. Click **➕ Add Investment** to get started.",
                icon="💡",
            )
        elif not _filtered_igi:
            st.info("No investments match the current filter.", icon="🔍")
        else:
            # Group by institution
            _seen_inst: set[str] = set()
            for _inv in _filtered_igi:
                # Institution header (once per group)
                if _inv.institution not in _seen_inst:
                    _seen_inst.add(_inv.institution)
                    st.markdown(f"#### 🏛️ {_inv.institution}")

                _inv_txns = [t for t in _igi_txns if t.investment_id == _inv.investment_id]
                _status_icon = {
                    "Pending Funding": "⏳",
                    "Active": "✅",
                    "Maturity Action Required": "⏰",
                    "Closed": "📁",
                }.get(_inv.status, "•")

                _days_left: int | None = None
                if _inv.maturity_date and _inv.status != "Closed":
                    try:
                        _days_left = (date.fromisoformat(_inv.maturity_date) - date.today()).days
                    except ValueError:
                        pass
                if _days_left is None:
                    _days_str = ""
                elif _days_left < 0:
                    _days_str = f" · {abs(_days_left)}d overdue"
                elif _days_left <= 60:
                    _days_str = f" · ⚡ {_days_left}d left"
                else:
                    _days_str = f" · {_days_left}d left"

                with st.expander(
                    f"{_status_icon} **{_inv.investment_name}** · "
                    f"{_inv.current_value * _igi_rate:,.2f} {_igi_disp_ccy} · "
                    f"Yield {_inv.expected_yield_pct:.2f}% · "
                    f"{_inv.status} · "
                    f"Maturity {_inv.maturity_date or '—'}{_days_str}",
                    expanded=(_inv.status == "Maturity Action Required"),
                ):
                    # Info row
                    _ri1, _ri2, _ri3, _ri4 = st.columns(4)
                    _ri1.caption(f"**Principal:** {_inv.principal_amount * _igi_rate:,.2f} {_igi_disp_ccy}")
                    _ri2.caption(f"**Structure:** {_inv.profit_payment_structure}")
                    _ri3.caption(f"**Liquidity:** {_inv.liquidity_type}")
                    _ri4.caption(f"**Maturity Instruction:** {_inv.maturity_instruction}")
                    if _inv.sharia_structure != "Not Specified":
                        st.caption(f"🕌 Sharia: {_inv.sharia_structure} · {_inv.sharia_status}")
                    if _inv.parent_investment_id or _inv.child_investment_id:
                        _chain_parts = []
                        if _inv.parent_investment_id:
                            _chain_parts.append(f"Parent: `{_inv.parent_investment_id}`")
                        if _inv.child_investment_id:
                            _chain_parts.append(f"Child: `{_inv.child_investment_id}`")
                        st.caption("🔗 Chain: " + " · ".join(_chain_parts))
                    if _inv.notes:
                        st.caption(f"📝 {_inv.notes}")

                    # Performance metrics
                    _m = compute_igi_metrics(
                        _inv.investment_id,
                        _investments=_igi_investments,
                        _all_txns=_igi_txns,
                    )
                    if _m:
                        _met1, _met2, _met3, _met4 = st.columns(4)
                        _met1.metric(f"Total Profit Received · {_igi_disp_ccy}", f"{_m.get('total_profit_received', 0) * _igi_rate:,.2f}")
                        _met2.metric(f"Unrealized Profit · {_igi_disp_ccy}",     f"{_m.get('unrealized_profit', 0) * _igi_rate:,.2f}")
                        _met3.metric(f"Total Return · {_igi_disp_ccy}",          f"{_m.get('total_return', 0) * _igi_rate:,.2f}")
                        _xirr_val = _m.get("xirr")
                        _met4.metric("XIRR", f"{_xirr_val*100:.2f}%" if _xirr_val is not None else "N/A")

                        # ── Yield Schedule (projection — not accounting) ──────
                        _proj = _m.get("projected_total_profit")
                        if _proj is not None:
                            _acc  = _m.get("accrued_to_date", 0.0)
                            _recv = _m.get("total_profit_received", 0.0)
                            _out  = _m.get("outstanding", 0.0) or 0.0
                            st.caption(
                                "📈 **Yield Schedule** — projected from expected rate · "
                                "*informational only, not accounting*"
                            )
                            _ys1, _ys2, _ys3, _ys4 = st.columns(4)
                            _ys1.metric(
                                f"Projected Total · {_igi_disp_ccy}",
                                f"{_proj * _igi_rate:,.2f}",
                            )
                            _ys2.metric(
                                f"Accrued to Date · {_igi_disp_ccy}",
                                f"{_acc * _igi_rate:,.2f}",
                            )
                            _delta_vs_acc = (
                                f"{(_recv - _acc) * _igi_rate:+,.2f} vs accrued"
                                if _acc > 0 else None
                            )
                            _ys3.metric(
                                f"Received · {_igi_disp_ccy}",
                                f"{_recv * _igi_rate:,.2f}",
                                delta=_delta_vs_acc,
                            )
                            _ys4.metric(
                                f"Outstanding · {_igi_disp_ccy}",
                                f"{_out * _igi_rate:,.2f}",
                            )
                            _prog_val = min(1.0, _recv / _proj) if _proj > 0 else 0.0
                            _prog_pct = _recv / _proj * 100 if _proj > 0 else 0.0
                            _acc_pct  = _acc  / _proj * 100 if _proj > 0 else 0.0
                            st.progress(
                                _prog_val,
                                text=(
                                    f"{_prog_pct:.0f}% of projected total received"
                                    + (f" · {_acc_pct:.0f}% accrued to date" if _acc > 0 else "")
                                ),
                            )

                    # Transaction list — table view + separate edit/delete
                    st.caption(f"**Transactions** ({len(_inv_txns)})")
                    if _inv_txns:
                        _sorted_txns = sorted(
                            _inv_txns, key=lambda x: x.date, reverse=True
                        )
                        _txn_df_rows = [
                            {
                                "Date":   t.date,
                                "Type":   t.txn_type,
                                "Amount": f"{t.amount:,.2f}",
                                "Notes":  t.notes or "—",
                            }
                            for t in _sorted_txns
                        ]
                        st.dataframe(
                            pd.DataFrame(_txn_df_rows),
                            use_container_width=True,
                            hide_index=True,
                        )
                        with st.expander("✏️ Edit a transaction"):
                            _txn_labels = [
                                f"{t.date}  ·  {t.txn_type}  ·  {t.amount:,.2f}"
                                for t in _sorted_txns
                            ]
                            _sel_idx = st.selectbox(
                                "Select transaction to edit",
                                options=range(len(_sorted_txns)),
                                format_func=lambda i: _txn_labels[i],
                                key=f"igi_sel_txn_{_inv.investment_id}",
                            )
                            if _sel_idx is not None:
                                _sel_t = _sorted_txns[_sel_idx]
                                if st.button(
                                    "✏️ Edit selected",
                                    use_container_width=True,
                                    key=f"igi_tedit_{_sel_t.txn_id}",
                                ):
                                    _dlg_igi_edit_txn(_sel_t)
                    else:
                        st.caption("_No transactions recorded yet._")

                    # Action buttons
                    _can_mature   = _inv.status in ("Maturity Action Required", "Active")
                    _can_withdraw = _inv.status != "Closed"
                    _can_delete   = _inv.status == "Pending Funding"
                    _act1, _act2, _act3, _act4, _act5 = st.columns(5)
                    with _act1:
                        if st.button("💰 Add Txn", key=f"igi_atxn_{_inv.investment_id}", use_container_width=True):
                            _dlg_igi_txn(_inv)
                    with _act2:
                        if st.button("✏️ Edit", key=f"igi_edit_{_inv.investment_id}", use_container_width=True):
                            _dlg_igi_edit(_inv)
                    with _act3:
                        if st.button(
                            "🔔 Maturity", key=f"igi_mat_{_inv.investment_id}",
                            use_container_width=True, disabled=not _can_mature,
                            type="primary" if _inv.status == "Maturity Action Required" else "secondary",
                        ):
                            _dlg_igi_maturity(_inv)
                    with _act4:
                        if st.button(
                            "📤 Withdraw", key=f"igi_wd_{_inv.investment_id}",
                            use_container_width=True, disabled=not _can_withdraw,
                        ):
                            _dlg_igi_withdraw(_inv)
                    with _act5:
                        if st.button(
                            "🗑️ Delete", key=f"igi_delinv_{_inv.investment_id}",
                            use_container_width=True, disabled=not _can_delete,
                            help="Only available for Pending Funding investments",
                        ):
                            _dlg_igi_del_inv(_inv)

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION B — CROWDFUNDING
    # ═══════════════════════════════════════════════════════════════════════
    else:

        # ── Dialogs ───────────────────────────────────────────────────────

        @st.dialog("➕ Add Crowdfunding Account")
        def _dlg_cf_add():
            _ca1, _ca2 = st.columns(2)
            with _ca1:
                _pn  = st.text_input("Platform Name *", key="cf_add_pn")
                _an  = st.text_input("Account Name *", key="cf_add_an")
                _cft = st.selectbox("Crowdfunding Type", CROWDFUNDING_TYPES, key="cf_add_type")
                _ins = st.text_input("Institution *", key="cf_add_inst")
                _cur = st.selectbox("Currency", CURRENCIES,
                                    index=CURRENCIES.index("SAR") if "SAR" in CURRENCIES else 0,
                                    key="cf_add_ccy")
            with _ca2:
                _cav = st.number_input("Current Account Value", min_value=0.0, step=100.0, format="%.2f", key="cf_add_cav")
                _ac  = st.number_input("Available Cash", min_value=0.0, step=100.0, format="%.2f", key="cf_add_ac")
                _ai  = st.number_input("Active Investments", min_value=0.0, step=100.0, format="%.2f", key="cf_add_ai")
                _di  = st.number_input("Delayed Investments", min_value=0.0, step=100.0, format="%.2f", key="cf_add_di")
                _def = st.number_input("Defaulted Investments", min_value=0.0, step=100.0, format="%.2f", key="cf_add_def")
            _cf1, _cf2 = st.columns(2)
            with _cf1:
                _td = st.number_input("Total Deposits", min_value=0.0, step=100.0, format="%.2f", key="cf_add_td")
                _tw = st.number_input("Total Withdrawals", min_value=0.0, step=100.0, format="%.2f", key="cf_add_tw")
            with _cf2:
                _tp = st.number_input("Total Profit Received", min_value=0.0, step=100.0, format="%.2f", key="cf_add_tp")
                _tl = st.number_input("Total Losses", min_value=0.0, step=100.0, format="%.2f", key="cf_add_tl")
            _lud  = st.date_input("Last Update Date", value=date.today(), key="cf_add_lud")
            with st.expander("Sharia Metadata (optional)"):
                _sstr  = st.selectbox("Sharia Structure", SHARIA_STRUCTURES, key="cf_add_sstr")
                _sstat = st.selectbox("Compliance Status", SHARIA_COMPLIANCE_STATUSES,
                                      index=SHARIA_COMPLIANCE_STATUSES.index("Not Applicable"),
                                      key="cf_add_sstat")
                _sn    = st.text_area("Sharia Notes", key="cf_add_sn", max_chars=300)
            _notes = st.text_area("Notes", key="cf_add_notes", max_chars=500)
            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button("💾 Save", type="primary", use_container_width=True, key="cf_add_save"):
                    _acct, _err = add_cf_account(
                        platform_name=_pn, account_name=_an, crowdfunding_type=_cft,
                        institution=_ins, currency=_cur, current_account_value=_cav,
                        available_cash=_ac, active_investments=_ai,
                        delayed_investments=_di, defaulted_investments=_def,
                        total_deposits=_td, total_withdrawals=_tw,
                        total_profit_received=_tp, total_losses=_tl,
                        last_update_date=_lud.isoformat(),
                        notes=_notes, sharia_structure=_sstr,
                        sharia_status=_sstat, sharia_notes=_sn,
                    )
                    if _err:
                        st.error(_err)
                    else:
                        st.toast(f"Account added: {_acct.platform_name} – {_acct.account_name}", icon="✅")
                        st.rerun()
            with _b2:
                if st.button("Cancel", use_container_width=True, key="cf_add_cancel"):
                    st.rerun()

        @st.dialog("✏️ Edit CF Account")
        def _dlg_cf_edit(acct):
            _ec1, _ec2 = st.columns(2)
            with _ec1:
                _pn  = st.text_input("Platform Name", value=acct.platform_name, key=f"cf_e_pn_{acct.account_id}")
                _an  = st.text_input("Account Name", value=acct.account_name, key=f"cf_e_an_{acct.account_id}")
                _ins = st.text_input("Institution", value=acct.institution, key=f"cf_e_ins_{acct.account_id}")
                _cft = st.selectbox("Type", CROWDFUNDING_TYPES,
                                    index=CROWDFUNDING_TYPES.index(acct.crowdfunding_type) if acct.crowdfunding_type in CROWDFUNDING_TYPES else 0,
                                    key=f"cf_e_type_{acct.account_id}")
            with _ec2:
                _stat = st.selectbox("Status", CF_STATUSES,
                                     index=CF_STATUSES.index(acct.status) if acct.status in CF_STATUSES else 0,
                                     key=f"cf_e_stat_{acct.account_id}")
                _td   = st.number_input("Total Deposits", value=float(acct.total_deposits), min_value=0.0, step=100.0, format="%.2f", key=f"cf_e_td_{acct.account_id}")
                _tw   = st.number_input("Total Withdrawals", value=float(acct.total_withdrawals), min_value=0.0, step=100.0, format="%.2f", key=f"cf_e_tw_{acct.account_id}")
                _tp   = st.number_input("Total Profit Received", value=float(acct.total_profit_received), min_value=0.0, step=100.0, format="%.2f", key=f"cf_e_tp_{acct.account_id}")
                _tl   = st.number_input("Total Losses", value=float(acct.total_losses), min_value=0.0, step=100.0, format="%.2f", key=f"cf_e_tl_{acct.account_id}")
            _notes = st.text_area("Notes", value=acct.notes, max_chars=500, key=f"cf_e_notes_{acct.account_id}")
            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button("💾 Save", type="primary", use_container_width=True, key=f"cf_e_save_{acct.account_id}"):
                    _, _err = edit_cf_account(
                        acct.account_id, platform_name=_pn, account_name=_an,
                        institution=_ins, crowdfunding_type=_cft, status=_stat,
                        total_deposits=_td, total_withdrawals=_tw,
                        total_profit_received=_tp, total_losses=_tl, notes=_notes,
                    )
                    if _err:
                        st.error(_err)
                    else:
                        st.toast("Account updated", icon="💾")
                        st.rerun()
            with _b2:
                if st.button("Cancel", use_container_width=True, key=f"cf_e_cancel_{acct.account_id}"):
                    st.rerun()

        @st.dialog("💰 Add CF Transaction")
        def _dlg_cf_txn(acct):
            st.caption(f"**{acct.platform_name}** · {acct.account_name} · {acct.currency}")
            _ct1, _ct2, _ct3 = st.columns(3)
            with _ct1:
                _tt  = st.selectbox("Type", CF_TRANSACTION_TYPES, key=f"cf_t_type_{acct.account_id}")
            with _ct2:
                _amt = st.number_input("Amount", min_value=0.01, step=100.0, format="%.2f", key=f"cf_t_amt_{acct.account_id}")
            with _ct3:
                _dt  = st.date_input("Date", value=date.today(), key=f"cf_t_dt_{acct.account_id}")
            _notes = st.text_area("Notes", key=f"cf_t_notes_{acct.account_id}", max_chars=300)
            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button("💾 Save", type="primary", use_container_width=True, key=f"cf_t_save_{acct.account_id}"):
                    _, _err = record_cf_transaction(
                        account_id=acct.account_id, txn_type=_tt,
                        amount=_amt, txn_date=_dt.isoformat(), notes=_notes,
                    )
                    if _err:
                        st.error(_err)
                    else:
                        st.toast(f"{_tt}: {_amt:,.2f} {acct.currency}", icon="✅")
                        st.rerun()
            with _b2:
                if st.button("Cancel", use_container_width=True, key=f"cf_t_cancel_{acct.account_id}"):
                    st.rerun()

        @st.dialog("📸 Update Snapshot")
        def _dlg_cf_snap(acct):
            st.caption(
                f"**{acct.platform_name}** · {acct.account_name}  \n"
                "Captures the current state. Historical snapshots are never overwritten."
            )
            _sd  = st.date_input("Snapshot Date", value=date.today(), key=f"cf_s_dt_{acct.account_id}")
            _sc1, _sc2 = st.columns(2)
            with _sc1:
                _cav = st.number_input("Current Account Value", value=float(acct.current_account_value), min_value=0.0, step=100.0, format="%.2f", key=f"cf_s_cav_{acct.account_id}")
                _ac  = st.number_input("Available Cash", value=float(acct.available_cash), min_value=0.0, step=100.0, format="%.2f", key=f"cf_s_ac_{acct.account_id}")
                _ai  = st.number_input("Active Investments", value=float(acct.active_investments), min_value=0.0, step=100.0, format="%.2f", key=f"cf_s_ai_{acct.account_id}")
            with _sc2:
                _di  = st.number_input("Delayed Investments", value=float(acct.delayed_investments), min_value=0.0, step=100.0, format="%.2f", key=f"cf_s_di_{acct.account_id}")
                _def = st.number_input("Defaulted Investments", value=float(acct.defaulted_investments), min_value=0.0, step=100.0, format="%.2f", key=f"cf_s_def_{acct.account_id}")
            _notes = st.text_area("Notes", key=f"cf_s_notes_{acct.account_id}", max_chars=300)
            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button("💾 Save Snapshot", type="primary", use_container_width=True, key=f"cf_s_save_{acct.account_id}"):
                    _, _err = add_cf_snapshot(
                        account_id=acct.account_id,
                        snapshot_date=_sd.isoformat(),
                        current_account_value=_cav, available_cash=_ac,
                        active_investments=_ai, delayed_investments=_di,
                        defaulted_investments=_def, notes=_notes,
                    )
                    if _err:
                        st.error(_err)
                    else:
                        st.toast("Snapshot saved — account position updated", icon="📸")
                        st.rerun()
            with _b2:
                if st.button("Cancel", use_container_width=True, key=f"cf_s_cancel_{acct.account_id}"):
                    st.rerun()

        # ── Load data ─────────────────────────────────────────────────────
        _cf_accounts  = load_cf_accounts()
        _cf_txns      = load_cf_transactions()
        _cf_snapshots = load_cf_snapshots()

        # ── Summary metrics ────────────────────────────────────────────────
        _cf_all    = list(_cf_accounts.values())
        _cf_active = [a for a in _cf_all if a.status == "Active"]
        _cf_total  = sum(a.current_account_value for a in _cf_active)
        _cf_dep    = sum(a.total_deposits for a in _cf_active)
        _cf_profit = sum(a.total_profit_received for a in _cf_active)
        _cf_losses = sum(a.total_losses for a in _cf_active)

        _csm1, _csm2, _csm3, _csm4, _csm5 = st.columns(5)
        _csm1.metric("Accounts",          len(_cf_all))
        _csm2.metric("Active",            len(_cf_active))
        _csm3.metric("Total Value",       f"{_cf_total:,.2f}")
        _csm4.metric("Total Deposits",    f"{_cf_dep:,.2f}")
        _csm5.metric("Net Profit / Loss", f"{_cf_profit - _cf_losses:,.2f}")

        # ── Add button + status filter ─────────────────────────────────────
        _cf_c1, _cf_c2 = st.columns([3, 1])
        with _cf_c1:
            _cf_stat_filter = st.selectbox("Filter by Status", ["All"] + CF_STATUSES, key="cf_status_filter")
        with _cf_c2:
            if st.button("➕ Add Account", use_container_width=True, type="primary", key="cf_open_add"):
                _dlg_cf_add()

        # ── Account list ────────────────────────────────────────────────────
        _filtered_cf = _cf_all
        if _cf_stat_filter != "All":
            _filtered_cf = [a for a in _cf_all if a.status == _cf_stat_filter]
        _filtered_cf = sorted(_filtered_cf, key=lambda x: x.platform_name)

        if not _cf_all:
            st.info("No crowdfunding accounts yet. Click **➕ Add Account** to get started.", icon="💡")
        elif not _filtered_cf:
            st.info("No accounts match the current filter.", icon="🔍")
        else:
            for _acct in _filtered_cf:
                _acct_txns  = [t for t in _cf_txns if t.account_id == _acct.account_id]
                _acct_snaps = [s for s in _cf_snapshots if s.account_id == _acct.account_id]
                _rec        = compute_cf_reconciliation(_acct.account_id)
                _udiff      = _rec.get("unreconciled_diff", 0.0)
                _udiff_icon = "✅" if abs(_udiff) < 0.01 else "⚠️"

                with st.expander(
                    f"**{_acct.platform_name}** · {_acct.account_name} · "
                    f"{_acct.current_account_value:,.2f} {_acct.currency} · "
                    f"{_acct.crowdfunding_type} · {_acct.status} · "
                    f"{_udiff_icon} Recon diff: {_udiff:+,.2f}",
                    expanded=False,
                ):
                    # Info row
                    _rci1, _rci2, _rci3, _rci4 = st.columns(4)
                    _rci1.caption(f"**Institution:** {_acct.institution}")
                    _rci2.caption(f"**Available Cash:** {_acct.available_cash:,.2f}")
                    _rci3.caption(f"**Delayed:** {_acct.delayed_investments:,.2f}")
                    _rci4.caption(f"**Defaulted:** {_acct.defaulted_investments:,.2f}")
                    if _acct.sharia_structure != "Not Specified":
                        st.caption(f"🕌 Sharia: {_acct.sharia_structure} · {_acct.sharia_status}")

                    # Metrics
                    _cm = compute_cf_metrics(_acct.account_id)
                    if _cm:
                        _cmet1, _cmet2, _cmet3, _cmet4, _cmet5 = st.columns(5)
                        _cmet1.metric("Net Deposits",    f"{_cm.get('net_deposits', 0):,.2f}")
                        _cmet2.metric("Total Profit",    f"{_cm.get('total_profit_received', 0):,.2f}")
                        _cmet3.metric("Total Losses",    f"{_cm.get('total_losses', 0):,.2f}")
                        _cmet4.metric("Net P&L",         f"{_cm.get('net_profit_loss', 0):,.2f}")
                        _cxirr = _cm.get("xirr")
                        _cmet5.metric("XIRR", f"{_cxirr*100:.2f}%" if _cxirr is not None else "N/A")

                    # Reconciliation detail
                    with st.expander("📊 Reconciliation Detail", expanded=False):
                        _rc1, _rc2, _rc3 = st.columns(3)
                        _rc1.metric("Deposits",       f"{_rec.get('deposits', 0):,.2f}")
                        _rc2.metric("Withdrawals",    f"{_rec.get('withdrawals', 0):,.2f}")
                        _rc3.metric("Profits",        f"{_rec.get('profits', 0):,.2f}")
                        _rc4, _rc5, _rc6 = st.columns(3)
                        _rc4.metric("Losses",         f"{_rec.get('losses', 0):,.2f}")
                        _rc5.metric("Expected Balance", f"{_rec.get('expected_balance', 0):,.2f}")
                        _rc6.metric("Unreconciled Diff", f"{_udiff:+,.2f}")
                        if abs(_udiff) > 0.01:
                            st.caption(
                                "Possible causes: auto-invest activity, platform timing, "
                                "unrecorded transactions, fees, valuation changes, or data entry."
                            )

                    # Transaction mini-table
                    if _acct_txns:
                        with st.expander(f"💰 Transactions ({len(_acct_txns)})", expanded=False):
                            _ct_rows = [
                                {"Date": t.date, "Type": t.txn_type,
                                 "Amount": t.amount, "Notes": t.notes}
                                for t in sorted(_acct_txns, key=lambda x: x.date, reverse=True)
                            ]
                            st.dataframe(pd.DataFrame(_ct_rows), use_container_width=True, hide_index=True)

                    # Snapshot history
                    if _acct_snaps:
                        with st.expander(f"📸 Snapshots ({len(_acct_snaps)})", expanded=False):
                            _snap_rows = [
                                {"Date": s.snapshot_date,
                                 "Value": s.current_account_value,
                                 "Cash": s.available_cash,
                                 "Active": s.active_investments,
                                 "Delayed": s.delayed_investments,
                                 "Defaulted": s.defaulted_investments,
                                 "Notes": s.notes}
                                for s in sorted(_acct_snaps, key=lambda x: x.snapshot_date, reverse=True)
                            ]
                            st.dataframe(pd.DataFrame(_snap_rows), use_container_width=True, hide_index=True)

                    # Action buttons
                    _cact1, _cact2, _cact3 = st.columns(3)
                    with _cact1:
                        if st.button("💰 Add Txn", key=f"cf_atxn_{_acct.account_id}", use_container_width=True):
                            _dlg_cf_txn(_acct)
                    with _cact2:
                        if st.button("📸 Snapshot", key=f"cf_snap_{_acct.account_id}", use_container_width=True):
                            _dlg_cf_snap(_acct)
                    with _cact3:
                        if st.button("✏️ Edit", key=f"cf_edit_{_acct.account_id}", use_container_width=True):
                            _dlg_cf_edit(_acct)
                    if _acct.notes:
                        st.caption(f"📝 {_acct.notes}")


# ── Fixed Assets Tab ──────────────────────────────────────────────────────────

def render_fixed_assets_tab() -> None:
    """Fixed Assets — manually-valued illiquid assets (real estate, vehicles, etc.)."""
    from portfolio.fixed_assets import (
        FIXED_ASSET_TYPES, FA_STATUSES,
        load_fixed_assets, add_fixed_asset, edit_fixed_asset, sell_fixed_asset,
    )
    from portfolio import CURRENCIES
    from fx_rates import get_rates_for_holdings
    from datetime import date
    import pandas as pd

    st.header("🏛️ Assets & Retirement")
    st.caption(
        "Track illiquid and long-term assets — real estate, vehicles, physical gold, "
        "business stakes, pension funds, and provident fund balances — "
        "with a simple current value and optional liability.  "
        "**Equity** (value − liability) feeds the Net Worth total in the header."
    )

    _base_ccy = st.session_state.get("global_base_ccy", "SAR")
    _fa_all   = load_fixed_assets()

    # ── Dialogs ───────────────────────────────────────────────────────────────

    @st.dialog("➕ Add Fixed Asset")
    def _dlg_fa_add():
        _c1, _c2 = st.columns(2)
        with _c1:
            _nm  = st.text_input("Asset Name *", key="fa_add_name",
                                  placeholder="e.g. Riyadh Apartment, 2023 Camry")
            _at  = st.selectbox("Asset Type *", FIXED_ASSET_TYPES, key="fa_add_type")
            _cur = st.selectbox(
                "Currency", CURRENCIES,
                index=CURRENCIES.index("SAR") if "SAR" in CURRENCIES else 0,
                key="fa_add_ccy",
            )
        with _c2:
            _cv  = st.number_input("Current Value *", min_value=0.0, step=1_000.0,
                                   format="%.2f", key="fa_add_cv",
                                   help="Your best estimate of today's market value.")
            _li  = st.number_input("Outstanding Liability", min_value=0.0, step=1_000.0,
                                   format="%.2f", key="fa_add_li",
                                   help="Mortgage, car loan, etc. Leave 0 if none.")
            _pp  = st.number_input("Purchase Price (optional)", min_value=0.0, step=1_000.0,
                                   format="%.2f", key="fa_add_pp",
                                   help="Leave 0 if unknown — used only to show unrealised gain.")
            _pd  = st.date_input("Purchase Date (optional)", value=None,
                                  key="fa_add_pd")
        _notes = st.text_area("Notes", key="fa_add_notes", max_chars=500)
        _b1, _b2 = st.columns(2)
        with _b1:
            if st.button("💾 Save", type="primary", use_container_width=True, key="fa_add_save"):
                _asset, _err = add_fixed_asset(
                    name=_nm, asset_type=_at, currency=_cur,
                    current_value=_cv, outstanding_liability=_li,
                    purchase_price=_pp,
                    purchase_date=_pd.isoformat() if _pd else "",
                    notes=_notes,
                )
                if _err:
                    st.error(_err)
                else:
                    st.toast(f"Asset added: {_asset.name}", icon="✅")
                    st.rerun()
        with _b2:
            if st.button("Cancel", use_container_width=True, key="fa_add_cancel"):
                st.rerun()

    @st.dialog("✏️ Edit Fixed Asset")
    def _dlg_fa_edit(asset):
        _c1, _c2 = st.columns(2)
        with _c1:
            _nm  = st.text_input("Asset Name", value=asset.name,
                                  key=f"fa_e_nm_{asset.asset_id}")
            _at  = st.selectbox("Asset Type", FIXED_ASSET_TYPES,
                                 index=FIXED_ASSET_TYPES.index(asset.asset_type)
                                       if asset.asset_type in FIXED_ASSET_TYPES else 0,
                                 key=f"fa_e_at_{asset.asset_id}")
            _cur = st.selectbox(
                "Currency", CURRENCIES,
                index=CURRENCIES.index(asset.currency) if asset.currency in CURRENCIES else 0,
                key=f"fa_e_cur_{asset.asset_id}",
            )
        with _c2:
            _cv  = st.number_input("Current Value", min_value=0.0, step=1_000.0,
                                   format="%.2f", value=float(asset.current_value),
                                   key=f"fa_e_cv_{asset.asset_id}")
            _li  = st.number_input("Outstanding Liability", min_value=0.0, step=1_000.0,
                                   format="%.2f", value=float(asset.outstanding_liability),
                                   key=f"fa_e_li_{asset.asset_id}")
            _pp  = st.number_input("Purchase Price", min_value=0.0, step=1_000.0,
                                   format="%.2f", value=float(asset.purchase_price),
                                   key=f"fa_e_pp_{asset.asset_id}")
            try:
                _pd_val = date.fromisoformat(asset.purchase_date) if asset.purchase_date else None
            except ValueError:
                _pd_val = None
            _pd = st.date_input("Purchase Date", value=_pd_val,
                                 key=f"fa_e_pd_{asset.asset_id}")
        _notes = st.text_area("Notes", value=asset.notes,
                               key=f"fa_e_notes_{asset.asset_id}", max_chars=500)
        _b1, _b2 = st.columns(2)
        with _b1:
            if st.button("💾 Save", type="primary", use_container_width=True,
                         key=f"fa_e_save_{asset.asset_id}"):
                _, _err = edit_fixed_asset(
                    asset.asset_id,
                    name=_nm, asset_type=_at, currency=_cur,
                    current_value=_cv, outstanding_liability=_li,
                    purchase_price=_pp,
                    purchase_date=_pd.isoformat() if _pd else "",
                    notes=_notes,
                )
                if _err:
                    st.error(_err)
                else:
                    st.toast("Asset updated.", icon="✅")
                    st.rerun()
        with _b2:
            if st.button("Cancel", use_container_width=True,
                         key=f"fa_e_cancel_{asset.asset_id}"):
                st.rerun()

    @st.dialog("🏷️ Mark as Sold")
    def _dlg_fa_sell(asset):
        st.warning(
            f"Mark **{asset.name}** as Sold?\n\n"
            "It will be removed from your Net Worth but kept in Sold History."
        )
        _b1, _b2 = st.columns(2)
        with _b1:
            if st.button("✅ Confirm Sold", type="primary", use_container_width=True,
                         key=f"fa_sell_ok_{asset.asset_id}"):
                _ok, _err = sell_fixed_asset(asset.asset_id)
                if _err:
                    st.error(_err)
                else:
                    st.toast(f"{asset.name} marked as Sold.", icon="🏷️")
                    st.rerun()
        with _b2:
            if st.button("Cancel", use_container_width=True,
                         key=f"fa_sell_cancel_{asset.asset_id}"):
                st.rerun()

    # ── Summary KPI row ───────────────────────────────────────────────────────

    _active = {k: v for k, v in _fa_all.items() if v.status == "Active"}
    _sold   = {k: v for k, v in _fa_all.items() if v.status == "Sold"}

    if _active:
        # Compute total equity in base ccy
        _fa_ccys = list({a.currency for a in _active.values()})
        _fa_fx   = get_rates_for_holdings(_fa_ccys, _base_ccy) if _fa_ccys else {}
        _fa_total_equity = sum(
            a.equity * ((_fa_fx.get(a.currency).rate if _fa_fx.get(a.currency) else 1.0))
            for a in _active.values()
        )
        _fa_total_value = sum(
            a.current_value * ((_fa_fx.get(a.currency).rate if _fa_fx.get(a.currency) else 1.0))
            for a in _active.values()
        )
        _fa_total_liab = _fa_total_value - _fa_total_equity

        def _fa_fmt(v: float) -> str:
            av = abs(v)
            if av >= 1_000_000:
                return f"{v / 1_000_000:.2f}M"
            if av >= 1_000:
                return f"{v:,.0f}"
            return f"{v:,.2f}"

        st.markdown(
            f'<div class="acct-summary-row">'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">Total Equity ({_base_ccy})</div>'
            f'    <div class="acct-kpi-val">{_fa_fmt(_fa_total_equity)}</div>'
            f'  </div>'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">Total Value ({_base_ccy})</div>'
            f'    <div class="acct-kpi-val">{_fa_fmt(_fa_total_value)}</div>'
            f'  </div>'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">Total Liability ({_base_ccy})</div>'
            f'    <div class="acct-kpi-val">{_fa_fmt(_fa_total_liab)}</div>'
            f'  </div>'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">Active Assets</div>'
            f'    <div class="acct-kpi-val">{len(_active)}</div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Sub-navigation ────────────────────────────────────────────────────────

    _fa_view = st.pills(
        "fa_view",
        ["🏠 Active", "📦 Sold History"],
        default="🏠 Active",
        label_visibility="collapsed",
        key="fa_subnav",
    )

    _cadd, _ = st.columns([1, 5])
    with _cadd:
        if st.button("➕ Add Asset", type="primary", use_container_width=True, key="fa_add_btn"):
            _dlg_fa_add()

    st.divider()

    # ═════════════════════════════════════════════════════════════════════════
    # ACTIVE ASSETS
    # ═════════════════════════════════════════════════════════════════════════
    if _fa_view == "🏠 Active":
        if not _active:
            st.info(
                "No fixed assets yet.  Click **➕ Add Asset** above to record your first "
                "real estate property, vehicle, physical gold holding, or other illiquid asset.",
                icon="🏠",
            )
        else:
            _TYPE_ICON = {
                "Real Estate":                "🏠",
                "Vehicle":                    "🚗",
                "Precious Metals (Physical)": "🪙",
                "Business Stake":             "💼",
                "Pension / Retirement Fund":  "🏦",
                "Provident Fund":             "🏛️",
                "Other":                      "📦",
            }
            for _asset in sorted(_active.values(), key=lambda a: a.name):
                _icon = _TYPE_ICON.get(_asset.asset_type, "📦")
                with st.expander(
                    f"{_icon} **{_asset.name}** — {_asset.asset_type}  ·  "
                    f"{_asset.currency} {_asset.current_value:,.0f}  →  "
                    f"equity {_asset.currency} {_asset.equity:,.0f}",
                    expanded=False,
                ):
                    _dc1, _dc2, _dc3 = st.columns(3)
                    _dc1.metric("Current Value", f"{_asset.currency} {_asset.current_value:,.2f}")
                    _dc2.metric("Liability",     f"{_asset.currency} {_asset.outstanding_liability:,.2f}")
                    _dc3.metric("Equity",        f"{_asset.currency} {_asset.equity:,.2f}")

                    if _asset.purchase_price > 0:
                        _gain = _asset.unrealized_gain
                        _gain_pct = (_gain / _asset.purchase_price * 100) if _gain is not None else None
                        _gc4, _gc5 = st.columns(2)
                        _gc4.metric("Purchase Price", f"{_asset.currency} {_asset.purchase_price:,.2f}")
                        if _gain is not None and _gain_pct is not None:
                            _gc5.metric(
                                "Unrealised Gain",
                                f"{_asset.currency} {_gain:+,.2f}",
                                delta=f"{_gain_pct:+.1f}%",
                            )

                    if _asset.purchase_date:
                        st.caption(f"📅 Purchased: {_asset.purchase_date}")
                    if _asset.notes:
                        st.caption(f"📝 {_asset.notes}")

                    _ba1, _ba2 = st.columns(2)
                    with _ba1:
                        if st.button("✏️ Edit", key=f"fa_edit_{_asset.asset_id}",
                                     use_container_width=True):
                            _dlg_fa_edit(_asset)
                    with _ba2:
                        if st.button("🏷️ Mark as Sold", key=f"fa_sell_{_asset.asset_id}",
                                     use_container_width=True):
                            _dlg_fa_sell(_asset)

    # ═════════════════════════════════════════════════════════════════════════
    # SOLD HISTORY
    # ═════════════════════════════════════════════════════════════════════════
    else:
        if not _sold:
            st.info("No sold assets yet.", icon="📦")
        else:
            _rows = []
            for a in sorted(_sold.values(), key=lambda x: x.updated_at or "", reverse=True):
                _rows.append({
                    "Name":           a.name,
                    "Type":           a.asset_type,
                    "Currency":       a.currency,
                    "Value at Sale":  a.current_value,
                    "Notes":          a.notes or "—",
                })
            st.dataframe(
                pd.DataFrame(_rows),
                use_container_width=True,
                hide_index=True,
            )


# ── Liabilities Tab ───────────────────────────────────────────────────────────

def render_liabilities_tab() -> None:
    """Liabilities — loans, credit cards, and other debts deducted from Net Worth."""
    from portfolio.liabilities import (
        LIABILITY_TYPES,
        load_liabilities, add_liability, edit_liability, mark_paid_off,
        compute_liabilities_base,
    )
    from portfolio import CURRENCIES
    from fx_rates import get_rates_for_holdings
    import pandas as pd

    st.header("📋 Liabilities")
    st.caption(
        "Track your financial obligations — loans, credit cards, mortgages, and other debts. "
        "Active liabilities are deducted from your **Net Worth** total in the header."
    )

    _base_ccy = st.session_state.get("global_base_ccy", "SAR")
    _libs_all = load_liabilities()

    # ── Dialogs ───────────────────────────────────────────────────────────────

    @st.dialog("➕ Add Liability")
    def _dlg_lib_add():
        _c1, _c2 = st.columns(2)
        with _c1:
            _nm  = st.text_input("Liability Name *", key="lib_add_name",
                                  placeholder="e.g. Car Loan, Credit Card")
            _lt  = st.selectbox("Type *", LIABILITY_TYPES, key="lib_add_type")
            _cur = st.selectbox(
                "Currency", CURRENCIES,
                index=CURRENCIES.index("SAR") if "SAR" in CURRENCIES else 0,
                key="lib_add_ccy",
            )
        with _c2:
            _bal = st.number_input("Outstanding Balance *", min_value=0.0, step=1_000.0,
                                   format="%.2f", key="lib_add_bal",
                                   help="Remaining amount owed.")
            _ir  = st.number_input("Interest Rate (% p.a.)", min_value=0.0, max_value=100.0,
                                   step=0.1, format="%.2f", key="lib_add_ir",
                                   help="Leave 0 if unknown.")
            _dd  = st.date_input("Due / Payoff Date (optional)", value=None, key="lib_add_dd")
        _lender = st.text_input("Lender / Institution", key="lib_add_lender",
                                 placeholder="e.g. Al Rajhi Bank, Riyad Bank")
        _notes  = st.text_area("Notes", key="lib_add_notes", max_chars=500)
        _b1, _b2 = st.columns(2)
        with _b1:
            if st.button("💾 Save", type="primary", use_container_width=True, key="lib_add_save"):
                _lib, _err = add_liability(
                    name=_nm, liability_type=_lt, currency=_cur,
                    outstanding_balance=_bal, lender=_lender,
                    interest_rate=_ir,
                    due_date=_dd.isoformat() if _dd else "",
                    notes=_notes,
                )
                if _err:
                    st.error(_err)
                else:
                    st.toast(f"Liability added: {_lib.name}", icon="✅")
                    st.rerun()
        with _b2:
            if st.button("Cancel", use_container_width=True, key="lib_add_cancel"):
                st.rerun()

    @st.dialog("✏️ Edit Liability")
    def _dlg_lib_edit(lib):
        _c1, _c2 = st.columns(2)
        with _c1:
            _nm  = st.text_input("Liability Name", value=lib.name,
                                  key=f"lib_e_nm_{lib.liability_id}")
            _lt  = st.selectbox("Type", LIABILITY_TYPES,
                                 index=LIABILITY_TYPES.index(lib.liability_type)
                                       if lib.liability_type in LIABILITY_TYPES else 0,
                                 key=f"lib_e_lt_{lib.liability_id}")
            _cur = st.selectbox(
                "Currency", CURRENCIES,
                index=CURRENCIES.index(lib.currency) if lib.currency in CURRENCIES else 0,
                key=f"lib_e_cur_{lib.liability_id}",
            )
        with _c2:
            _bal = st.number_input("Outstanding Balance", min_value=0.0, step=1_000.0,
                                   format="%.2f", value=float(lib.outstanding_balance),
                                   key=f"lib_e_bal_{lib.liability_id}")
            _ir  = st.number_input("Interest Rate (% p.a.)", min_value=0.0, max_value=100.0,
                                   step=0.1, format="%.2f", value=float(lib.interest_rate),
                                   key=f"lib_e_ir_{lib.liability_id}")
            try:
                _dd_val = __import__("datetime").date.fromisoformat(lib.due_date) if lib.due_date else None
            except ValueError:
                _dd_val = None
            _dd = st.date_input("Due / Payoff Date", value=_dd_val,
                                 key=f"lib_e_dd_{lib.liability_id}")
        _lender = st.text_input("Lender / Institution", value=lib.lender,
                                 key=f"lib_e_lender_{lib.liability_id}")
        _notes  = st.text_area("Notes", value=lib.notes,
                                key=f"lib_e_notes_{lib.liability_id}", max_chars=500)
        _b1, _b2 = st.columns(2)
        with _b1:
            if st.button("💾 Save", type="primary", use_container_width=True,
                         key=f"lib_e_save_{lib.liability_id}"):
                _, _err = edit_liability(
                    lib.liability_id,
                    name=_nm, liability_type=_lt, currency=_cur,
                    outstanding_balance=_bal, lender=_lender,
                    interest_rate=_ir,
                    due_date=_dd.isoformat() if _dd else "",
                    notes=_notes,
                )
                if _err:
                    st.error(_err)
                else:
                    st.toast("Liability updated.", icon="✅")
                    st.rerun()
        with _b2:
            if st.button("Cancel", use_container_width=True,
                         key=f"lib_e_cancel_{lib.liability_id}"):
                st.rerun()

    @st.dialog("✅ Mark as Paid Off")
    def _dlg_lib_paid(lib):
        st.warning(
            f"Mark **{lib.name}** as Paid Off?\n\n"
            "It will be removed from your Net Worth deduction but kept in history."
        )
        _b1, _b2 = st.columns(2)
        with _b1:
            if st.button("✅ Confirm Paid Off", type="primary", use_container_width=True,
                         key=f"lib_paid_ok_{lib.liability_id}"):
                _ok, _err = mark_paid_off(lib.liability_id)
                if _err:
                    st.error(_err)
                else:
                    st.toast(f"{lib.name} marked as Paid Off.", icon="✅")
                    st.rerun()
        with _b2:
            if st.button("Cancel", use_container_width=True,
                         key=f"lib_paid_cancel_{lib.liability_id}"):
                st.rerun()

    # ── Summary KPI row ───────────────────────────────────────────────────────

    _active = {k: v for k, v in _libs_all.items() if v.status == "Active"}
    _paid   = {k: v for k, v in _libs_all.items() if v.status == "Paid Off"}

    if _active:
        _lib_ccys = list({v.currency for v in _active.values()})
        _lib_fx   = get_rates_for_holdings(_lib_ccys, _base_ccy) if _lib_ccys else {}
        _total_owed = compute_liabilities_base(_active, _base_ccy, _lib_fx)

        def _lib_fmt(v: float) -> str:
            av = abs(v)
            if av >= 1_000_000:
                return f"{v / 1_000_000:.2f}M"
            if av >= 1_000:
                return f"{v:,.0f}"
            return f"{v:,.2f}"

        st.markdown(
            f'<div class="acct-summary-row">'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">Total Owed ({_base_ccy})</div>'
            f'    <div class="acct-kpi-val" style="color:#ef4444">{_lib_fmt(_total_owed)}</div>'
            f'  </div>'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">Active Liabilities</div>'
            f'    <div class="acct-kpi-val">{len(_active)}</div>'
            f'  </div>'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">Paid Off</div>'
            f'    <div class="acct-kpi-val" style="color:#22c55e">{len(_paid)}</div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Sub-navigation + add button ───────────────────────────────────────────

    _lib_view = st.pills(
        "lib_view",
        ["📋 Active", "✅ Paid Off History"],
        default="📋 Active",
        label_visibility="collapsed",
        key="lib_subnav",
    )

    _cadd, _ = st.columns([1, 5])
    with _cadd:
        if st.button("➕ Add Liability", type="primary", use_container_width=True, key="lib_add_btn"):
            _dlg_lib_add()

    st.divider()

    # ═════════════════════════════════════════════════════════════════════════
    # ACTIVE LIABILITIES
    # ═════════════════════════════════════════════════════════════════════════
    if _lib_view == "📋 Active":
        if not _active:
            st.info(
                "No active liabilities recorded.  Click **➕ Add Liability** above to track "
                "a loan, mortgage, credit card balance, or other obligation.",
                icon="📋",
            )
        else:
            _TYPE_ICON = {
                "Personal Loan":  "💳",
                "Car Loan":       "🚗",
                "Home Mortgage":  "🏠",
                "Credit Card":    "💳",
                "Business Loan":  "💼",
                "Other":          "📌",
            }
            _lib_ccys2 = list({v.currency for v in _active.values()})
            _lib_fx2   = get_rates_for_holdings(_lib_ccys2, _base_ccy) if _lib_ccys2 else {}
            for _lib in sorted(_active.values(), key=lambda x: x.name):
                _icon = _TYPE_ICON.get(_lib.liability_type, "📌")
                _rate = (_lib_fx2.get(_lib.currency).rate
                         if _lib_fx2.get(_lib.currency) else 1.0)
                _bal_base = _lib.outstanding_balance * _rate
                with st.expander(
                    f"{_icon} **{_lib.name}** — {_lib.liability_type}  ·  "
                    f"{_lib.currency} {_lib.outstanding_balance:,.0f}"
                    + (f"  ·  {_lib.lender}" if _lib.lender else ""),
                    expanded=False,
                ):
                    _dc1, _dc2, _dc3 = st.columns(3)
                    _dc1.metric("Balance", f"{_lib.currency} {_lib.outstanding_balance:,.2f}")
                    _dc2.metric(f"Balance ({_base_ccy})", f"{_bal_base:,.2f}")
                    _dc3.metric("Interest Rate", f"{_lib.interest_rate:.2f}% p.a." if _lib.interest_rate else "—")
                    if _lib.lender:
                        st.caption(f"🏦 Lender: {_lib.lender}")
                    if _lib.due_date:
                        st.caption(f"📅 Due: {_lib.due_date}")
                    if _lib.notes:
                        st.caption(f"📝 {_lib.notes}")
                    _ba1, _ba2 = st.columns(2)
                    with _ba1:
                        if st.button("✏️ Edit", key=f"lib_edit_{_lib.liability_id}",
                                     use_container_width=True):
                            _dlg_lib_edit(_lib)
                    with _ba2:
                        if st.button("✅ Mark Paid Off", key=f"lib_paid_{_lib.liability_id}",
                                     use_container_width=True):
                            _dlg_lib_paid(_lib)

    # ═════════════════════════════════════════════════════════════════════════
    # PAID OFF HISTORY
    # ═════════════════════════════════════════════════════════════════════════
    else:
        if not _paid:
            st.info("No paid-off liabilities yet.", icon="✅")
        else:
            _rows = []
            for _lib in sorted(_paid.values(), key=lambda x: x.updated_at or "", reverse=True):
                _rows.append({
                    "Name":     _lib.name,
                    "Type":     _lib.liability_type,
                    "Lender":   _lib.lender or "—",
                    "Currency": _lib.currency,
                    "Balance":  _lib.outstanding_balance,
                    "Notes":    _lib.notes or "—",
                })
            st.dataframe(
                pd.DataFrame(_rows),
                use_container_width=True,
                hide_index=True,
            )

# ── Developer Mode: SAHMK Discovery Console ──────────────────────────────────

def render_sahmk_discovery_tab() -> None:
    """Developer Mode — SAHMK Data Fetch & Store."""
    from portfolio.sahmk_discovery import (
        download_and_store as _disc_download,
        list_stored        as _disc_list,
    )

    if not st.session_state.get("dev_mode", False):
        st.info(
            "🔒 **SAHMK Discovery is only available in Developer Mode.**  \n"
            "Enable **🔧 Developer Mode** in the sidebar to access this tab.",
            icon="🔧",
        )
        return

    st.header("🔍 SAHMK Data")

    from sahmk_client import is_configured as _sahmk_configured
    _disc_yahoo_only = st.session_state.get("sahmk_provider_mode", "SAHMK + Yahoo") == "Yahoo only"
    if _disc_yahoo_only:
        st.info(
            "**Price provider is set to Yahoo only.**  \n"
            "Discovery Console requires SAHMK. Switch to **SAHMK + Yahoo** in ⚙️ Settings "
            "(sidebar) to access this tab.",
            icon="📡",
        )
        return
    if not _sahmk_configured():
        st.error("**SAHMK_API_KEY is not set.** Add it in Secrets to continue.", icon="🔑")
        return

    # ── Symbol + single Run button ────────────────────────────────────────────
    _sc1, _sc2 = st.columns([4, 1])
    with _sc1:
        _sym = st.text_input(
            "Saudi symbol",
            placeholder="e.g. 2222",
            key="disc_symbol",
            label_visibility="collapsed",
        ).strip()
    with _sc2:
        _run = st.button(
            "▶ Run",
            type="primary",
            use_container_width=True,
            key="disc_run_btn",
            disabled=not _sym,
        )

    # ── Fetch + store on click ────────────────────────────────────────────────
    if _run and _sym:
        with st.spinner(f"Fetching data for **{_sym}**…"):
            _result = _disc_download(_sym)
        _saved = [p for p in _result["stored"] if "discovery_report" not in p]
        if _saved:
            st.success(
                f"Stored **{len(_saved)}** dataset(s) for **{_sym}**: "
                + ", ".join(_result["discovery"]["available_datasets"]),
                icon="💾",
            )
        else:
            st.warning(f"No data available for **{_sym}** under the current subscription.", icon="⚠️")

    # ── Stored files table ────────────────────────────────────────────────────
    st.divider()
    _stored = _disc_list(_sym) if _sym else []
    _data_rows = [s for s in _stored if "discovery_report" not in s["slug"]]

    if not _data_rows:
        st.info(
            f"No stored data for **{_sym}**. Enter a symbol and press **▶ Run**." if _sym
            else "Enter a symbol above and press **▶ Run**.",
            icon="📭",
        )
    else:
        for _row in _data_rows:
            _rc1, _rc2 = st.columns([5, 1])
            with _rc1:
                st.markdown(
                    f"**{_row['dataset']}** &nbsp;·&nbsp; "
                    f"`{_row['filename']}` &nbsp;·&nbsp; "
                    f"{_row['fetched_at']} &nbsp;·&nbsp; "
                    f"{_row['size_bytes']:,} bytes"
                )
            with _rc2:
                if st.button("👁 View", key=f"view_{_row['filename']}", use_container_width=True):
                    _toggle = f"_disc_open_{_row['filename']}"
                    st.session_state[_toggle] = not st.session_state.get(_toggle, False)

            # Inline JSON viewer — shown when toggled open
            _toggle_key = f"_disc_open_{_row['filename']}"
            if st.session_state.get(_toggle_key):
                try:
                    with open(_row["filepath"], encoding="utf-8") as _fh:
                        _raw_txt = _fh.read()
                    st.code(_raw_txt, language="json")
                except OSError:
                    st.warning("Could not read file.", icon="⚠️")


# ── Main UI ───────────────────────────────────────────────────────────────────
render_global_header()

# ── Help page gate ─────────────────────────────────────────────────────────────
# When the user opens the user guide from the sidebar button, render the help
# page in place of the normal tabs and stop — no tab code runs.
if st.session_state.get("show_help", False):
    from help_guide import render_help_tab as _render_help
    _render_help()
    st.stop()

if True:
    (tab_fixed, tab_portfolio, tab_alt, tab_accounts, tab_activity,
     tab_analysis, tab_research,
     tab_test) = st.tabs([
        "🏦 Balance Sheet",
        "💼 Portfolio",
        "🏦 Alt Investments",
        "💳 Accounts",
        "📜 Activity",
        "🧭 Analysis",
        "🔍 Research",
        "🧪 Test Runner",
    ])

    _shared_bundle = _load_valuation_bundle(st.session_state.get("global_base_ccy", "SAR"))

    with tab_portfolio:
        _port_page = st.pills(
            "portfolio_nav",
            ["📊 Allocation", "💼 Holdings", "📁 Closed Holdings"],
            default="📊 Allocation",
            label_visibility="collapsed",
            key="portfolio_subnav",
        )
        st.divider()
        if _port_page == "💼 Holdings":
            render_holdings_tab(_shared_bundle)
        elif _port_page == "📁 Closed Holdings":
            render_closed_holdings_tab()
        else:
            render_allocation_tab(_shared_bundle)

    with tab_accounts:
        _acct_page = st.pills(
            "accounts_nav",
            ["💳 Accounts", "💵 Cash Ledger"],
            default="💳 Accounts",
            label_visibility="collapsed",
            key="accounts_subnav",
        )
        st.divider()
        if _acct_page == "💵 Cash Ledger":
            render_cash_ledger_tab()
        else:
            render_accounts_tab()

    with tab_activity:
        _act_page = st.pills(
            "activity_nav",
            ["📜 Transaction History", "💹 Cashflow"],
            default="📜 Transaction History",
            label_visibility="collapsed",
            key="activity_subnav",
        )
        st.divider()
        if _act_page == "💹 Cashflow":
            render_cashflow_tab()
        else:
            render_transactions_tab()

    with tab_analysis:
        _analysis_page = st.pills(
            "analysis_nav",
            ["🧭 Command Center", "📈 Performance", "🎯 Decision Queue", "🛡️ Portfolio Risk", "📝 Thesis Memory", "🌍 Market Intel"],
            default="🧭 Command Center",
            label_visibility="collapsed",
            key="analysis_subnav",
        )
        st.divider()
        if _analysis_page == "📈 Performance":
            render_performance_tab()
        elif _analysis_page == "🎯 Decision Queue":
            render_decision_queue_tab()
        elif _analysis_page == "🛡️ Portfolio Risk":
            render_portfolio_risk_tab()
        elif _analysis_page == "📝 Thesis Memory":
            render_thesis_memory_tab()
        elif _analysis_page == "🌍 Market Intel":
            render_market_intel_tab()
        else:
            render_command_center_tab()

    with tab_research:
        _res_page = st.pills(
            "research_nav",
            ["📄 Filing Search", "🔍 SAHMK Discovery", "🔬 Research Watchlist", "📂 Upload Filing"],
            default="📄 Filing Search",
            label_visibility="collapsed",
            key="research_subnav",
        )
        st.divider()
        if _res_page == "🔍 SAHMK Discovery":
            render_sahmk_discovery_tab()
        elif _res_page == "🔬 Research Watchlist":
            render_portfolio_dashboard()
        elif _res_page == "📂 Upload Filing":
            render_upload_tab()
        else:
            from edgar import EdgarAPIError, get_filings, lookup_company
            from edgar.filings import Filing

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

    with tab_alt:
        render_alt_investments_tab()

    with tab_fixed:
        # ── True Balance Sheet: all asset classes vs all liabilities ──────────
        from portfolio.alt_investments import load_igi_investments as _bs_load_igi
        from portfolio.crowdfunding    import load_cf_accounts     as _bs_load_cf
        from portfolio.fixed_assets    import load_fixed_assets    as _bs_load_fa
        from portfolio.liabilities     import (
            load_liabilities       as _bs_load_lib,
            compute_liabilities_base as _bs_clib,
        )
        from fx_rates import get_rates_for_holdings as _bs_getfx

        _bs_ccy = st.session_state.get("global_base_ccy", "SAR")

        # Investment Portfolio = securities MV only (matches header "Invested" KPI)
        # Cash is tracked separately and added into Total Assets below
        _bs_port = _shared_bundle["val"].holdings_value_base
        _bs_cash = _shared_bundle["val"].cash_value_base

        # Load remaining asset classes
        _bs_igi  = _bs_load_igi()
        _bs_cf   = _bs_load_cf()
        _bs_fa   = {k: v for k, v in _bs_load_fa().items()  if v.status != "Sold"}
        _bs_libs = {k: v for k, v in _bs_load_lib().items() if v.status == "Active"}

        # Extend FX rate map with any new currencies not in the portfolio bundle
        _bs_rates = dict(_shared_bundle["fx"])
        _bs_need  = list({
            *(inv.currency  for inv  in _bs_igi.values()  if inv.status != "Closed"),
            *(acct.currency for acct in _bs_cf.values()   if acct.status == "Active"),
            *(a.currency    for a    in _bs_fa.values()),
            *(l.currency    for l    in _bs_libs.values()),
        } - set(_bs_rates))
        if _bs_need:
            _bs_rates.update(_bs_getfx(_bs_need, _bs_ccy))

        def _bs_rate(ccy: str) -> float:
            r = _bs_rates.get(ccy)
            return r.rate if r else 1.0

        # ── Compute each component ─────────────────────────────────────────
        _bs_alts = round(sum(
            inv.current_value * _bs_rate(inv.currency)
            for inv in _bs_igi.values() if inv.status != "Closed"
        ) + sum(
            acct.current_account_value * _bs_rate(acct.currency)
            for acct in _bs_cf.values() if acct.status == "Active"
        ), 2)

        _bs_fixed = round(sum(
            a.equity * _bs_rate(a.currency) for a in _bs_fa.values()
        ), 2)

        _bs_total_assets = _bs_port + _bs_cash + _bs_alts + _bs_fixed
        _bs_debt         = _bs_clib(_bs_libs, _bs_ccy, _bs_rates)
        _bs_net          = _bs_total_assets - _bs_debt

        # ── Format helper ──────────────────────────────────────────────────
        def _bs_fmt(v: float) -> str:
            # Delegate to the shared canonical formatter so the Balance Sheet
            # KPIs render identically to the Holdings/Allocation KPIs.
            return fmt_money_compact(v)

        _net_col = "#22c55e" if _bs_net >= 0 else "#ef4444"

        # ── Stale-data badge for Balance Sheet KPIs (price-only; FX is user-controlled)
        import time as _bs_t
        _bs_epoch = st.session_state.get("mp_last_refresh_epoch")
        _bs_price_stale = (not _bs_epoch) or (_bs_t.time() - _bs_epoch > 3600)
        _BS_PRICE_BADGE = (
            '<span title="Prices not refreshed in the last hour — tap 🔄 to update." '
            'style="font-size:0.68em;cursor:default;margin-left:3px;">⚠️</span>'
            if _bs_price_stale else ""
        )

        # ── Daily Balance Sheet snapshots + day-over-day deltas ───────────
        try:
            from portfolio.bs_snapshot import record_bs_snapshot_if_needed as _bs_snap_rec
            _bs_prev = _bs_snap_rec(
                {"port": _bs_port, "cash": _bs_cash, "alts": _bs_alts,
                 "fixed": _bs_fixed, "assets": _bs_total_assets,
                 "debt": _bs_debt, "net": _bs_net},
                _bs_ccy,
            )
        except Exception:
            _bs_prev = None

        def _bs_comp_delta(key: str, current: float):
            if _bs_prev is None:
                return None, None
            pv = _bs_prev.get(key)
            if pv is None:
                return None, None
            pv = float(pv)
            if pv == 0.0:
                return None, None
            d = current - pv
            p = d / abs(pv) * 100.0
            return round(d, 2), round(p, 2)

        _bs_d_port_abs,   _bs_d_port_pct   = _bs_comp_delta("port",   _bs_port)
        _bs_d_cash_abs,   _bs_d_cash_pct   = _bs_comp_delta("cash",   _bs_cash)
        _bs_d_alts_abs,   _bs_d_alts_pct   = _bs_comp_delta("alts",   _bs_alts)
        _bs_d_fixed_abs,  _bs_d_fixed_pct  = _bs_comp_delta("fixed",  _bs_fixed)
        _bs_d_assets_abs, _bs_d_assets_pct = _bs_comp_delta("assets", _bs_total_assets)
        _bs_d_debt_abs,   _bs_d_debt_pct   = _bs_comp_delta("debt",   _bs_debt)
        _bs_d_net_abs,    _bs_d_net_pct    = _bs_comp_delta("net",    _bs_net)

        # ── Guard: suppress portfolio snapshot delta when data is unreliable ────
        # Two conditions null out the snapshot-based portfolio Δ:
        #   A) missing_fx — a holding's FX rate defaulted to 1.0, making today's MV
        #      artificially low vs. yesterday's snapshot → phantom large drop.
        #   B) Stale snapshot (>4 days) — covers the Saudi Thu→Sun gap.
        # On startup (no refresh yet) the snapshot value is intentionally shown as
        # a "last saved" indicator; live enrichment below overrides it after 🔄.
        _bs_any_miss_fx = any(
            getattr(r, "missing_fx", False)
            for r in _shared_bundle["val"].per_holding
        )
        _bs_snap_date = (_bs_prev or {}).get("date", "")
        from datetime import date as _bs_dt_date, timedelta as _bs_dt_td
        _bs_cutoff = (_bs_dt_date.today() - _bs_dt_td(days=4)).isoformat()
        if _bs_any_miss_fx or (_bs_snap_date and _bs_snap_date < _bs_cutoff):
            _bs_d_port_abs, _bs_d_port_pct = None, None

        # ── Enrich portfolio headline + delta with live session-cache prices ─────
        _bs_d_port_src = "vs yday" if _bs_prev else ""
        _bs_live_cnt = 0
        try:
            from market_prices import get_all_from_session as _bs_get_sess
            from portfolio.display_metrics import (
                compute_effective_portfolio_mv as _bs_eff_calc,
            )
            _bs_sess = _bs_get_sess()
            if _bs_sess:
                # Same shared helper as the Allocation tab — same val.per_holding
                # + same session cache → identical effective_total and day-Δ on
                # both tabs, guaranteeing Allocation KPI ≡ BS headline by construction.
                _bs_eff_total, _bs_stored, _bs_da, _bs_dp, _bs_live_cnt = _bs_eff_calc(
                    _shared_bundle["val"].per_holding, _bs_sess, _normalize_ticker
                )
                if _bs_live_cnt > 0:
                    _bs_port = _bs_eff_total   # headline: effective live MV
                    _bs_d_port_abs = _bs_da
                    _bs_d_port_pct = _bs_dp
                    _bs_d_port_src = ""
        except Exception:
            pass

        # ── Recompute totals from component sums for math consistency ─────────
        # Only when live enrichment actually fired (_bs_live_cnt > 0): Total
        # Assets and Net Worth must be re-derived from component deltas so the
        # arithmetic adds up visually (e.g. Portfolio +5,944 live → Total
        # Assets must also show ≥+5,944). Skip this recompute for snapshot-only
        # startup deltas — each component already has its own snapshot value.
        if _bs_live_cnt > 0 and _bs_d_port_abs is not None:
            # _bs_port was promoted to effective live MV by the enrichment block above.
            # Recompute headline totals from components NOW so Total Assets and Net
            # Worth are consistent with the updated portfolio value before any delta
            # percentages or donut values are computed below.
            _bs_total_assets = _bs_port + _bs_cash + _bs_alts + _bs_fixed
            _bs_net          = _bs_total_assets - _bs_debt
            _bsc_cash  = _bs_d_cash_abs  if _bs_d_cash_abs  is not None else 0.0
            _bsc_alts  = _bs_d_alts_abs  if _bs_d_alts_abs  is not None else 0.0
            _bsc_fixed = _bs_d_fixed_abs if _bs_d_fixed_abs is not None else 0.0
            _bs_d_assets_abs = round(_bs_d_port_abs + _bsc_cash + _bsc_alts + _bsc_fixed, 2)
            # %-of-previous (current − Δ), matching the portfolio day-Δ and the
            # snapshot-delta convention, so the percentages stay coherent.
            _bs_assets_prev  = _bs_total_assets - _bs_d_assets_abs
            _bs_d_assets_pct = (
                round(_bs_d_assets_abs / _bs_assets_prev * 100.0, 2)
                if _bs_assets_prev > 0 else None
            )
            _bsc_debt = _bs_d_debt_abs if _bs_d_debt_abs is not None else 0.0
            _bs_d_net_abs = round(_bs_d_assets_abs - _bsc_debt, 2)
            _bs_net_prev  = _bs_net - _bs_d_net_abs
            _bs_d_net_pct = (
                round(_bs_d_net_abs / abs(_bs_net_prev) * 100.0, 2)
                if _bs_net_prev != 0 else None
            )

        def _bs_delta_html(
            d_abs, d_pct, label: str = "", invert_color: bool = False,
        ) -> str:
            """Compact day-change sub-line rendered below a Balance Sheet KPI value."""
            _NEUTRAL = ('<div style="font-size:0.7rem;color:#94a3b8;'
                        'margin-top:2px">&#8212;</div>')
            if d_abs is None or d_pct is None:
                return _NEUTRAL
            # Financial practice: zero change is neutral regardless of direction
            # convention (e.g. liabilities showing ▲+0.0% in red is misleading).
            if abs(d_abs) < 0.005:
                return _NEUTRAL
            col_pos = "#22c55e" if not invert_color else "#ef4444"
            col_neg = "#ef4444" if not invert_color else "#22c55e"
            col     = col_pos if d_abs >= 0 else col_neg
            arrow   = "&#9650;" if d_abs >= 0 else "&#9660;"   # ▲ / ▼
            sign    = "+" if d_abs >= 0 else "\u2212"
            pct_s   = f"{sign}{abs(d_pct):.1f}%"
            abs_s   = sign + _bs_fmt(abs(d_abs))
            lbl_s   = (f'&nbsp;<span style="opacity:.5;font-size:0.65rem">'
                       f'{label}</span>' if label else "")
            return (f'<div style="font-size:0.72rem;color:{col};margin-top:3px;'
                    f'white-space:nowrap">{arrow}&thinsp;{pct_s}&nbsp;({abs_s})'
                    f'{lbl_s}</div>')

        _yd = "vs yday" if _bs_prev else ""
        _bs_dh_port   = _bs_delta_html(_bs_d_port_abs,   _bs_d_port_pct,   _bs_d_port_src)
        _bs_dh_cash   = _bs_delta_html(_bs_d_cash_abs,   _bs_d_cash_pct,   _yd)
        _bs_dh_alts   = _bs_delta_html(_bs_d_alts_abs,   _bs_d_alts_pct,   _yd)
        _bs_dh_fixed  = _bs_delta_html(_bs_d_fixed_abs,  _bs_d_fixed_pct,  _yd)
        _bs_dh_assets = _bs_delta_html(_bs_d_assets_abs, _bs_d_assets_pct, _yd)
        _bs_dh_debt   = _bs_delta_html(_bs_d_debt_abs,   _bs_d_debt_pct,   _yd,
                                       invert_color=True)
        _bs_dh_net    = _bs_delta_html(_bs_d_net_abs,    _bs_d_net_pct,    _yd)

        # ── Balance Sheet banner ───────────────────────────────────────────
        st.markdown(
            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
            f'padding:14px 20px 12px;margin-bottom:14px;">'

            # Section label
            f'<div style="font-size:0.7rem;font-weight:700;letter-spacing:0.09em;'
            f'color:#94a3b8;text-transform:uppercase;margin-bottom:10px;">'
            f'Balance Sheet · {_bs_ccy}</div>'

            # Row 1 — Assets
            f'<div style="display:flex;flex-wrap:wrap;gap:0.4rem 2rem;align-items:flex-start;'
            f'padding-bottom:10px;border-bottom:1px solid #e2e8f0;margin-bottom:10px;">'

            f'  <div>'
            f'    <div class="acct-kpi-lbl">&#128200; Investment Portfolio</div>'
            f'    <div class="acct-kpi-val" style="color:#0f172a">{_bs_fmt(_bs_port)}{_BS_PRICE_BADGE}</div>'
            f'    {_bs_dh_port}'
            f'  </div>'
            f'  <div style="color:#94a3b8;font-size:1rem;padding-top:16px">+</div>'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">&#128181; Cash &amp; Banks</div>'
            f'    <div class="acct-kpi-val" style="color:#0f172a">{_bs_fmt(_bs_cash)}</div>'
            f'    {_bs_dh_cash}'
            f'  </div>'
            f'  <div style="color:#94a3b8;font-size:1rem;padding-top:16px">+</div>'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">&#127974; Alt Investments</div>'
            f'    <div class="acct-kpi-val" style="color:#0f172a">{_bs_fmt(_bs_alts)}</div>'
            f'    {_bs_dh_alts}'
            f'  </div>'
            f'  <div style="color:#94a3b8;font-size:1rem;padding-top:16px">+</div>'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">&#127963; Fixed Assets (Equity)</div>'
            f'    <div class="acct-kpi-val" style="color:#0f172a">{_bs_fmt(_bs_fixed)}</div>'
            f'    {_bs_dh_fixed}'
            f'  </div>'
            f'  <div style="color:#94a3b8;font-size:1rem;padding-top:16px">=</div>'
            f'  <div>'
            f'    <div class="acct-kpi-lbl" style="color:#0ea5e9">Total Assets</div>'
            f'    <div class="acct-kpi-val" style="color:#0ea5e9;font-size:1.5rem">'
            f'      {_bs_fmt(_bs_total_assets)}'
            f'    </div>'
            f'    {_bs_dh_assets}'
            f'  </div>'
            f'</div>'

            # Row 2 — Liabilities + Net Worth
            f'<div style="display:flex;flex-wrap:wrap;gap:0.4rem 2rem;align-items:flex-start;">'
            f'  <div>'
            f'    <div class="acct-kpi-lbl">&#128203; Total Liabilities</div>'
            f'    <div class="acct-kpi-val" style="color:#ef4444">({_bs_fmt(_bs_debt)})</div>'
            f'    {_bs_dh_debt}'
            f'  </div>'
            f'  <div style="color:#94a3b8;font-size:1rem;padding-top:16px">=</div>'
            f'  <div>'
            f'    <div class="acct-kpi-lbl" style="color:{_net_col}">&#128142; Net Worth</div>'
            f'    <div class="acct-kpi-val" style="color:{_net_col};font-size:1.65rem;font-weight:700">'
            f'      {_bs_fmt(_bs_net)}'
            f'    </div>'
            f'    {_bs_dh_net}'
            f'  </div>'
            f'</div>'

            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Two-panel charts ───────────────────────────────────────────────
        import plotly.graph_objects as go
        from portfolio.net_worth import load_nw_snapshots as _bs_load_snaps

        _bs_col_chart, _bs_col_trend = st.columns([1, 1], gap="medium")

        # Left — Asset Distribution Donut
        with _bs_col_chart:
            st.markdown(
                '<p style="font-size:0.78rem;font-weight:600;color:#64748b;'
                'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">'
                'Asset Distribution</p>',
                unsafe_allow_html=True,
            )
            _bs_donut_labels = ["📈 Portfolio", "🏦 Alt Investments", "🏛️ Fixed Assets"]
            _bs_donut_values = [_bs_port, _bs_alts, _bs_fixed]
            _bs_donut_colors = ["#0ea5e9", "#8b5cf6", "#f59e0b"]
            # Only show slices with value > 0
            _bs_dv = [(l, v, c) for l, v, c in
                      zip(_bs_donut_labels, _bs_donut_values, _bs_donut_colors) if v > 0]
            if _bs_dv and _bs_total_assets > 0:
                _dl, _dv, _dc = zip(*_bs_dv)
                _bs_donut_fig = go.Figure(go.Pie(
                    labels=list(_dl),
                    values=list(_dv),
                    textinfo="percent",
                    textposition="inside",
                    insidetextorientation="radial",
                    hovertemplate="<b>%{label}</b><br>%{value:,.0f} "
                                  + _bs_ccy + "<br>%{percent:.1f}<extra></extra>",
                    marker=dict(colors=list(_dc), line=dict(color="#ffffff", width=2)),
                    hole=0.42,
                ))
                _bs_donut_fig.update_layout(
                    margin=dict(l=4, r=4, t=8, b=8),
                    height=240,
                    showlegend=True,
                    legend=dict(
                        orientation="v", x=1.01, y=0.5,
                        font=dict(size=11), bgcolor="rgba(0,0,0,0)",
                    ),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    annotations=[dict(
                        text=f"<b>{_bs_ccy}</b>",
                        x=0.5, y=0.5, font_size=12, showarrow=False,
                    )],
                )
                st.plotly_chart(_bs_donut_fig, use_container_width=True,
                                config={"displayModeBar": False})
            else:
                st.info("No asset data to display.", icon="📊")

        # Right — Net Worth Monthly Trend
        with _bs_col_trend:
            st.markdown(
                '<p style="font-size:0.78rem;font-weight:600;color:#64748b;'
                'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">'
                'Net Worth Trend</p>',
                unsafe_allow_html=True,
            )
            _bs_snaps = sorted(
                [s for s in _bs_load_snaps() if s.get("ccy") == _bs_ccy],
                key=lambda x: x["month"],
            )
            # Always include today's computed net worth as the live point
            _today_month = __import__("datetime").date.today().strftime("%Y-%m")
            _bs_trend_pts = [s for s in _bs_snaps if s["month"] != _today_month]
            _bs_trend_pts.append({"month": _today_month, "value": _bs_net, "ccy": _bs_ccy})
            _bs_trend_pts.sort(key=lambda x: x["month"])

            if len(_bs_trend_pts) >= 1:
                import datetime as _bsdt
                _bs_months = [
                    _bsdt.datetime.strptime(p["month"], "%Y-%m").strftime("%b'%y").upper()
                    for p in _bs_trend_pts
                ]
                _bs_values = [p["value"] for p in _bs_trend_pts]
                _line_col  = "#22c55e" if (_bs_values[-1] >= _bs_values[0]) else "#ef4444"
                _bs_trend_fig = go.Figure()
                _bs_trend_fig.add_trace(go.Scatter(
                    x=_bs_months,
                    y=_bs_values,
                    mode="lines+markers",
                    line=dict(color=_line_col, width=2.5, shape="spline"),
                    marker=dict(size=6, color=_line_col,
                                line=dict(color="#ffffff", width=1.5)),
                    fill="tozeroy",
                    fillcolor="rgba(34,197,94,0.08)" if _line_col == "#22c55e"
                              else "rgba(239,68,68,0.08)",
                    hovertemplate="<b>%{x}</b><br>%{y:,.0f} "
                                  + _bs_ccy + "<extra></extra>",
                ))
                _bs_trend_fig.update_layout(
                    margin=dict(l=4, r=4, t=8, b=8),
                    height=240,
                    xaxis=dict(
                        showgrid=False, zeroline=False, type="category",
                        tickfont=dict(size=10), tickangle=-30,
                    ),
                    yaxis=dict(
                        showgrid=True, zeroline=False,
                        gridcolor="#f1f5f9", tickfont=dict(size=10),
                        tickformat=".2s",
                    ),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                )
                st.plotly_chart(_bs_trend_fig, use_container_width=True,
                                config={"displayModeBar": False})
            else:
                st.info("Net worth trend will appear after the first month of data.", icon="📈")

        # ── Sub-page pills ─────────────────────────────────────────────────
        _bs_page = st.pills(
            "bs_nav",
            ["🏛️ Assets", "📋 Liabilities"],
            default="🏛️ Assets",
            label_visibility="collapsed",
            key="bs_subnav",
        )
        st.divider()
        if _bs_page == "📋 Liabilities":
            render_liabilities_tab()
        else:
            render_fixed_assets_tab()

    with tab_test:
        render_test_runner_tab()
