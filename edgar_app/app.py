"""
app.py — SEC EDGAR Filing Research Tool
----------------------------------------
Streamlit web app for exploring SEC filings with optional AI analysis.

Structure:
  edgar/       — EDGAR API data layer (client + filing logic)
  ai/          — AI analysis: fetcher.py + analyzer.py
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

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SEC EDGAR Filing Research",
    page_icon="📋",
    layout="centered",
)

# ── Filing type definitions ───────────────────────────────────────────────────
FILING_TYPES = {
    "10-K": {"label": "10-K — Annual Report", "limit": 3},
    "10-Q": {"label": "10-Q — Quarterly Report", "limit": 5},
    "8-K":  {"label": "8-K — Current Report (material events)", "limit": 5},
}

_IMPACT_COLOR = {"Strong": "🟢", "Stable": "🔵", "Weak": "🟡", "Broken": "🔴"}
_ACTION_COLOR  = {"Buy": "🟢", "Hold": "🔵", "Reduce": "🟡", "Exit": "🔴"}


# ── Resolve API key (checked fresh on every page load) ───────────────────────
def _st_secrets():
    try:
        return st.secrets
    except Exception:
        return None

_api_key = get_api_key(_st_secrets())
_ai_ready = bool(_api_key)


# ── Helper: render AI analysis result ────────────────────────────────────────
def render_analysis(result: AnalysisResult) -> None:
    if result.error:
        st.error(f"**Analysis failed:** {result.error}")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Thesis Impact",    f"{_IMPACT_COLOR.get(result.thesis_impact, '⚪')} {result.thesis_impact}")
    col2.metric("Suggested Action", f"{_ACTION_COLOR.get(result.suggested_action, '⚪')} {result.suggested_action}")
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
def render_filing_card(filing: Filing, company_name: str, index: int) -> None:
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
            btn = st.button(
                "Analyze Filing",
                key=analyze_key,
                use_container_width=True,
                disabled=not _ai_ready,
                help=None if _ai_ready else "Add OPENAI_API_KEY to Replit Secrets to enable",
            )
            if btn:
                st.session_state[result_key] = None
                with st.spinner("Fetching filing and running AI analysis…"):
                    st.session_state[result_key] = analyze_filing(
                        filing.url,
                        filing.form_type,
                        company_name,
                        st_secrets=_st_secrets(),
                    )

        if st.session_state.get(result_key) is not None:
            st.divider()
            render_analysis(st.session_state[result_key])


# ── Helper: render a filing section ──────────────────────────────────────────
def render_section(form_type, filings, company_name, label):
    st.subheader(label)
    if not filings:
        st.warning(f"No {form_type} filings found for this company.")
        return
    for i, filing in enumerate(filings, start=1):
        render_filing_card(filing, company_name, i)


# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("📋 SEC EDGAR Filing Research")
st.caption(
    "Look up the latest SEC filings for any publicly traded US company. "
    "Data is sourced directly from [SEC EDGAR](https://www.sec.gov/cgi-bin/browse-edgar)."
)

# ── Debug: API key status (does not reveal the key value) ────────────────────
with st.expander("🔑 API Key Status (debug)", expanded=not _ai_ready):
    if _ai_ready:
        st.success("API key found — AI analysis is enabled.", icon="✅")
    else:
        st.error("API key missing — OPENAI_API_KEY not found in environment or Replit Secrets.", icon="❌")
        st.markdown(
            "**To fix:**\n"
            "1. Open the **Secrets** panel (lock icon in the left sidebar)\n"
            "2. Add a secret named exactly `OPENAI_API_KEY`\n"
            "3. Click **Restart app** below to reload with the new secret"
        )
        if st.button("🔄 Restart app to reload secrets"):
            st.rerun()

st.divider()

# ── Ticker input ──────────────────────────────────────────────────────────────
col_input, col_btn = st.columns([3, 1])
with col_input:
    ticker_input = st.text_input(
        "Stock Ticker Symbol",
        placeholder="e.g. AAPL, MSFT, VCYT",
        label_visibility="collapsed",
    ).strip().upper()
with col_btn:
    search_clicked = st.button("Search", type="primary", use_container_width=True)

# ── Run search ────────────────────────────────────────────────────────────────
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
        errors: dict[str, str] = {}
        for form_type, cfg in FILING_TYPES.items():
            try:
                results[form_type] = get_filings(company, form_type, limit=cfg["limit"])
            except EdgarAPIError as e:
                results[form_type] = []
                errors[form_type] = str(e)

    for form_type, msg in errors.items():
        st.warning(f"Could not fetch {form_type} filings: {msg}")

    tabs = st.tabs([cfg["label"] for cfg in FILING_TYPES.values()])
    for tab, (form_type, cfg) in zip(tabs, FILING_TYPES.items()):
        with tab:
            render_section(
                form_type=form_type,
                filings=results.get(form_type, []),
                company_name=company.name,
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
