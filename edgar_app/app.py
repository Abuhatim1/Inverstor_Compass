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
    page_title="بوصلة",
    page_icon="🧭",
    layout="wide",
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
        font-size: 0.68rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        line-height: 1.6;
        white-space: nowrap;
    }
    .gh-val-big { font-size: 2rem;    font-weight: 700; line-height: 1.1; white-space: nowrap; }
    .gh-val-med { font-size: 1.5rem;  font-weight: 600; line-height: 1.1; white-space: nowrap; }
    .gh-val-sm  { font-size: 1.25rem; font-weight: 600; line-height: 1.1; }
    .gh-val-xs  { font-size: 1rem;    color: #6b7280;   line-height: 1.4; }
    .gh-pct     { font-size: 0.82rem; font-weight: 500; }

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
        .gh-val-big  { font-size: 1.35rem !important; }
        .gh-val-med  { font-size: 1.05rem !important; }
        .gh-val-sm   { font-size: 0.9rem  !important; }
        .gh-val-xs   { font-size: 0.8rem  !important; }
        .gh-pct      { font-size: 0.7rem  !important; }
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
        font-size: 0.65rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        line-height: 1.6;
    }
    .acct-kpi-val {
        font-size: 1.15rem;
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
        .gh-val-big { font-size: 1.1rem  !important; }
        .gh-val-med { font-size: 0.92rem !important; }
        .gh-val-sm  { font-size: 0.8rem  !important; }
        .gh-val-xs  { font-size: 0.72rem !important; }
        .gh-lbl     { font-size: 0.55rem !important; }
        .gh-pct     { font-size: 0.68rem !important; }

        /* Compact tab bar buttons */
        [data-testid="stTabs"] button[role="tab"] {
            padding: 0.3rem 0.55rem !important;
            font-size: 0.72rem !important;
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

    # ── Market Price Auto-Refresh ─────────────────────────────────────────────
    st.divider()
    st.caption("📡 **Market Price Auto-Refresh**")
    from market_prices import market_session_label as _msl, is_us_market_open as _mko
    _si, _sl = _msl()
    st.caption(f"{_si} {_sl}")

    mp_auto_on = st.toggle(
        "Auto-refresh prices",
        value=False,
        key="mp_auto_on",
        help="Automatically re-fetches live prices at the chosen interval. "
             "Never triggers AI analysis.",
    )
    mp_interval = st.selectbox(
        "Interval",
        ["1 minute", "5 minutes", "15 minutes"],
        index=1,
        key="mp_interval",
        disabled=not mp_auto_on,
    )
    _last_ts = st.session_state.get("mp_last_refresh")
    if _last_ts:
        st.caption(f"Last refresh: **{_last_ts}**")
        if mp_auto_on:
            import time as _t
            _ivl_secs = {"1 minute": 60, "5 minutes": 300, "15 minutes": 900}.get(
                mp_interval, 300
            )
            _ep       = st.session_state.get("mp_last_refresh_epoch", 0.0)
            _secs_left = max(0, int(_ep + _ivl_secs - _t.time()))
            if _secs_left > 0:
                st.caption(f"Next refresh: ~{_secs_left}s")
            else:
                st.caption("Next refresh: imminent")
    else:
        st.caption("Prices not yet fetched this session.")

    if mp_auto_on and not _mko():
        st.caption("🔴 Market closed — prices may be delayed")

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
            set(list(load_portfolio().keys()) + list(load_holdings().keys()))
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
    for ticker, md in fetched.items():
        if ticker not in _h:
            continue  # watchlist-only tickers are not written to holdings
        try:
            if md.is_ok and md.current_price:
                update_current_price(ticker, float(md.current_price), source="yfinance")
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
    Records the actual provider ("SAHMK", "yfinance", "cached", "manual").
    Returns (ok_list, fail_list).
    """
    from portfolio import update_current_price, load_holdings as _lh
    _h = holdings if holdings is not None else _lh()
    ok_list:   list[str] = []
    fail_list: list[str] = []
    for ticker, rp in routed.items():
        if ticker not in _h:
            continue
        try:
            if rp.is_ok and rp.price:
                update_current_price(ticker, float(rp.price), source=rp.provider)
                ok_list.append(ticker)
            else:
                fail_list.append(ticker)
        except Exception:
            fail_list.append(ticker)
    return ok_list, fail_list


def _run_price_refresh(*, force: bool = True) -> int:
    """
    Refresh market prices for every known ticker using the multi-provider router.

    Holdings with an exchange_symbol go through SAHMK first; all others fall
    through to yfinance then cached/manual.  Watchlist-only tickers are still
    fetched via yfinance and stored in the session cache for UI display.
    Returns the count of tickers successfully updated.
    """
    from market_prices import refresh_all_prices, save_to_session
    from market_data_router import refresh_holdings_prices
    from portfolio import load_holdings as _lh_inner
    try:
        # ── Routed refresh for actual holdings ────────────────────────────────
        _holdings_inner = _lh_inner()
        ok_count = 0
        if _holdings_inner:
            routed = refresh_holdings_prices(_holdings_inner, force=force)
            ok_list, _ = _apply_routed_prices(routed, _holdings_inner)
            ok_count = len(ok_list)

        # ── yfinance session cache for watchlist / price-debug UI ─────────────
        raw_tickers = _collect_all_tickers()
        if raw_tickers:
            ticker_map = {_normalize_ticker(t): t for t in raw_tickers}
            results = refresh_all_prices(list(ticker_map.keys()), force=force)
            save_to_session(results)

        return ok_count
    except Exception:
        return 0


# 1. Automatic fetch on first load of this browser session
if "mp_initial_done" not in st.session_state:
    st.session_state["mp_initial_done"] = True
    if _collect_all_tickers():          # only if the user has tickers already
        _run_price_refresh(force=False) # use cache if still warm (60 s TTL)

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
    _existing = load_holdings().get(_ptk)
    if _existing:
        st.info(
            f"**{_ptk}** is already in your Holdings "
            f"({_existing.quantity:g} shares @ {_existing.avg_cost:.4f}). "
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
            st.caption(f"Opening cost: **{_ptotal:,.4f} {_pccy}**")
    else:
        st.caption(f"Opening cost: **{_ptotal:,.4f} {_pccy}**")

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
                        update_current_price(_ptk_clean, float(_pprice), source="yfinance")
                    if _paid:
                        try:
                            _promo_upd_cash(_paid, -_ptotal)
                        except Exception:
                            pass
                    for _dk in _PROMO_KEYS:
                        st.session_state.pop(_dk, None)
                    st.toast(
                        f"**{_ptk_clean}** promoted to Holdings! "
                        f"{float(_pqty):.4f} shares @ {_pccy} {float(_pcost):.4f}",
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
                            f"{md.day_indicator} **{md.current_price:.2f} {md.currency}**"
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
                _wl_existing = holdings.get(ticker)
                if _wl_existing:
                    st.caption(
                        f"✅ Already held · {_wl_existing.quantity:g} shares @ "
                        f"{_wl_existing.avg_cost:.4f} · "
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
        rc1.metric(f"Holdings ({val.base_currency})", f"{val.holdings_value_base:,.2f}")
        rc2.metric(f"Cash ({val.base_currency})",     f"{val.cash_value_base:,.2f}")
        rc3.metric("Total Portfolio",                  f"{val.total_portfolio_value_base:,.2f}")
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
    _excluded: list[str] = []
    _rows: list[dict] = []
    for _r in val.per_holding:
        _h = holdings.get(_r.ticker)
        if _h is None:
            continue
        if _r.missing_price or _r.missing_fx:
            _excluded.append(_r.ticker)
            continue
        if _r.base_market_value <= 0:
            continue
        _rows.append({
            "Ticker":  _r.ticker,
            "Company": getattr(_h, "company_name", _r.ticker) or _r.ticker,
            "Market":  getattr(_h, "market",  "Other"),
            "Sector":  getattr(_h, "sector",  "Other"),
            "CCY":     _r.local_currency,
            "_mv":     _r.base_market_value,
            "_cb":     _r.base_cost_basis,
            "_wt":     _r.invested_weight_pct,
        })

    if _excluded:
        st.warning(
            "Excluded from allocation due to missing price or FX: "
            f"**{', '.join(_excluded)}**",
            icon="⚠️",
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
    _all_sectors   = sorted(_mkt_df["Sector"].unique().tolist())
    _all_ccys_u    = sorted(_mkt_df["CCY"].unique().tolist())
    _all_companies = sorted(_mkt_df["Company"].unique().tolist())

    # Purge stale child filter state — remove any stored values that no longer
    # exist within the new market scope (prevents false "No holdings match" msg)
    for _k, _valid in [
        ("alloc_ms_sector", _all_sectors),
        ("alloc_ms_ccy",    _all_ccys_u),
        ("alloc_ms_asset",  _all_companies),
    ]:
        _stored = st.session_state.get(_k)
        if _stored and not all(v in _valid for v in _stored):
            st.session_state.pop(_k, None)

    # ── Chart view ────────────────────────────────────────────────────────────
    _view = st.selectbox(
        "Chart view",
        ["By Asset", "By Sector", "By Market", "By Currency"],
        key="alloc_chart_view",
    )
    _grp = {"By Asset": "Company", "By Sector": "Sector",
            "By Market": "Market", "By Currency": "CCY"}[_view]

    # ── Multi-select filters (collapsible to keep the UI compact) ────────────
    with st.expander("🔍 Filters", expanded=False):
        _fc1, _fc2 = st.columns(2)
        with _fc1:
            _sel_sectors   = st.multiselect(
                "Sector", _all_sectors,
                default=st.session_state.get("alloc_ms_sector", _all_sectors),
                key="alloc_ms_sector",
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
            for _k in ("alloc_ms_sector", "alloc_ms_ccy", "alloc_ms_asset"):
                st.session_state.pop(_k, None)
            st.rerun()
    # Read current child selections (fall back to all scoped options)
    _sel_sectors   = st.session_state.get("alloc_ms_sector",   _all_sectors)
    _sel_ccys_u    = st.session_state.get("alloc_ms_ccy",      _all_ccys_u)
    _sel_companies = st.session_state.get("alloc_ms_asset",    _all_companies)

    # ── Apply filters — base is market-scoped; child filters applied on top ───
    _filt = _mkt_df.copy()
    if _sel_sectors   and set(_sel_sectors)   != set(_all_sectors):
        _filt = _filt[_filt["Sector"].isin(_sel_sectors)]
    if _sel_ccys_u    and set(_sel_ccys_u)    != set(_all_ccys_u):
        _filt = _filt[_filt["CCY"].isin(_sel_ccys_u)]
    if _sel_companies and set(_sel_companies) != set(_all_companies):
        _filt = _filt[_filt["Company"].isin(_sel_companies)]

    if _filt.empty:
        st.info("No holdings match the selected filters. Use the Reset button to clear.", icon="🔍")
        return

    # ── Filtered Allocation Summary ───────────────────────────────────────────
    _fas_mv       = _filt["_mv"].sum()
    _fas_cb       = _filt["_cb"].sum()
    _fas_pnl      = _fas_mv - _fas_cb
    _fas_pnl_pct  = (_fas_pnl / _fas_cb * 100) if _fas_cb > 0 else 0.0
    _total_mv_all = getattr(val, "holdings_value_base", _fas_mv)
    _fas_weight   = (_fas_mv / _total_mv_all * 100) if _total_mv_all > 0 else 0.0
    _fas_n        = len(_filt)
    _pnl_color    = "normal" if _fas_pnl >= 0 else "inverse"
    _pnl_sign     = "+" if _fas_pnl >= 0 else ""

    def _fmt_compact(v: float) -> str:
        """Round to nearest K or M for compact display; keep sign."""
        av = abs(v)
        if av >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if av >= 10_000:
            return f"{v / 1_000:.0f}K"
        return f"{v:,.0f}"

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
    <div class="fas-kpi-val">{_fmt_compact(_fas_mv)}</div>
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
    _hov = "<b>%{label}</b><br>MV: %{value:,.0f} " + base_ccy + "<br>Share: %{percent:.1f}<extra></extra>"
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
        "By Asset":    "alloc_ms_asset",
        "By Sector":   "alloc_ms_sector",
        "By Market":   "alloc_ms_market",
        "By Currency": "alloc_ms_ccy",
    }
    _ms_all_map = {
        "By Asset":    _all_companies,
        "By Sector":   _all_sectors,
        "By Market":   _all_markets,
        "By Currency": _all_ccys_u,
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
        _pdf.cell(0, 6, f"Allocation Detail — {len(_disp)} holding(s)  ·  {base_ccy} {_total_mv:,.0f} total", ln=True)
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
                f"{_row[_mv_col_label]:,.0f}",
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

    _ex1, _ex2 = st.columns(2)
    with _ex1:
        if _report_bytes:
            _btn_lbl = (
                "⬇️ Export Report (PDF)"
                if _report_mime == "application/pdf"
                else "⬇️ Export Chart (PNG)"
            )
            st.download_button(
                _btn_lbl,
                data=_report_bytes,
                file_name=_report_name,
                mime=_report_mime,
                key="alloc_dl_report",
                use_container_width=True,
            )
    with _ex2:
        _csv_io = _io.StringIO()
        _disp.to_csv(_csv_io, index=False, float_format="%.2f")
        st.download_button(
            "⬇️ Export Table (CSV)",
            data=_csv_io.getvalue(),
            file_name=f"allocation_{_slug}_{_ts_file}.csv",
            mime="text/csv",
            key="alloc_dl_csv",
            use_container_width=True,
        )

    # ── Filtered asset table ──────────────────────────────────────────────────
    st.caption(
        f"**{_view}** · {len(_disp)} holding(s) · "
        + (f"Filtered — {_filter_str}" if _active_filters else f"{base_ccy} {_total_mv:,.0f} total")
    )
    st.dataframe(
        _disp,
        hide_index=True,
        use_container_width=True,
        column_config={
            _mv_col_label: st.column_config.NumberColumn(_mv_col_label, format="%,.0f"),
            "Weight %":    st.column_config.NumberColumn("Weight %",    format="%.1f%%"),
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
    wt_map    = {r.ticker: r.invested_weight_pct for r in val.per_holding}
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

        # ── Build the holdings table ───────────────────────────────────────────
        _mv_col       = f"MV ({_base_ccy})"
        rows          = []
        _ticker_order: list[str] = []
        manual_tickers: list[str] = []

        for ticker, h in sorted(holdings.items()):
            if h.quantity <= 1e-9:          # hide fully-closed positions
                continue
            has_tk  = getattr(h, "has_ticker", True)
            ccy     = getattr(h, "currency", "USD")
            fx_r    = _fx.get(ccy)
            fx_rate = fx_r.rate if fx_r else 1.0
            mv_base = round(h.market_value * fx_rate, 2)
            pnl_pct = h.unrealized_pnl_pct
            status  = "🟢" if pnl_pct > 0.01 else ("🔴" if pnl_pct < -0.01 else "⚪")

            norm_tk = _normalize_ticker(ticker)
            md = live_cache.get(norm_tk) or live_cache.get(ticker)

            if not has_tk:
                manual_tickers.append(ticker)

            _src_raw   = getattr(h, "price_source", "manual") or "manual"
            _src_label = {"SAHMK": "SAHMK", "yfinance": "Yahoo",
                          "cached": "Cached", "manual": "Manual"}.get(
                _src_raw, _src_raw.capitalize())

            _aid       = getattr(h, "default_account_id", "") or ""
            _acct_obj  = _all_accounts.get(_aid)
            _acct_name = _acct_obj.account_name if _acct_obj else ("Unassigned" if not _aid else "Unknown")

            _ticker_order.append(ticker)
            rows.append({
                " ":        status,
                "Company":  h.company_name or ticker,
                "Ticker":   ticker,
                "Qty":      round(h.quantity, 4),
                "Avg Cost": round(h.avg_cost, 4),
                "Price":    round(h.current_price, 4),
                _mv_col:    mv_base,
                "P&L %":    round(pnl_pct, 2),
                "Wt %":     round(_wt_map.get(ticker, 0.0), 1),
                "CCY":      ccy,
                "Src":      _src_label,
                "Account":  _acct_name,
            })

        _tbl_sel = st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                " ":        st.column_config.TextColumn(" ", width="small"),
                "Company":  st.column_config.TextColumn("Company"),
                "Ticker":   st.column_config.TextColumn("Ticker", width="small"),
                "Qty":      st.column_config.NumberColumn("Qty",      format="%.4f"),
                "Avg Cost": st.column_config.NumberColumn("Avg Cost", format="%.4f"),
                "Price":    st.column_config.NumberColumn("Price",    format="%.4f"),
                _mv_col:    st.column_config.NumberColumn(_mv_col,    format="%,.0f"),
                "P&L %":    st.column_config.NumberColumn("P&L %",   format="%+.2f%%"),
                "Wt %":     st.column_config.NumberColumn("Wt %",    format="%.1f%%", width="small"),
                "CCY":      st.column_config.TextColumn("CCY", width="small"),
                "Src":      st.column_config.TextColumn("Src", width="small"),
                "Account":  st.column_config.TextColumn("Account"),
            },
        )
        st.caption("👆 Tap a row to select it, then use the action bar below  ·  🟢 profit  🔴 loss  ⚪ flat")

        # ── Table action buttons ───────────────────────────────────────────────
        _tab1, _tab2, _tab3, _tab4 = st.columns(4)
        with _tab1:
            # Refresh prices via multi-provider router (SAHMK → yfinance → cached)
            if st.button("🔄 Refresh Prices", key="refresh_mp_holdings",
                         use_container_width=True,
                         help="Fetch live prices (SAHMK → Yahoo Finance → cached)."):
                from market_data_router import refresh_holdings_prices as _rr
                _has_tk_holdings = {
                    t: h for t, h in holdings.items()
                    if getattr(h, "has_ticker", True)
                }
                with st.spinner(f"Fetching {len(_has_tk_holdings)} price(s)…"):
                    _routed = _rr(_has_tk_holdings, force=True)
                # Also update yfinance session cache for the debug tab
                _ticker_map = {_normalize_ticker(t): t for t in _has_tk_holdings}
                _fetched_norm = refresh_all_prices(list(_ticker_map.keys()), force=False)
                save_to_session(_fetched_norm)
                _ok_list, _fail_list = _apply_routed_prices(_routed, holdings)
                _s_lbl = market_session_label()[1]
                st.toast(
                    f"Updated {len(_ok_list)} · Failed {len(_fail_list)} · {_s_lbl}",
                    icon="✅" if _ok_list else "⚠️",
                )
                st.rerun()
        with _tab2:
            # Download CSV
            import io as _io
            _csv_buf = _io.StringIO()
            _csv_buf.write(
                "ticker,company_name,asset_type,market,sector,currency,"
                "opening_quantity,avg_cost,current_price,market_value,unrealized_pnl_pct\n"
            )
            for _r in rows:
                _tk2 = _r["Ticker"]
                _hh  = holdings.get(_tk2)
                if _hh:
                    _csv_buf.write(
                        f"{_tk2},"
                        f"{_hh.company_name},"
                        f"{getattr(_hh,'asset_type','Stock')},"
                        f"{getattr(_hh,'market','US')},"
                        f"{getattr(_hh,'sector','Other')},"
                        f"{getattr(_hh,'currency','USD')},"
                        f"{_hh.quantity},"
                        f"{_hh.avg_cost},"
                        f"{_hh.current_price},"
                        f"{_hh.market_value},"
                        f"{_hh.unrealized_pnl_pct}\n"
                    )
            st.download_button(
                "⬇️ Download CSV",
                data=_csv_buf.getvalue(),
                file_name=f"holdings_{date.today()}.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_holdings_csv",
            )
        _add_new_clicked = False
        with _tab3:
            if st.button("⬆️ Bulk Upload", key="open_bulk_upload_btn",
                         use_container_width=True,
                         help="Upload multiple new positions from a CSV file."):
                _dlg_bulk_upload()
        with _tab4:
            if st.button("➕ Add New Position", key="open_add_new_btn",
                         type="primary", use_container_width=True,
                         help="Open a single new position with a BUY transaction."):
                _add_new_clicked = True

        # ── Secondary diagnostics ──────────────────────────────────────────────
        # FX rate warnings
        if _manual_fx:
            st.warning(
                f"Totals in **{_base_ccy}** use estimated FX for: "
                f"**{', '.join(_manual_fx)}**. Click 💱 to refresh.",
                icon="💱",
            )
        elif _val.warnings:
            for _w in _val.warnings:
                st.warning(_w, icon="⚠️")
        else:
            _s_icon, _s_lbl2 = market_session_label()
            st.caption(
                f"{_s_icon} {_s_lbl2}  ·  "
                f"Invested {_val.invested_allocation_pct:.1f}%  ·  "
                f"Cash {_val.cash_allocation_pct:.1f}%"
            )


        # ── Manual price update (untickered assets only) ───────────────────────
        if manual_tickers:
            with st.expander(
                f"📝 Update manual prices ({len(manual_tickers)} asset(s))",
                expanded=False,
            ):
                st.caption(
                    "These assets have no Yahoo Finance ticker. "
                    "Enter a price and click Save."
                )
                for tk in sorted(manual_tickers):
                    h_m = holdings[tk]
                    mp_c1, mp_c2 = st.columns([3, 1])
                    with mp_c1:
                        new_p = st.number_input(
                            f"{tk}  ·  {h_m.company_name}",
                            value=float(h_m.current_price or 0.0),
                            min_value=0.0,
                            step=0.01,
                            format="%.4f",
                            key=f"mp_manual_{tk}",
                        )
                    with mp_c2:
                        st.write("")
                        if st.button("Save", key=f"mp_save_{tk}",
                                     use_container_width=True):
                            if abs(new_p - float(h_m.current_price or 0.0)) > 1e-9:
                                update_current_price(tk, new_p, source="manual")
                                st.toast(f"{tk} price updated to {new_p:.4f}", icon="💾")
                            st.rerun()

    # ── Account helpers (needed by all dialogs, including Add New) ───────────
    from portfolio.accounts import active_accounts as _active_accts_fn, account_display_name as _acct_dn
    from portfolio.accounts import load_accounts as _load_accts_raw, update_account_cash as _upd_cash

    def _acct_pairs_for(currency: str | None = None):
        """Return [(account_id, Account)] for active accounts. Never raises."""
        try:
            return list(_active_accts_fn(currency).items())
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
                        f"| {_val.currency}  {_val.current_price:.4f}"
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
            _ad_tk     = st.text_input("Ticker / Asset ID", key="ahn_tk_confirm",
                                       help="Auto-filled after Validate. Edit if needed.")
            _ad_name   = st.text_input("Company / Asset name", key="ahn_name")
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

        # ── Account (filtered by selected currency) ───────────────────────────
        _pairs_ccy = _acct_pairs_for(currency=_ad_ccy)
        _pairs_all = _acct_pairs_for()
        _use_pairs = _pairs_ccy if _pairs_ccy else _pairs_all
        _acct_opts = {"": f"— no account —"}
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
        if not _ad_aid:
            st.warning("An account is required to open a position.", icon="⚠️")

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

        # ── Duplicate guard ───────────────────────────────────────────────────
        _ad_tk_clean = _ad_tk.strip().replace(" ", "_").upper()
        _ad_tk_norm  = _ntk(_ad_tk_clean) if _ad_tk_clean else ""
        _open_norms  = {_ntk(k) for k, h in holdings.items() if h.quantity > 1e-9}
        _is_dup      = bool(_ad_tk_clean and _ad_tk_norm in _open_norms)

        if _is_dup:
            st.error(
                f"**{_ad_tk_clean}** already has an open position.  \n"
                "Use that row's **Buy / Edit / Sell** actions to modify it. "
                "A new position can only be opened once the existing one is fully closed.",
                icon="🚫",
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
            # Cash check blocks only Mode B; Mode A is always allowed
            _submit_disabled = (
                not _ad_tk_clean
                or _is_dup
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
                            # Persist extra metadata
                            upsert_holding(
                                ticker=_ad_tk_clean,
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
                        upsert_holding(
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
                                _ad_tk_clean, _ad_price,
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
                            f"{_ad_qty:.4f} shares @ {_ad_cost:.4f} {_ad_ccy}",
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
                f"**{dlg_ticker}** · {dlg_h.company_name}  "
                f"| {dlg_h.quantity:,.4f} shares @ avg {dlg_h.avg_cost:.4f} {_d_ccy}"
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
                st.caption(f"Est. new avg cost: **{_new_avg:.4f} {_d_ccy}**")
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
                            ticker=dlg_ticker, side="BUY",
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
                                f"Bought {_d_qty:.4f} × {dlg_ticker} @ {_d_price:.4f}  "
                                f"· New avg cost: {_h2.avg_cost:.4f}",
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
            _d_ccy   = getattr(dlg_h, "currency", "USD")
            _d_avail = float(dlg_h.quantity)
            _d_pairs = _acct_pairs_for()
            _d_labels = ["— no account —"] + [_acct_dn(a) for _, a in _d_pairs]
            _d_ids    = [""] + [aid for aid, _ in _d_pairs]
            st.caption(
                f"**{dlg_ticker}** · {dlg_h.company_name}  "
                f"| **{_d_avail:,.4f}** shares available @ avg cost {dlg_h.avg_cost:.4f} {_d_ccy}"
            )
            _d_full = st.checkbox("Close full position", value=True)
            if _d_full:
                _d_qty = _d_avail
                st.info(f"Will sell all {_d_avail:,.4f} shares.")
            else:
                _d_qty = st.number_input(
                    "Qty to sell",
                    min_value=0.0001, max_value=_d_avail + 0.0001,
                    value=min(1.0, _d_avail), step=1.0, format="%.4f",
                )
            _d_price = st.number_input(
                "Sale price / share",
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
                "Record correction only — skip cash credit",
                help="Use this to reduce the holding without crediting any account cash.",
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
                            ticker=dlg_ticker, side="SELL",
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
                                f"{'Closed' if _fully else 'Sold'} {_final_qty:,.4f} × {dlg_ticker} "
                                f"@ {_d_price:.4f}  · P&L: {_rpnl:+,.2f} {_d_ccy}",
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

        # ── Dialog: Edit ─────────────────────────────────────────────────────
        @st.dialog("✏️ Edit Holding")
        def _dlg_edit(dlg_ticker: str, dlg_h):
            from portfolio.accounts import load_accounts as _ed_load_accts, account_display_name as _ed_acct_dn
            st.caption(
                f"**{dlg_ticker}** — direct field correction.  "
                "Transaction history is not affected."
            )
            _e_name  = st.text_input("Company name", value=dlg_h.company_name or "")
            _e_qty   = st.number_input(
                "Quantity (correction)", value=float(dlg_h.quantity),
                min_value=0.0, step=1.0, format="%.4f",
            )
            _e_avg   = st.number_input(
                "Avg cost (correction)", value=float(dlg_h.avg_cost),
                min_value=0.0, step=0.01, format="%.4f",
            )
            _e_price = st.number_input(
                "Current price", value=float(dlg_h.current_price),
                min_value=0.0, step=0.01, format="%.4f",
            )
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
            # Build options: "" sentinel first (placeholder), then real IDs
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
                            ticker=dlg_ticker,
                            company_name=_e_name or None,
                            quantity=float(_e_qty),
                            avg_cost=float(_e_avg),
                            current_price=float(_e_price),
                            notes=_e_notes or None,
                            exchange_symbol=_e_exsym.strip() or None,
                            default_account_id=_e_aid,
                        )
                        st.toast(f"{dlg_ticker} updated", icon="💾")
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
                f"Remove **{dlg_ticker}** ({dlg_h.company_name}) from your holdings?  "
                "Transaction history is preserved. This only removes the active position.",
                icon="⚠️",
            )
            _conf_check = st.checkbox("I understand — this cannot be undone")
            _conf_text  = st.text_input(f"Type  {dlg_ticker}  to confirm")
            _ready = _conf_check and _conf_text.strip().upper() == dlg_ticker.upper()
            _xb1, _xb2 = st.columns(2)
            with _xb1:
                if st.button(
                    "🗑️ Delete", type="primary",
                    use_container_width=True, disabled=not _ready,
                ):
                    try:
                        soft_delete_holding(dlg_ticker)
                        st.toast(f"{dlg_ticker} removed from holdings", icon="🗑️")
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
            ALLOWED_ASSET_TYPES = {
                "Stock", "ETF", "Fund", "Crypto", "Bond",
                "Cash Equivalent", "Commodity", "Other",
            }
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
            _open_norms  = {_ntk_bu(k) for k, h in _ex_holdings.items() if h.quantity > 1e-9}
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
                        _re.append(
                            f"ticker '{_raw_tk}' already has an open holding — "
                            "use row actions to update it"
                        )
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
                                        _v["ticker"],
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
            _st = _ticker_order[_si] if _si < len(_ticker_order) else None
            _sh = holdings.get(_st) if _st else None
            if _st and _sh:
                with st.container(border=True):
                    _abar_info, _ab1, _ab2, _ab3, _ab4 = st.columns([3, 1, 1, 1, 1])
                    with _abar_info:
                        _ab_ccy = getattr(_sh, "currency", "USD")
                        st.markdown(
                            f"**{_st}** · {_sh.company_name}  "
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
                            _dlg_sell(_st, _sh)
                    with _ab3:
                        if st.button("✏️ Edit", key="tbl_edit_btn",
                                     use_container_width=True):
                            _dlg_edit(_st, _sh)
                    with _ab4:
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
            f'    <div class="acct-kpi-val">{_total_cash:,.0f}</div>'
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
    """Buy / Sell transaction recording and full history."""
    from portfolio import (
        ASSET_TYPES, CURRENCIES, DEFAULT_SECTORS, MARKETS,
        load_holdings, load_transactions, load_portfolio, record_transaction,
    )
    from portfolio.accounts import (
        load_accounts, active_accounts, account_display_name,
    )
    from portfolio.cash_ledger import append_cash_entry
    import pandas as pd
    from datetime import date as _date_cls

    st.header("🔁 Transactions")
    st.caption(
        "Record buy and sell transactions. "
        "Cash is automatically debited / credited to the linked account."
    )

    holdings  = load_holdings()
    watchlist = load_portfolio()
    accounts  = load_accounts()
    _act_accts = {aid: a for aid, a in accounts.items() if a.active}

    # ── Record form ───────────────────────────────────────────────────────────
    with st.expander("🔁 Record Buy / Sell", expanded=True):
        tr1, tr2 = st.columns(2)
        with tr1:
            all_tickers = sorted(set(holdings.keys()) | set(watchlist.keys()))
            if all_tickers:
                _txn_src = st.radio("Source", ["From existing", "New ticker"],
                                    horizontal=True, key="txn_tab_src")
                if _txn_src == "From existing":
                    txn_ticker = st.selectbox("Ticker", all_tickers, key="txn_tab_tk_sel")
                else:
                    txn_ticker = st.text_input("Ticker", key="txn_tab_tk_txt").strip().upper()
            else:
                txn_ticker = st.text_input("Ticker", key="txn_tab_tk_txt").strip().upper()

            txn_side  = st.radio("Side", ["BUY", "SELL"], horizontal=True, key="txn_tab_side")
            txn_qty   = st.number_input("Quantity",   min_value=0.0, step=1.0,         key="txn_tab_qty")
            txn_price = st.number_input("Price/unit", min_value=0.0, step=0.01, format="%.4f", key="txn_tab_price")
            txn_fees  = st.number_input(
                "Fees", min_value=0.0, step=1.0, format="%.2f", key="txn_tab_fees",
                help="Broker fees. 0 if none.",
            )

        with tr2:
            txn_date  = st.date_input("Date", value=_date_cls.today(), key="txn_tab_date")
            txn_notes = st.text_area("Notes (optional)", key="txn_tab_notes", height=70)

            # Detect holding's currency for account filter
            _h_ccy = "USD"
            if txn_ticker and txn_ticker in holdings:
                _h_ccy = getattr(holdings[txn_ticker], "currency", "USD")

            # Account selector — filtered by currency
            _matching = {aid: a for aid, a in _act_accts.items()
                         if a.base_currency == _h_ccy}
            _acct_opts = {"(none — skip cash tracking)": None}
            _acct_opts.update({account_display_name(a): aid for aid, a in _matching.items()})

            if _act_accts and not _matching:
                st.warning(
                    f"No active **{_h_ccy}** account found. "
                    "Add one in the **💳 Accounts** tab.",
                    icon="⚠️",
                )
            _acct_lbl = st.selectbox(
                f"Account ({_h_ccy})", list(_acct_opts.keys()), key="txn_tab_acct",
            )
            txn_account_id = _acct_opts.get(_acct_lbl)

            # Cash impact preview
            if txn_qty > 0 and txn_price > 0:
                _gross = txn_qty * txn_price
                if txn_side == "BUY":
                    st.info(f"Cash out: **{_h_ccy} {_gross + txn_fees:,.2f}**", icon="💸")
                else:
                    st.info(f"Cash in: **{_h_ccy} {_gross - txn_fees:,.2f}**",  icon="💰")

            # Metadata for new holdings created by BUY
            new_h_market   = st.selectbox("Market (new holding)", MARKETS,       key="txn_tab_mkt")
            new_h_sector   = st.selectbox("Sector (new holding)", DEFAULT_SECTORS, key="txn_tab_sec")
            new_h_type     = st.selectbox("Type   (new holding)", ASSET_TYPES,   key="txn_tab_type")
            _ccy_idx = CURRENCIES.index(_h_ccy) if _h_ccy in CURRENCIES else 0
            new_h_currency = st.selectbox("Currency (new holding)", CURRENCIES,
                                          index=_ccy_idx, key="txn_tab_cur")

        if st.button("🔁 Record transaction", type="primary", key="txn_tab_submit"):
            if not txn_ticker:
                st.error("Ticker is required.")
            elif txn_qty <= 0:
                st.error("Quantity must be > 0.")
            else:
                _cn = (
                    watchlist[txn_ticker].company_name if txn_ticker in watchlist
                    else holdings[txn_ticker].company_name if txn_ticker in holdings
                    else txn_ticker
                )
                txn, updated, err = record_transaction(
                    ticker=txn_ticker, side=txn_side,
                    quantity=float(txn_qty), price=float(txn_price),
                    txn_date=txn_date.isoformat(), notes=txn_notes,
                    company_name=_cn, market=new_h_market, sector=new_h_sector,
                    asset_type=new_h_type, currency=new_h_currency,
                )
                if err:
                    st.error(err)
                else:
                    if txn_account_id:
                        _gross2 = float(txn_qty) * float(txn_price)
                        _net    = (-(_gross2 + txn_fees) if txn_side == "BUY"
                                   else (_gross2 - txn_fees))
                        append_cash_entry(
                            account_id=txn_account_id,
                            transaction_type=txn_side,
                            currency=_h_ccy, amount=_net,
                            linked_ticker=txn_ticker,
                            notes=txn_notes or f"{txn_side} {txn_qty:g} @ {txn_price}",
                            entry_date=txn_date.isoformat(),
                        )
                        if txn_fees > 0:
                            append_cash_entry(
                                account_id=txn_account_id,
                                transaction_type="FEE",
                                currency=_h_ccy, amount=-txn_fees,
                                linked_ticker=txn_ticker,
                                notes="Broker fee",
                                entry_date=txn_date.isoformat(),
                            )
                        try:
                            from portfolio.accounts import update_account_cash
                            update_account_cash(txn_account_id, _net)
                        except Exception:
                            pass
                    st.toast(f"{txn_side} {txn_qty:g} {txn_ticker} @ {txn_price:.4f} recorded",
                             icon="🔁")
                    st.rerun()

    # ── Transaction history ───────────────────────────────────────────────────
    txns = load_transactions()
    if txns:
        st.subheader("📜 Transaction History")
        _sorted = sorted(txns, key=lambda t: (t.date, t.recorded_at), reverse=True)
        _acct_names = {aid: a.account_name for aid, a in accounts.items()}
        rows = [{
            "Date":     t.date,
            "Ticker":   t.ticker,
            "Side":     t.side,
            "Qty":      t.quantity,
            "Price":    round(t.price, 4),
            "Value":    round(t.quantity * t.price, 2),
            "Fees":     getattr(t, "fees", 0.0),
            "Account":  _acct_names.get(getattr(t, "account_id", ""), "—") or "—",
            "Notes":    t.notes,
        } for t in _sorted]
        _txn_df = pd.DataFrame(rows)
        _txn_df.index = range(1, len(_txn_df) + 1)
        st.table(_txn_df)
        st.caption(f"{len(txns)} transaction(s) total.")
    else:
        st.info("No transactions recorded yet.", icon="ℹ️")


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
        "Realized P&L is calculated using **FIFO** cost basis. "
        "Use **↩️ Reopen** to restore a position if you re-enter a ticker."
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
            f"{ch.total_quantity:.4f} shares  ·  held {ch.holding_period_label}",
            expanded=False,
        ):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Avg Buy Price",  f"{ch.avg_buy_price:.4f}")
            c2.metric("Avg Sell Price", f"{ch.avg_sell_price:.4f}")
            c3.metric("Total Buy",      f"{ch.total_buy_value:,.2f}")
            c4.metric("Total Sell",     f"{ch.total_sell_value:,.2f}")
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Fees",           f"{ch.total_fees:,.4f}")
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

            # ── Reopen button ──────────────────────────────────────────────────
            st.write("")
            _reopen_key = f"reopen_{ticker}"
            _confirm_key = f"reopen_confirm_{ticker}"
            if not st.session_state.get(_confirm_key):
                if st.button(
                    f"↩️ Reopen / Undo  {ticker}",
                    key=_reopen_key,
                    help="Void all closed lots for this ticker (soft-delete). "
                         "The position will disappear from Closed Holdings. "
                         "If you still hold shares, they remain in Active Holdings.",
                ):
                    st.session_state[_confirm_key] = True
                    st.rerun()
            else:
                st.warning(
                    f"This will **void** all {len(ch.lots)} closed lot(s) for **{ticker}**. "
                    "The realized P&L records will be hidden (not permanently deleted). "
                    "Confirm?",
                    icon="⚠️",
                )
                _ok_c, _cancel_c = st.columns(2)
                with _ok_c:
                    if st.button(f"✅ Yes, reopen {ticker}", key=f"reopen_ok_{ticker}",
                                 use_container_width=True, type="primary"):
                        voided = void_lots_for_ticker(ticker, void_reason="Reopened via UI")
                        st.toast(f"Voided {voided} lot(s) for {ticker}", icon="↩️")
                        st.session_state.pop(_confirm_key, None)
                        st.rerun()
                with _cancel_c:
                    if st.button("Cancel", key=f"reopen_cancel_{ticker}",
                                 use_container_width=True):
                        st.session_state.pop(_confirm_key, None)
                        st.rerun()


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


# ── Global header — brand (left) · KPIs (center) · controls (right) ──────────
def render_global_header() -> str:
    """
    Professional three-zone app bar rendered above all tabs.
    LEFT : compass SVG + بوصلة المستثمر (inline, ~48 px logo)
    CENTER: Portfolio · P&L · Cash · Refresh  — horizontal flex row
    RIGHT : CCY selector + 💱 FX refresh button
    Returns the selected base currency string.
    Sticky behaviour via CSS  :has(.bousala-appbar) on the parent stHorizontalBlock.
    """
    from portfolio import load_holdings
    from portfolio.accounts import load_accounts as _gh_accts
    from fx_rates import get_rates_for_holdings, refresh_fx_rates
    from portfolio.valuation import calculate_portfolio_valuation

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

    # RIGHT — CCY + FX inside a collapsible.
    # Streamlit renders expander contents even when collapsed, so the
    # selectbox always returns its value for the valuation below.
    with _cR:
        _cur_ccy_lbl = st.session_state.get("global_base_ccy", "SAR")
        with st.expander(f"⚙️ {_cur_ccy_lbl}", expanded=False):
            _base_ccy = st.selectbox(
                "Base currency",
                options=["SAR", "USD", "EUR", "GBP"],
                key="global_base_ccy",
                help="All portfolio totals shown in this currency.",
            )
            _do_fx = st.button(
                "💱 Refresh FX rates",
                key="global_refresh_fx_btn",
                use_container_width=True,
                help="Refresh FX rates from Yahoo Finance.",
            )

    # ── Compute portfolio valuation ────────────────────────────────────────
    _gh_hld  = load_holdings()
    _gh_ccys = list({getattr(h, "currency", "USD") for h in _gh_hld.values()}) if _gh_hld else []
    _gh_fx   = get_rates_for_holdings(_gh_ccys, _base_ccy) if _gh_ccys else {}
    _gh_val  = calculate_portfolio_valuation(_gh_hld, _gh_accts(), _base_ccy, fx_rates=_gh_fx)
    _gh_ref  = st.session_state.get("mp_last_refresh") or "—"
    _has     = bool(_gh_hld)
    _pc      = "#22c55e" if _gh_val.unrealized_pnl_base >= 0 else "#ef4444"
    _ps      = "+" if _gh_val.unrealized_pnl_base >= 0 else ""

    def _gh_fmt(v: float) -> str:
        av = abs(v)
        if av >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if av >= 10_000:
            return f"{v / 1_000:.0f}K"
        return f"{v:,.0f}"

    # CENTER — horizontal KPI flex row (all four metrics in one HTML block)
    with _cM:
        if _has:
            _pct_html = f'<span class="gh-pct">({_ps}{_gh_val.unrealized_pnl_pct:.1f}%)</span>'
            st.markdown(
                f'<div class="gh-kpi-row">'
                # Portfolio value — largest
                f'  <div class="gh-kpi">'
                f'    <div class="gh-lbl">Portfolio ({_base_ccy})</div>'
                f'    <div class="gh-val-big">{_gh_fmt(_gh_val.total_portfolio_value_base)}</div>'
                f'  </div>'
                # P&L — medium-large, coloured
                f'  <div class="gh-kpi">'
                f'    <div class="gh-lbl">Unrealized P&amp;L</div>'
                f'    <div class="gh-val-med" style="color:{_pc}">'
                f'      {_ps}{_gh_fmt(_gh_val.unrealized_pnl_base)} {_pct_html}'
                f'    </div>'
                f'  </div>'
                # Cash — medium
                f'  <div class="gh-kpi">'
                f'    <div class="gh-lbl">Cash</div>'
                f'    <div class="gh-val-sm">{_gh_fmt(_gh_val.cash_value_base)}</div>'
                f'  </div>'
                # Last refresh — small / muted
                f'  <div class="gh-kpi">'
                f'    <div class="gh-lbl">Refresh</div>'
                f'    <div class="gh-val-xs">{_gh_ref}</div>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="gh-kpi-row">'
                f'  <div class="gh-kpi">'
                f'    <div class="gh-lbl">Portfolio ({_base_ccy})</div>'
                f'    <div class="gh-val-xs" style="color:#94a3b8;margin-top:4px">'
                f'      No holdings yet — add one below</div>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Handle FX refresh (after valuation so _gh_ccys is available)
    if _do_fx and _gh_hld:
        with st.spinner("Fetching rates…"):
            refresh_fx_rates(_gh_ccys, _base_ccy)
        st.toast("FX rates updated", icon="💱")
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
with st.sidebar:
    st.markdown("### ⚙️ App Settings")
    st.checkbox(
        "🔧 Developer Mode",
        key="dev_mode",
        value=False,
        help="Show technical diagnostics and FX reconciliation tables.",
    )

render_global_header()

(tab_holdings, tab_allocation, tab_closed, tab_accounts, tab_transactions, tab_cash,
 tab_decisions, tab_risk, tab_command,
 tab_thesis, tab_market_intel, tab_search, tab_watchlist, tab_upload,
 tab_test, tab_discovery) = st.tabs([
    "💼 Holdings",
    "📊 Allocation",
    "📁 Closed Holdings",
    "💳 Accounts",
    "🔁 Transactions",
    "💵 Cash Ledger",
    "🎯 Decision Queue",
    "🛡️ Portfolio Risk",
    "🧭 Command Center",
    "📝 Thesis Memory",
    "🌍 Market Intel",
    "📄 Filing Search",
    "🔬 Research Watchlist",
    "📂 Upload Filing",
    "🧪 Test Runner",
    "🔍 SAHMK Discovery",
])

_shared_bundle = _load_valuation_bundle(st.session_state.get("global_base_ccy", "SAR"))

with tab_holdings:
    render_holdings_tab(_shared_bundle)

with tab_allocation:
    render_allocation_tab(_shared_bundle)

with tab_closed:
    render_closed_holdings_tab()

with tab_accounts:
    render_accounts_tab()

with tab_transactions:
    render_transactions_tab()

with tab_cash:
    render_cash_ledger_tab()

with tab_decisions:
    render_decision_queue_tab()

with tab_risk:
    render_portfolio_risk_tab()

with tab_command:
    render_command_center_tab()

with tab_thesis:
    render_thesis_memory_tab()

with tab_market_intel:
    render_market_intel_tab()

with tab_watchlist:
    render_portfolio_dashboard()

with tab_upload:
    render_upload_tab()

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

with tab_test:
    render_test_runner_tab()

with tab_discovery:
    render_sahmk_discovery_tab()
