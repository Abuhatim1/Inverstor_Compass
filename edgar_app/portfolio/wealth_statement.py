"""
portfolio/wealth_statement.py
------------------------------
Family Wealth Statement PDF generator.

Produces a human-readable, professionally formatted multi-page PDF summarising
all asset classes -- intended for family members, trustees, and legal
representatives, not for trading.

Usage
    from portfolio.wealth_statement import build_wealth_statement
    pdf_bytes = build_wealth_statement(base_ccy="SAR", notes="Contact Ahmed...")

Output
    Raw bytes of a PDF document.  Pass directly to st.download_button(data=...).
"""
from __future__ import annotations

import os
import sys
from datetime import date as _date

from fpdf import FPDF

# ── Palette ──────────────────────────────────────────────────────────────────
_DARK   = (15,  23,  42)
_BLUE   = (30,  64, 175)
_LIGHT  = (239, 246, 255)
_WHITE  = (255, 255, 255)
_TEXT   = (15,  23,  42)
_MUTED  = (100, 116, 139)

_MARGIN = 14
_W      = 182   # usable A4 width with 14 mm margins each side


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe(s) -> str:
    """
    Sanitise text for Helvetica (Latin-1) output.
    1. Replace known typographic symbols with ASCII equivalents.
    2. Drop any remaining character outside the Latin-1 range (ord > 255),
       including Arabic, CJK, emoji, etc. that come from user data.
    """
    _MAP = {
        '\u2014': '--',   # em dash
        '\u2013': '-',    # en dash
        '\u2012': '-',    # figure dash
        '\u2212': '-',    # minus sign
        '\u2022': '-',    # bullet
        '\u2026': '...',  # ellipsis
        '\u00a0': ' ',    # non-breaking space
        '\u2018': "'",    # left single quote
        '\u2019': "'",    # right single quote
        '\u201c': '"',    # left double quote
        '\u201d': '"',    # right double quote
        '\u2500': '-',    # box drawing light horizontal
        '\u2550': '=',    # box drawing double horizontal
    }
    result = str(s)
    for src, dst in _MAP.items():
        result = result.replace(src, dst)
    # Strip anything still outside Latin-1 (covers Arabic, CJK, emoji, etc.)
    return ''.join(c if ord(c) <= 255 else '?' for c in result)


def _m(v: float) -> str:
    """Format a monetary amount: 2 decimal places with thousands separator."""
    return f"{v:,.2f}"


def _q(v: float) -> str:
    """Format a share quantity: integer when whole, 4 dp otherwise."""
    return f"{v:,.4f}" if v != int(v) else f"{int(v):,}"


def _rate(fx: dict, ccy: str) -> float:
    obj = fx.get(ccy)
    return obj.rate if obj else 1.0


def _clip(s, n: int) -> str:
    return str(s)[:n] if s else "-"


# ── PDF class ─────────────────────────────────────────────────────────────────

class _WealthPDF(FPDF):
    """fpdf2 subclass with header/footer and reusable drawing helpers.
    All text is routed through _safe() to stay within Latin-1."""

    def __init__(self, base_ccy: str, date_str: str) -> None:
        super().__init__()
        self.base_ccy = base_ccy
        self.date_str = date_str
        self.alias_nb_pages()
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)
        self.set_auto_page_break(auto=True, margin=18)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*_MUTED)
        txt = (
            f"Bousala Investor Compass"
            f"  |  Confidential"
            f"  |  {self.date_str}"
            f"  |  Page {self.page_no()} of {{nb}}"
        )
        self.cell(0, 8, _safe(txt), align="C")
        self.set_text_color(0, 0, 0)

    # ── Drawing helpers ──────────────────────────────────────────────────────

    def section_header(self, title: str, subtitle: str = "") -> None:
        self.set_fill_color(*_BLUE)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, _safe(f"  {title}"), fill=True, ln=True)
        if subtitle:
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*_MUTED)
            self.cell(0, 5, _safe(f"  {subtitle}"), ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def table_header(self, cols: list[str], widths: list[int]) -> None:
        self.set_fill_color(*_DARK)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 8)
        for col, w in zip(cols, widths):
            self.cell(w, 6, _safe(col), fill=True)
        self.ln()
        self.set_text_color(0, 0, 0)

    def table_row(
        self,
        vals: list,
        widths: list[int],
        even: bool,
        aligns: list[str] | None = None,
    ) -> None:
        self.set_fill_color(*(_LIGHT if even else _WHITE))
        self.set_font("Helvetica", "", 8)
        aligns = aligns or (["L"] * len(vals))
        for v, w, a in zip(vals, widths, aligns):
            self.cell(w, 5, _safe(v), fill=True, align=a)
        self.ln()

    def total_row(
        self, label: str, label_w: int, value: str, value_w: int
    ) -> None:
        self.set_fill_color(*_DARK)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 8)
        self.cell(label_w, 6, _safe(f"  {label}"), fill=True)
        self.cell(value_w, 6, _safe(value), fill=True, align="R")
        self.ln()
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def kv_row(self, label: str, value: str, even: bool) -> None:
        self.set_fill_color(*(_LIGHT if even else _WHITE))
        self.set_font("Helvetica", "B", 8)
        self.cell(60, 5, _safe(label), fill=True)
        self.set_font("Helvetica", "", 8)
        self.cell(_W - 60, 5, _safe(value), fill=True)
        self.ln()


# ── Main builder ──────────────────────────────────────────────────────────────

def build_wealth_statement(base_ccy: str = "SAR", notes: str = "") -> bytes:
    """
    Build and return a Family Wealth Statement as a PDF (raw bytes).

    Parameters
    ----------
    base_ccy : str
        Base currency for converted totals (e.g. "SAR").
    notes : str
        Optional personal message printed on the final page.

    Returns
    -------
    bytes -- PDF document ready for st.download_button(data=...).
    """
    _here = os.path.dirname(__file__)
    if _here not in sys.path:
        sys.path.insert(0, os.path.dirname(_here))

    from portfolio import load_holdings
    from portfolio.accounts import load_accounts
    from portfolio.alt_investments import load_igi_investments
    from portfolio.crowdfunding import load_cf_accounts
    from portfolio.fixed_assets import load_fixed_assets
    from portfolio.valuation import calculate_portfolio_valuation
    from fx_rates import get_rates_for_holdings

    # Load & filter
    holdings = load_holdings()
    accounts = load_accounts()
    igi = {k: v for k, v in load_igi_investments().items() if v.status != "Closed"}
    cf  = {k: v for k, v in load_cf_accounts().items()    if v.status == "Active"}
    fa  = {k: v for k, v in load_fixed_assets().items()   if v.status == "Active"}

    # Collect currencies for one FX request
    ccys: set[str] = set()
    for h in holdings.values():
        ccys.add(getattr(h, "currency", base_ccy))
    for inv in igi.values():
        ccys.add(inv.currency)
    for a in cf.values():
        ccys.add(a.currency)
    for a in fa.values():
        ccys.add(a.currency)
    for a in accounts.values():
        ccys.add(a.base_currency)

    fx: dict = get_rates_for_holdings(list(ccys), base_ccy) if ccys else {}

    val = None
    if holdings or accounts:
        try:
            val = calculate_portfolio_valuation(
                holdings, accounts, base_ccy, fx_rates=fx
            )
        except Exception:
            val = None

    # Section totals
    port_mv_base = val.holdings_value_base if val else 0.0
    cash_base    = val.cash_value_base      if val else 0.0
    igi_base  = sum(inv.current_value        * _rate(fx, inv.currency) for inv in igi.values())
    cf_base   = sum(a.current_account_value  * _rate(fx, a.currency)   for a   in cf.values())
    fa_base   = sum(a.equity                 * _rate(fx, a.currency)   for a   in fa.values())
    nw        = port_mv_base + cash_base + igi_base + cf_base + fa_base

    today_str = _date.today().strftime("%d %B %Y")
    pdf = _WealthPDF(base_ccy, today_str)

    # =========================================================================
    # PAGE 1 -- COVER
    # =========================================================================
    pdf.add_page()

    # Dark header band
    pdf.set_fill_color(*_DARK)
    pdf.rect(0, 0, 210, 52, "F")
    pdf.set_xy(_MARGIN, 8)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "Bousala - Investor Compass", ln=True)
    pdf.set_x(_MARGIN)
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 10, "Family Wealth Statement", ln=True)
    pdf.set_x(_MARGIN)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 7,
        f"Prepared on {today_str}  |  Base Currency: {base_ccy}  |  Confidential",
        ln=True,
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(20)

    # Introduction
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_TEXT)
    pdf.multi_cell(
        0, 6,
        "This document provides a complete picture of financial assets and properties "
        "as of the date shown above. It is prepared automatically from the Bousala "
        "portfolio tracker and is intended to assist family members, trustees, and "
        "legal representatives in understanding the full scope of holdings.\n\n"
        "All values are shown in their original currency and also converted to the "
        f"base currency ({base_ccy}) using the exchange rates current at the time of "
        "this report.",
        ln=True,
    )
    pdf.ln(5)

    # Net worth highlight
    pdf.set_fill_color(*_DARK)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(
        0, 12,
        f"  Total Net Worth  --  {base_ccy} {_m(nw)}",
        fill=True,
        ln=True,
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)

    # Cover summary table
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_MUTED)
    pdf.cell(0, 5, "SNAPSHOT BY CATEGORY", ln=True)
    pdf.set_text_color(0, 0, 0)

    _sw = [_W - 52, 52]
    _summary = [
        ("Investment Portfolio (Stocks & ETFs)", port_mv_base),
        ("Alternative Investments",              igi_base),
        ("Bank, Cash & Crowdfunding Accounts",   cash_base + cf_base),
        ("Properties, Vehicles & Retirement",    fa_base),
    ]
    pdf.table_header(["Category", f"Value ({base_ccy})"], _sw)
    for i, (lbl, amt) in enumerate(_summary):
        pdf.table_row([lbl, _m(amt)], _sw, i % 2 == 0, ["L", "R"])
    pdf.total_row("Total Net Worth", _sw[0], f"{base_ccy} {_m(nw)}", _sw[1])

    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(
        0, 5,
        "Exchange rates and market prices are as of the last recorded update. "
        "For legal or estate planning matters, please consult a qualified financial "
        "or legal professional.",
        ln=True,
    )
    pdf.set_text_color(0, 0, 0)

    # =========================================================================
    # SECTION 1 -- INVESTMENT PORTFOLIO (Stocks & ETFs)
    # =========================================================================
    if holdings:
        pdf.add_page()
        pdf.section_header(
            "Section 1 - Investment Portfolio (Stocks & ETFs)",
            "Market values are based on the most recently recorded price in Bousala.",
        )
        _cols = [
            "Company / Name", "Ticker", "Shares",
            "Last Price", "Value (CCY)", f"Value ({base_ccy})",
        ]
        _wids = [60, 16, 18, 26, 32, 30]
        pdf.table_header(_cols, _wids)

        _sec_total = 0.0
        for i, h in enumerate(
            sorted(holdings.values(), key=lambda x: (x.company_name or x.ticker or ""))
        ):
            mv   = h.market_value
            mv_b = mv * _rate(fx, h.currency)
            _sec_total += mv_b
            pdf.table_row(
                [
                    _clip(h.company_name or h.ticker, 32),
                    _clip(h.ticker, 10),
                    _q(h.quantity),
                    f"{h.currency} {_m(h.current_price)}",
                    f"{h.currency} {_m(mv)}",
                    _m(mv_b),
                ],
                _wids, i % 2 == 0,
                ["L", "L", "R", "R", "R", "R"],
            )

        pdf.total_row(
            f"Total - {len(holdings)} holding(s)",
            sum(_wids[:-1]),
            f"{base_ccy} {_m(_sec_total)}",
            _wids[-1],
        )

    # =========================================================================
    # SECTION 2 -- ALTERNATIVE INVESTMENTS
    # =========================================================================
    if igi:
        pdf.add_page()
        pdf.section_header(
            "Section 2 - Alternative Investments",
            "Includes murabaha, sukuk, fixed income, and other non-listed instruments.",
        )
        _cols = [
            "Investment Name", "Type", "Status",
            "Currency", "Value (CCY)", f"Value ({base_ccy})",
        ]
        _wids = [56, 30, 26, 16, 26, 28]
        pdf.table_header(_cols, _wids)

        _sec_total = 0.0
        for i, inv in enumerate(sorted(igi.values(), key=lambda x: x.investment_name)):
            rate  = _rate(fx, inv.currency)
            val_b = inv.current_value * rate
            _sec_total += val_b
            pdf.table_row(
                [
                    _clip(inv.investment_name, 34),
                    _clip(inv.sharia_structure or "N/A", 18),
                    _clip(inv.status, 14),
                    inv.currency,
                    f"{inv.currency} {_m(inv.current_value)}",
                    _m(val_b),
                ],
                _wids, i % 2 == 0,
                ["L", "L", "L", "L", "R", "R"],
            )

        pdf.total_row(
            f"Total - {len(igi)} investment(s)",
            sum(_wids[:-1]),
            f"{base_ccy} {_m(_sec_total)}",
            _wids[-1],
        )

    # =========================================================================
    # SECTION 3 -- BANK, CASH & CROWDFUNDING ACCOUNTS
    # =========================================================================
    _acct_rows: list[tuple] = []
    for a in accounts.values():
        if a.cash_balance == 0:
            continue
        rate  = _rate(fx, a.base_currency)
        bal_b = a.cash_balance * rate
        _acct_rows.append((
            a.account_name or "-",
            a.institution  or "-",
            a.account_type,
            a.base_currency,
            a.cash_balance,
            bal_b,
        ))
    _cf_rows: list[tuple] = []
    for a in cf.values():
        rate  = _rate(fx, a.currency)
        val_b = a.current_account_value * rate
        _cf_rows.append((
            a.account_name  or "-",
            a.platform_name or a.institution or "-",
            "Crowdfunding",
            a.currency,
            a.current_account_value,
            val_b,
        ))

    if _acct_rows or _cf_rows:
        pdf.add_page()
        pdf.section_header(
            "Section 3 - Bank, Cash & Crowdfunding Accounts",
            "Cash balances in brokerage, bank, and crowdfunding accounts.",
        )
        _cols = [
            "Account Name", "Institution", "Type",
            "Currency", "Balance (CCY)", f"Balance ({base_ccy})",
        ]
        _wids = [50, 38, 26, 16, 24, 28]
        pdf.table_header(_cols, _wids)

        _sec_total = 0.0
        all_rows = (
            sorted(_acct_rows, key=lambda r: r[0])
            + sorted(_cf_rows, key=lambda r: r[0])
        )
        for i, (nm, inst, typ, ccy, bal, bal_b) in enumerate(all_rows):
            _sec_total += bal_b
            pdf.table_row(
                [
                    _clip(nm, 28),
                    _clip(inst, 22),
                    typ,
                    ccy,
                    f"{ccy} {_m(bal)}",
                    _m(bal_b),
                ],
                _wids, i % 2 == 0,
                ["L", "L", "L", "L", "R", "R"],
            )

        pdf.total_row(
            f"Total - {len(all_rows)} account(s)",
            sum(_wids[:-1]),
            f"{base_ccy} {_m(_sec_total)}",
            _wids[-1],
        )

    # =========================================================================
    # SECTION 4 -- PROPERTIES, VEHICLES & RETIREMENT
    # =========================================================================
    if fa:
        pdf.add_page()
        pdf.section_header(
            "Section 4 - Properties, Vehicles & Retirement",
            "Net Equity = Current Value - Outstanding Loan or Mortgage.",
        )
        _cols = [
            "Asset Name", "Category",
            "Currency", "Current Value", "Loan / Mortgage",
            "Net Equity", f"Equity ({base_ccy})",
        ]
        _wids = [44, 30, 16, 24, 24, 20, 24]
        pdf.table_header(_cols, _wids)

        _sec_total = 0.0
        for i, asset in enumerate(sorted(fa.values(), key=lambda a: a.name)):
            rate   = _rate(fx, asset.currency)
            eq_b   = asset.equity * rate
            _sec_total += eq_b
            pdf.table_row(
                [
                    _clip(asset.name, 26),
                    _clip(asset.asset_type, 18),
                    asset.currency,
                    _m(asset.current_value),
                    _m(asset.outstanding_liability),
                    _m(asset.equity),
                    _m(eq_b),
                ],
                _wids, i % 2 == 0,
                ["L", "L", "L", "R", "R", "R", "R"],
            )

        pdf.total_row(
            f"Total - {len(fa)} asset(s)",
            sum(_wids[:-1]),
            f"{base_ccy} {_m(_sec_total)}",
            _wids[-1],
        )

    # =========================================================================
    # SECTION 5 -- CONSOLIDATED SUMMARY
    # =========================================================================
    pdf.add_page()
    pdf.section_header(
        "Section 5 - Consolidated Net Worth Summary",
        "All figures in base currency after FX conversion.",
    )

    _sw5 = [_W - 52, 52]
    pdf.table_header(["Asset Category", f"Total ({base_ccy})"], _sw5)
    _sec5 = [
        ("Investment Portfolio (Stocks & ETFs)", port_mv_base),
        ("Alternative Investments",              igi_base),
        ("Cash in Brokerage & Bank Accounts",    cash_base),
        ("Crowdfunding Accounts",                cf_base),
        ("Properties, Vehicles & Retirement",    fa_base),
    ]
    for i, (lbl, amt) in enumerate(_sec5):
        pdf.table_row([lbl, _m(amt)], _sw5, i % 2 == 0, ["L", "R"])
    pdf.total_row("Total Net Worth", _sw5[0], f"{base_ccy} {_m(nw)}", _sw5[1])

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_MUTED)
    pdf.cell(0, 5, "ALLOCATION BREAKDOWN", ln=True)
    pdf.set_text_color(0, 0, 0)

    if nw > 0:
        pdf.table_header(["Category", "Allocation (%)"], _sw5)
        for i, (lbl, amt) in enumerate(_sec5):
            pct = (amt / nw * 100) if nw else 0.0
            pdf.table_row([lbl, f"{pct:.1f}%"], _sw5, i % 2 == 0, ["L", "R"])
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(0, 6, "No assets recorded yet.", ln=True)
        pdf.set_text_color(0, 0, 0)

    # =========================================================================
    # NOTES PAGE -- Account Directory & Personal Message
    # =========================================================================
    pdf.add_page()
    pdf.section_header("Important Information & Contacts")

    # Account / institution directory
    _dir_rows: list[tuple[str, str]] = []
    for a in sorted(accounts.values(), key=lambda x: x.account_name or ""):
        if a.institution:
            _dir_rows.append((
                f"{a.account_name} ({a.account_type})",
                a.institution,
            ))
    for inv in sorted(igi.values(), key=lambda x: x.investment_name):
        if inv.institution:
            _dir_rows.append((inv.investment_name, inv.institution))
    for a in sorted(cf.values(), key=lambda x: x.account_name or ""):
        inst = a.platform_name or a.institution or ""
        if inst:
            _dir_rows.append((f"{a.account_name} (Crowdfunding)", inst))

    if _dir_rows:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_TEXT)
        pdf.cell(0, 6, "Where are the accounts held?", ln=True)
        pdf.ln(1)
        pdf.table_header(["Account / Investment", "Institution"], [_W - 60, 60])
        for i, (acc, inst) in enumerate(_dir_rows):
            pdf.table_row(
                [_clip(acc, 55), _clip(inst, 34)],
                [_W - 60, 60], i % 2 == 0,
            )
        pdf.ln(5)

    # Personal note box
    pdf.set_fill_color(*_LIGHT)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_TEXT)
    pdf.cell(0, 7, "  Personal Note from Account Holder", fill=True, ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.ln(2)
    if notes and notes.strip():
        pdf.multi_cell(0, 6, _safe(notes.strip()), ln=True)
    else:
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(
            0, 6,
            "(No personal note was provided when this document was generated. "
            "Add one in the sidebar before downloading.)",
            ln=True,
        )
    pdf.set_text_color(0, 0, 0)

    # Legal disclaimer
    pdf.ln(8)
    pdf.set_draw_color(*_MUTED)
    pdf.line(_MARGIN, pdf.get_y(), _MARGIN + _W, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(
        0, 5,
        "This document was generated automatically by the Bousala investment tracker "
        "and reflects data recorded as of the date above. Values are based on the most "
        "recently available prices and may not reflect real-time market conditions. "
        "This document does not constitute legal, financial, or investment advice. "
        "For estate planning or legal purposes, please consult a qualified professional.",
        ln=True,
    )

    return bytes(pdf.output())
