"""
app.py — SEC EDGAR Filing Research Tool
----------------------------------------
A beginner-friendly Streamlit web app for exploring SEC filings.

Structure:
  edgar/       — EDGAR API data layer (client + filing logic)
  ai/          — AI analysis module (stub, ready for OpenAI)
  app.py       — This file: Streamlit UI only
"""

import streamlit as st

from edgar import EdgarAPIError, get_filings, lookup_company
from edgar.filings import Filing
from ai import analyze_filing

# ── Page config ──────────────────────────────────────────────────────────────
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


# ── Helper: render a single filing card ──────────────────────────────────────
def render_filing_card(filing: Filing, company_name: str, index: int) -> None:
    with st.container(border=True):
        col_left, col_right = st.columns([3, 1])
        with col_left:
            st.markdown(f"**{filing.form_type} #{index}**")
            st.write(f"📅 Filed: **{filing.filing_date}**")
            if filing.report_date != "N/A":
                st.write(f"📆 Period: {filing.report_date}")
            st.caption(f"Accession: {filing.accession}")
        with col_right:
            st.link_button("View on SEC.gov", filing.url, use_container_width=True)

        # AI analysis expander (ready for OpenAI — see ai/analyzer.py)
        with st.expander("AI Analysis (coming soon)"):
            with st.spinner("Analyzing..."):
                summary = analyze_filing(filing, company_name)
            st.info(summary)


# ── Helper: render a filing section ──────────────────────────────────────────
def render_section(
    form_type: str,
    filings: list[Filing],
    company_name: str,
    label: str,
) -> None:
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

st.divider()

# ── Ticker input ──────────────────────────────────────────────────────────────
col_input, col_btn = st.columns([3, 1])
with col_input:
    ticker_input = st.text_input(
        "Stock Ticker Symbol",
        placeholder="e.g. AAPL, MSFT, TSLA",
        label_visibility="collapsed",
    ).strip().upper()
with col_btn:
    search_clicked = st.button("Search", type="primary", use_container_width=True)

# ── Run search ────────────────────────────────────────────────────────────────
if search_clicked or ticker_input:
    if not ticker_input:
        st.error("Please enter a ticker symbol.")
        st.stop()

    with st.spinner(f"Looking up {ticker_input}..."):
        try:
            company = lookup_company(ticker_input)
        except EdgarAPIError as e:
            st.error(str(e))
            st.stop()

    # Company header
    st.divider()
    st.markdown(f"### {company.name}")
    col1, col2, col3 = st.columns(3)
    col1.metric("Ticker", company.ticker)
    col2.metric("CIK", company.cik)
    col3.metric("Filings Source", "SEC EDGAR")

    st.divider()

    # Fetch all three filing types in sequence (clear progress for the user)
    with st.spinner("Fetching filings from SEC EDGAR..."):
        results: dict[str, list[Filing]] = {}
        errors: dict[str, str] = {}
        for form_type, cfg in FILING_TYPES.items():
            try:
                results[form_type] = get_filings(company, form_type, limit=cfg["limit"])
            except EdgarAPIError as e:
                results[form_type] = []
                errors[form_type] = str(e)

    # Show any fetch errors
    for form_type, msg in errors.items():
        st.warning(f"Could not fetch {form_type} filings: {msg}")

    # Tabs — one per filing type
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
    # Empty state
    st.info(
        "Enter a US stock ticker above (e.g. **AAPL**, **MSFT**, **TSLA**) "
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
