"""
app.py — SEC EDGAR Filing Research Tool
----------------------------------------
Streamlit web app for exploring SEC filings with optional AI analysis
and a persistent Portfolio State Engine.

Structure:
  edgar/       — EDGAR API data layer (client + filing logic)
  ai/          — AI analysis: fetcher.py + analyzer.py
  portfolio/   — Portfolio state engine (JSON-backed, per-ticker)
  app.py       — This file: Streamlit UI only
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
from portfolio import PortfolioEntry, delete_ticker, load_portfolio, update_portfolio

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SEC EDGAR Filing Research",
    page_icon="📋",
    layout="centered",
)

# ── Filing type definitions ───────────────────────────────────────────────────
FILING_TYPES = {
    "10-K": {"label": "10-K — Annual Report",    "limit": 3},
    "10-Q": {"label": "10-Q — Quarterly Report", "limit": 5},
    "8-K":  {"label": "8-K — Current Report",    "limit": 5},
}

_IMPACT_COLOR = {"Strong": "🟢", "Stable": "🔵", "Weak": "🟡", "Broken": "🔴"}
_ACTION_COLOR  = {"Buy": "🟢",   "Hold": "🔵",  "Reduce": "🟡", "Exit": "🔴"}


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
        help=(
            "Returns a sample analysis instantly without calling OpenAI. "
            "Useful for testing the UI or when your quota is exhausted."
        ),
    )

    if demo_mode:
        st.info("Demo mode **on** — Analyze Filing returns sample data.", icon="🧪")
    elif _ai_ready:
        st.success("API key found — live AI analysis active.", icon="✅")
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

_analyze_enabled = _ai_ready or demo_mode


# ── Helper: render AI analysis result ────────────────────────────────────────
def render_analysis(result: AnalysisResult) -> None:
    if result.is_demo:
        label = "🧪 Demo result"
        if result.error:
            label += f" — {result.error}"
        st.info(label)
    elif result.error and not result.what_changed:
        st.error(f"**Analysis failed:** {result.error}")
        return

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


# ── Helper: render a single filing card ──────────────────────────────────────
def render_filing_card(filing: Filing, company_name: str, ticker: str, index: int) -> None:
    with st.container(border=True):
        col_left, col_mid, col_right = st.columns([3, 1, 1])
        with col_left:
            st.markdown(f"**{filing.form_type} #{index}**")
            st.write(f"📅 Filed: **{filing.filing_date}**")
            if filing.report_date != "N/A":
                st.write(f"📆 Period: {filing.report_date}")
            st.caption(f"Accession: {filing.accession}")
        with col_mid:
            st.link_button("View on SEC.gov", filing.url, use_container_width=True)
        with col_right:
            analyze_key = f"analyze_{filing.accession}"
            result_key  = f"result_{filing.accession}"
            btn_label   = "🧪 Demo Analysis" if (demo_mode and not _ai_ready) else "Analyze Filing"

            if st.button(
                btn_label,
                key=analyze_key,
                use_container_width=True,
                disabled=not _analyze_enabled,
                help=None if _analyze_enabled else "Enable Demo Mode or add OPENAI_API_KEY",
            ):
                st.session_state[result_key] = None
                spinner_msg = "Loading demo analysis…" if demo_mode else "Fetching filing and running AI analysis…"
                with st.spinner(spinner_msg):
                    result = analyze_filing(
                        filing_url=filing.url,
                        form_type=filing.form_type,
                        company_name=company_name,
                        st_secrets=_st_secrets(),
                        demo_mode=demo_mode,
                    )
                    st.session_state[result_key] = result

                    # ── Save to portfolio if analysis produced usable data ────
                    if result.what_changed:
                        update_portfolio(ticker, company_name, result, filing.form_type)
                        st.toast(f"Portfolio updated for {ticker}", icon="💾")

        if st.session_state.get(result_key) is not None:
            st.divider()
            render_analysis(st.session_state[result_key])


# ── Helper: render a filing section ──────────────────────────────────────────
def render_section(form_type: str, filings: list[Filing], company_name: str, ticker: str, label: str) -> None:
    st.subheader(label)
    if not filings:
        st.warning(f"No {form_type} filings found for this company.")
        return
    for i, filing in enumerate(filings, start=1):
        render_filing_card(filing, company_name, ticker, i)


# ── Portfolio Dashboard ───────────────────────────────────────────────────────
def render_portfolio_dashboard() -> None:
    st.header("📊 Portfolio State")

    portfolio = load_portfolio()

    if not portfolio:
        st.info(
            "No tickers tracked yet. Search for a company, then click "
            "**Analyze Filing** on any filing to add it here.",
            icon="💡",
        )
        return

    st.caption(f"{len(portfolio)} ticker(s) tracked · updates automatically after each analysis")

    for ticker, entry in sorted(portfolio.items()):
        thesis_icon = _IMPACT_COLOR.get(entry.thesis_status, "⚪")
        action_icon = _ACTION_COLOR.get(entry.recommended_action, "⚪")

        with st.container(border=True):
            # Header row
            hcol1, hcol2, hcol3 = st.columns([2, 3, 1])
            with hcol1:
                st.markdown(f"### {ticker}")
                st.caption(entry.company_name)
            with hcol2:
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Thesis",     f"{thesis_icon} {entry.thesis_status}")
                mc2.metric("Action",     f"{action_icon} {entry.recommended_action}")
                mc3.metric("Conviction", f"{entry.conviction_score}/100")
            with hcol3:
                st.caption(f"Last: {entry.last_filing_type}")
                st.caption(f"Updated: {entry.last_updated}")
                if st.button("🗑️ Remove", key=f"del_{ticker}", use_container_width=True):
                    delete_ticker(ticker)
                    st.rerun()

            # Catalysts + Risks
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


# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("📋 SEC EDGAR Filing Research")
st.caption(
    "Look up the latest SEC filings for any publicly traded US company. "
    "Data is sourced directly from [SEC EDGAR](https://www.sec.gov/cgi-bin/browse-edgar)."
)

# ── Tabs: Search vs Portfolio ─────────────────────────────────────────────────
tab_search, tab_portfolio = st.tabs(["🔍 Filing Search", "📊 Portfolio State"])

with tab_portfolio:
    render_portfolio_dashboard()

with tab_search:
    st.divider()

    # Ticker input
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
