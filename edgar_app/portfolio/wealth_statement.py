"""
portfolio/wealth_statement.py
------------------------------
Family Wealth Statement PDF generator — fully Arabic UI, RTL layout.

All static labels, section headers, column headers, footer text, and
disclaimers are in Arabic.  User-entered data (company names, account names,
institution names, investment names, personal notes, ticker symbols, currency
codes, numeric values) is rendered exactly as typed.

Arabic rendering: Amiri Unicode font + arabic_reshaper (letter shaping) +
python-bidi (visual right-to-left ordering).

RTL layout: table columns are reversed so the descriptive/name column sits on
the right and numeric columns sit on the left, matching Arabic reading direction.

Usage
    from portfolio.wealth_statement import build_wealth_statement
    pdf_bytes = build_wealth_statement(base_ccy="SAR", notes="...")

Output
    Raw bytes of a PDF document.  Pass directly to st.download_button(data=...).
"""
from __future__ import annotations

import os
import sys
from datetime import date as _date

from fpdf import FPDF

# ── Arabic shaping (graceful fallback if packages not installed) ──────────────
try:
    import arabic_reshaper as _reshaper          # type: ignore
    from bidi.algorithm import get_display as _bidi  # type: ignore
    _ARABIC_OK = True
except ImportError:
    _ARABIC_OK = False


# ── Palette ───────────────────────────────────────────────────────────────────
_DARK   = (15,  23,  42)
_BLUE   = (30,  64, 175)
_LIGHT  = (239, 246, 255)
_WHITE  = (255, 255, 255)
_TEXT   = (15,  23,  42)
_MUTED  = (100, 116, 139)

_MARGIN = 14
_W      = 182   # usable A4 width with 14 mm margins each side

# ── Font paths ────────────────────────────────────────────────────────────────
_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
_AMIRI_R  = os.path.join(_FONT_DIR, "Amiri-Regular.ttf")
_AMIRI_B  = os.path.join(_FONT_DIR, "Amiri-Bold.ttf")
_HAVE_AMIRI = os.path.isfile(_AMIRI_R) and os.path.isfile(_AMIRI_B)


# ── Arabic UI strings (all static labels) ────────────────────────────────────
_AR: dict[str, str] = {
    # Cover
    "app_name":      "بوصلة - بوصلة المستثمر",
    "doc_title":     "تقرير كشف الثروة",
    "prepared":      "أُعِدَّ بتاريخ",
    "base_ccy_lbl":  "العملة الأساسية",
    "confidential":  "سري",
    "intro": (
        "تُقدِّم هذه الوثيقة صورةً شاملةً للأصول المالية والعقارات "
        "حتى التاريخ المُشار إليه أعلاه. أُعِدَّت تلقائياً بواسطة منصة "
        "بوصلة لتتبع المحافظ، وتهدف إلى مساعدة أفراد الأسرة والأوصياء "
        "والممثلين القانونيين على فهم النطاق الكامل للحيازات.\n\n"
        "تُعرَض جميع القيم بعملاتها الأصلية وبالعملة الأساسية ({base_ccy}) "
        "وفق أسعار الصرف السارية وقت إعداد هذا التقرير."
    ),
    "total_nw":      "إجمالي صافي الثروة",
    "snapshot":      "ملخص حسب الفئة",
    "col_category":  "الفئة",
    "col_value":     "القيمة",
    "cat_portfolio": "محفظة الأسهم والصناديق المتداولة",
    "cat_alt":       "الاستثمارات البديلة",
    "cat_cash":      "الحسابات المصرفية والنقدية والتمويل الجماعي",
    "cat_fa":        "العقارات والمركبات والتقاعد",
    "cover_note": (
        "تستند أسعار الصرف وأسعار السوق إلى آخر تحديث مُسجَّل. "
        "للأغراض القانونية أو تخطيط التركات، يُرجى استشارة "
        "مختص مالي أو قانوني معتمد."
    ),
    # Section 1
    "sec1_title":    "القسم الأول - محفظة الأسهم والصناديق المتداولة",
    "sec1_sub":      "تستند القيم السوقية إلى آخر سعر مُسجَّل في بوصلة.",
    "col_company":   "الشركة / الاسم",
    "col_ticker":    "الرمز",
    "col_shares":    "الأسهم",
    "col_price":     "آخر سعر",
    "col_val_ccy":   "القيمة (العملة)",
    "col_val_base":  "القيمة (قاعدة)",
    "total_hld":     "الإجمالي - {n} استثمار",
    # Section 2
    "sec2_title":    "القسم الثاني - الاستثمارات البديلة",
    "sec2_sub":      "يشمل المرابحة والصكوك والدخل الثابت والأدوات غير المُدرجة الأخرى.",
    "col_inv_name":  "اسم الاستثمار",
    "col_type":      "النوع",
    "col_status":    "الحالة",
    "col_currency":  "العملة",
    "total_inv":     "الإجمالي - {n} استثمار",
    # Section 3
    "sec3_title":    "القسم الثالث - الحسابات المصرفية والنقدية والتمويل الجماعي",
    "sec3_sub":      "أرصدة النقد في حسابات السمسرة والبنوك والتمويل الجماعي.",
    "col_acc_name":  "اسم الحساب",
    "col_inst":      "المؤسسة",
    "col_acc_type":  "النوع",
    "col_bal_ccy":   "الرصيد (العملة)",
    "col_bal_base":  "الرصيد (قاعدة)",
    "crowdfunding":  "تمويل جماعي",
    "total_accts":   "الإجمالي - {n} حساب",
    # Section 4
    "sec4_title":    "القسم الرابع - العقارات والمركبات والتقاعد",
    "sec4_sub":      "صافي حقوق الملكية = القيمة الحالية - القرض أو الرهن العقاري.",
    "col_asset":     "اسم الأصل",
    "col_asset_cat": "الفئة",
    "col_cur_val":   "القيمة الحالية",
    "col_loan":      "القرض / الرهن",
    "col_equity":    "صافي حقوق الملكية",
    "col_eq_base":   "حقوق الملكية (قاعدة)",
    "total_assets":  "الإجمالي - {n} أصل",
    # Section 5
    "sec5_title":    "القسم السادس - ملخص صافي الثروة الموحَّد",
    "sec5_sub":      "جميع الأرقام بالعملة الأساسية بعد تحويل العملات.",
    "col_asset_grp": "فئة الأصل",
    "col_total":     "الإجمالي",
    "cat_port_mv":   "محفظة الأسهم والصناديق المتداولة",
    "cat_alt_inv":   "الاستثمارات البديلة",
    "cat_cash_brk":  "النقد في حسابات السمسرة والبنوك",
    "cat_cf":        "حسابات التمويل الجماعي",
    "cat_fa_sec":    "العقارات والمركبات والتقاعد",
    "alloc":         "توزيع التخصيص",
    "col_alloc":     "التخصيص (%)",
    "no_assets":     "لا توجد أصول مُسجَّلة بعد.",
    # Notes page
    "notes_title":   "معلومات مهمة وجهات الاتصال",
    "dir_heading":   "أين تُحتفظ الحسابات؟",
    "col_acc_inv":   "الحساب / الاستثمار",
    "col_inst2":     "المؤسسة",
    "note_heading":  "ملاحظة شخصية من صاحب الحساب",
    "no_note": (
        "(لم تُضَف أي ملاحظة شخصية عند إنشاء هذه الوثيقة. "
        "يمكنك إضافتها من الشريط الجانبي قبل التنزيل.)"
    ),
    "disclaimer": (
        "أُنشئت هذه الوثيقة تلقائياً بواسطة منصة بوصلة للاستثمار "
        "وتعكس البيانات المُسجَّلة حتى التاريخ المُشار إليه أعلاه. "
        "تستند القيم إلى أحدث الأسعار المتاحة وقد لا تعكس ظروف السوق الآنية. "
        "لا تُمثِّل هذه الوثيقة نصيحةً قانونيةً أو ماليةً أو استثمارية. "
        "لأغراض التخطيط العقاري أو القانوني، يُرجى استشارة مختص معتمد."
    ),
    # Footer  ({date} and {page} are filled at render time; {{nb}} → {nb} for fpdf2)
    "footer_tpl": "بوصلة المستثمر  |  سري  |  {date}  |  صفحة {page} من {{nb}}",
    # Detail / sub-rows (location & notes)
    "detail_held_at": "محتجز في",
    "detail_note":    "ملاحظة",
    "detail_inst":    "المؤسسة",
    # Section 5 — Liabilities
    "sec5_liab_title": "القسم الخامس - الالتزامات والمديونيات",
    "sec5_liab_sub":   "الأرصدة القائمة المُستحقة للسداد بعملاتها الأصلية وبالعملة الأساسية.",
    "col_liab_name":   "الالتزام / الاسم",
    "col_lender":      "الجهة المُقرِضة",
    "total_liab":      "إجمالي الالتزامات - {n} التزام",
    "cat_liab":        "إجمالي الالتزامات",
}


# ── Text helpers ──────────────────────────────────────────────────────────────

def _is_arabic(text: str) -> bool:
    """Return True if the string contains any Arabic-script character."""
    return any('\u0600' <= c <= '\u06FF' or '\uFE70' <= c <= '\uFEFF' for c in str(text))


def _ar_text(text: str) -> str:
    """
    Reshape and apply the Unicode bidi algorithm to Arabic text so that
    fpdf2 renders it in correct visual order (right-to-left).
    Falls back to a transliteration-safe ASCII strip when packages are absent.
    """
    s = str(text)
    if not _is_arabic(s):
        return _safe_latin(s)
    if _ARABIC_OK:
        reshaped = _reshaper.reshape(s)
        return _bidi(reshaped)
    return ''.join(c if ord(c) <= 255 else '?' for c in s)


def _safe_latin(s) -> str:
    """
    Replace typographic symbols with ASCII equivalents so Helvetica
    (Latin-1) renders them without error.  Does NOT touch Arabic chars.
    """
    _MAP = {
        '\u2014': '--',   '\u2013': '-',    '\u2012': '-',
        '\u2212': '-',    '\u2022': '-',    '\u2026': '...',
        '\u00a0': ' ',    '\u2018': "'",    '\u2019': "'",
        '\u201c': '"',    '\u201d': '"',    '\u2500': '-',   '\u2550': '=',
    }
    result = str(s)
    for src, dst in _MAP.items():
        result = result.replace(src, dst)
    return ''.join(
        c if ord(c) <= 255 or _is_arabic(c) else '?'
        for c in result
    )


def _m(v: float) -> str:
    """Monetary amount: 2 decimal places with thousands separator."""
    return f"{v:,.2f}"


def _q(v: float) -> str:
    """Share quantity: integer when whole, 4 dp otherwise."""
    return f"{v:,.4f}" if v != int(v) else f"{int(v):,}"


def _rate(fx: dict, ccy: str) -> float:
    obj = fx.get(ccy)
    return obj.rate if obj else 1.0


def _clip(s, n: int) -> str:
    return str(s)[:n] if s else "-"


# ── PDF class ─────────────────────────────────────────────────────────────────

class _WealthPDF(FPDF):
    """
    fpdf2 subclass — fully Arabic UI, RTL layout.

    Font strategy
    -------------
    Amiri      — All static UI labels (Arabic); also used for user data that
                 contains Arabic script (auto-detected by _smart_cell).
    Helvetica  — User data that is purely Latin/ASCII (company names,
                 tickers, numbers, currency codes typed in Latin).
    """

    def __init__(self, base_ccy: str, date_str: str) -> None:
        super().__init__()
        self.base_ccy = base_ccy
        self.date_str = date_str

        if _HAVE_AMIRI:
            self.add_font("Amiri", style="",  fname=_AMIRI_R)
            self.add_font("Amiri", style="B", fname=_AMIRI_B)

        self.alias_nb_pages()
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)
        self.set_auto_page_break(auto=True, margin=18)

    # ── Internal font switchers ───────────────────────────────────────────────

    def _hv(self, style: str = "", size: float = 8) -> None:
        """Set Helvetica (Latin)."""
        self.set_font("Helvetica", style, size)

    def _am(self, style: str = "", size: float = 9) -> None:
        """Set Amiri (Arabic/Unicode) when available, else fall back to Helvetica."""
        if _HAVE_AMIRI:
            self.set_font("Amiri", style, size)
        else:
            self.set_font("Helvetica", style, size)

    # ── fpdf overrides ────────────────────────────────────────────────────────

    def footer(self) -> None:
        self.set_y(-14)
        self._am("", 7)
        self.set_text_color(*_MUTED)
        raw = _AR["footer_tpl"].format(date=self.date_str, page=self.page_no())
        self.cell(0, 8, _ar_text(raw), align="R")
        self.set_text_color(0, 0, 0)

    # ── Smart cell: auto-detects Arabic, switches font & alignment ────────────

    def _smart_cell(
        self,
        w: float,
        h: float,
        text,
        fill: bool = False,
        align: str = "R",
        base_size: float = 8,
    ) -> None:
        """
        Draw a single table cell.  Arabic text → Amiri + right-align.
        Latin text → Helvetica + requested align (default "R" for RTL layout).
        """
        s = str(text)
        if _is_arabic(s):
            self._am("", base_size + 1)
            display = _ar_text(s)
            self.cell(w, h, display, fill=fill, align="R")
            self._hv("", base_size)
        else:
            self._hv("", base_size)
            self.cell(w, h, _safe_latin(s), fill=fill, align=align)

    def _smart_multicell(self, w: float, h: float, text, base_size: float = 9) -> None:
        """
        Draw a multi-line block.  Arabic → Amiri + bidi + right-align.
        Latin → Helvetica + left-align (user notes may be in any language).
        """
        s = str(text)
        if _is_arabic(s):
            self._am("", base_size + 1)
            display = _ar_text(s)
            self.multi_cell(w, h, display, align="R", ln=True)
            self._hv("", base_size)
        else:
            self._hv("", base_size)
            self.multi_cell(w, h, _safe_latin(s), ln=True)

    # ── Drawing helpers ───────────────────────────────────────────────────────

    def section_header(self, title: str, subtitle: str = "") -> None:
        """Blue band with Arabic title, right-aligned."""
        self.set_fill_color(*_BLUE)
        self.set_text_color(*_WHITE)
        self._am("B", 12)
        self.cell(0, 8, _ar_text(title), fill=True, ln=True, align="R")
        if subtitle:
            self._am("", 8)
            self.set_text_color(*_MUTED)
            self.cell(0, 5, _ar_text(subtitle), ln=True, align="R")
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def table_header(self, cols: list[str], widths: list[int]) -> None:
        """Dark band with Arabic column headers, right-aligned."""
        self.set_fill_color(*_DARK)
        self.set_text_color(*_WHITE)
        self._am("B", 9)
        for col, w in zip(cols, widths):
            self.cell(w, 6, _ar_text(col), fill=True, align="R")
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
        aligns = aligns or (["R"] * len(vals))
        for v, w, a in zip(vals, widths, aligns):
            self._smart_cell(w, 5, v, fill=True, align=a, base_size=8)
        self.ln()

    def total_row(
        self,
        label: str,
        label_w: int,
        value: str,
        value_w: int,
        rtl: bool = False,
    ) -> None:
        """
        Total / summary row.
        rtl=True  →  value (number) on the LEFT, label (Arabic) on the RIGHT.
        rtl=False →  label on the left, value on the right (legacy).
        """
        self.set_fill_color(*_DARK)
        self.set_text_color(*_WHITE)
        if rtl:
            self._hv("B", 8)
            self.cell(value_w, 6, _safe_latin(value), fill=True, align="R")
            self._am("B", 9)
            self.cell(label_w, 6, _ar_text(label), fill=True, align="R")
        else:
            self._hv("B", 8)
            self.cell(label_w, 6, _safe_latin(f"  {label}"), fill=True)
            self.cell(value_w, 6, _safe_latin(value), fill=True, align="R")
        self.ln()
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def kv_row(self, label: str, value: str, even: bool) -> None:
        self.set_fill_color(*(_LIGHT if even else _WHITE))
        self._am("B", 8)
        self.cell(60, 5, _ar_text(label), fill=True, align="R")
        self._smart_cell(_W - 60, 5, value, fill=True, base_size=8)
        self.ln()

    def detail_row(self, text: str) -> None:
        """
        Muted sub-row spanning full width — used for custodian, institution,
        or free-text notes beneath each main table row.
        Skipped automatically when text is blank.
        """
        if not str(text).strip():
            return
        self.set_fill_color(245, 247, 250)
        self.set_text_color(*_MUTED)
        # Prefix uses Helvetica (ASCII-safe); text body uses smart font detection.
        self._hv("", 7)
        self.cell(10, 4, "   >>", fill=True, align="L")
        self._smart_cell(_W - 10, 4, str(text), fill=True, align="R", base_size=7)
        self.ln()
        self.set_text_color(0, 0, 0)


# ── RTL column helper ──────────────────────────────────────────────────────────

def _rtl(cols: list, wids: list, aligns: list | None = None):
    """Return (cols, wids, aligns) reversed for RTL table layout."""
    return (
        list(reversed(cols)),
        list(reversed(wids)),
        list(reversed(aligns)) if aligns else None,
    )


# ── Main builder ───────────────────────────────────────────────────────────────

def build_wealth_statement(base_ccy: str = "SAR", notes: str = "") -> bytes:
    """
    Build and return a Family Wealth Statement as a PDF (raw bytes).

    Parameters
    ----------
    base_ccy : str
        Base currency for converted totals (e.g. "SAR").
    notes : str
        Optional personal message printed on the final page.
        Supports Arabic and Latin text.

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
    from portfolio.liabilities import load_liabilities, compute_liabilities_base
    from portfolio.valuation import calculate_portfolio_valuation
    from fx_rates import get_rates_for_holdings

    # Load & filter
    holdings = load_holdings()
    accounts = load_accounts()
    igi  = {k: v for k, v in load_igi_investments().items() if v.status != "Closed"}
    cf   = {k: v for k, v in load_cf_accounts().items()    if v.status == "Active"}
    fa   = {k: v for k, v in load_fixed_assets().items()   if v.status == "Active"}
    libs = {k: v for k, v in load_liabilities().items()    if v.status == "Active"}

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
    for lib in libs.values():
        ccys.add(lib.currency)

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
    igi_base   = sum(inv.current_value        * _rate(fx, inv.currency) for inv in igi.values())
    cf_base    = sum(a.current_account_value  * _rate(fx, a.currency)   for a   in cf.values())
    fa_base    = sum(a.equity                 * _rate(fx, a.currency)   for a   in fa.values())
    liab_base  = compute_liabilities_base(libs, base_ccy, fx)
    gross_nw   = port_mv_base + cash_base + igi_base + cf_base + fa_base
    nw         = gross_nw - liab_base

    today_str = _date.today().strftime("%d %B %Y")
    pdf = _WealthPDF(base_ccy, today_str)

    # =========================================================================
    # PAGE 1 -- COVER  (RTL: all text right-aligned)
    # =========================================================================
    pdf.add_page()

    # Dark header band
    pdf.set_fill_color(*_DARK)
    pdf.rect(0, 0, 210, 52, "F")
    pdf.set_xy(_MARGIN, 8)
    pdf.set_text_color(*_WHITE)

    pdf._am("B", 9)
    pdf.cell(0, 7, _ar_text(_AR["app_name"]), ln=True, align="R")
    pdf.set_x(_MARGIN)
    pdf._am("B", 20)
    pdf.cell(0, 10, _ar_text(_AR["doc_title"]), ln=True, align="R")
    pdf.set_x(_MARGIN)
    pdf._am("", 10)
    prepared_line = (
        f"{_AR['prepared']} {today_str}"
        f"  |  {_AR['base_ccy_lbl']}: {base_ccy}"
        f"  |  {_AR['confidential']}"
    )
    pdf.cell(0, 7, _ar_text(prepared_line), ln=True, align="R")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(20)

    # Introduction paragraph
    pdf._am("", 10)
    pdf.set_text_color(*_TEXT)
    pdf.multi_cell(
        0, 6,
        _ar_text(_AR["intro"].format(base_ccy=base_ccy)),
        align="R",
        ln=True,
    )
    pdf.ln(5)

    # Net worth highlight
    pdf.set_fill_color(*_DARK)
    pdf.set_text_color(*_WHITE)
    pdf._am("B", 13)
    nw_banner = f"{_AR['total_nw']}  --  {base_ccy} {_m(nw)}"
    pdf.cell(0, 12, _ar_text(nw_banner), fill=True, ln=True, align="R")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)

    # Cover snapshot heading
    pdf._am("B", 9)
    pdf.set_text_color(*_MUTED)
    pdf.cell(0, 5, _ar_text(_AR["snapshot"]), ln=True, align="R")
    pdf.set_text_color(0, 0, 0)

    # Cover summary table — RTL: [value(52) | category(130)]
    _sw_ltr = [_W - 52, 52]
    _sw_r   = list(reversed(_sw_ltr))   # [52, _W - 52]
    _summary = [
        (_AR["cat_portfolio"], port_mv_base),
        (_AR["cat_alt"],       igi_base),
        (_AR["cat_cash"],      cash_base + cf_base),
        (_AR["cat_fa"],        fa_base),
    ]
    if liab_base > 0:
        _summary.append((_AR["cat_liab"], -liab_base))
    pdf.table_header(
        [f"{_AR['col_value']} ({base_ccy})", _AR["col_category"]],
        _sw_r,
    )
    for i, (lbl, amt) in enumerate(_summary):
        pdf.table_row([_m(amt), lbl], _sw_r, i % 2 == 0, ["R", "R"])
    pdf.total_row(
        _AR["total_nw"], _sw_r[1],
        f"{base_ccy} {_m(nw)}", _sw_r[0],
        rtl=True,
    )

    pdf.ln(2)
    pdf._am("", 7)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(0, 5, _ar_text(_AR["cover_note"]), align="R", ln=True)
    pdf.set_text_color(0, 0, 0)

    # =========================================================================
    # SECTION 1 -- INVESTMENT PORTFOLIO
    # =========================================================================
    if holdings:
        pdf.add_page()
        pdf.section_header(_AR["sec1_title"], _AR["sec1_sub"])

        # LTR order: Company(60) | Ticker(16) | Shares(18) | Price(26) | Val CCY(32) | Val Base(30)
        # RTL order: Val Base(30) | Val CCY(32) | Price(26) | Shares(18) | Ticker(16) | Company(60)
        _wids_ltr = [60, 16, 18, 26, 32, 30]
        _wids_r   = list(reversed(_wids_ltr))  # [30, 32, 26, 18, 16, 60]
        _cols_r   = [
            f"{_AR['col_val_base']} ({base_ccy})",
            _AR["col_val_ccy"],
            _AR["col_price"],
            _AR["col_shares"],
            _AR["col_ticker"],
            _AR["col_company"],
        ]
        pdf.table_header(_cols_r, _wids_r)

        _sec_total = 0.0
        for i, h in enumerate(
            sorted(holdings.values(), key=lambda x: (x.company_name or x.ticker or ""))
        ):
            mv   = h.market_value
            mv_b = mv * _rate(fx, h.currency)
            _sec_total += mv_b
            vals_r = [
                _m(mv_b),
                f"{h.currency} {_m(mv)}",
                f"{h.currency} {_m(h.current_price)}",
                _q(h.quantity),
                _clip(h.ticker, 10),
                _clip(h.company_name or h.ticker, 32),
            ]
            pdf.table_row(vals_r, _wids_r, i % 2 == 0, ["R"] * 6)
            # ── Custodian sub-row ─────────────────────────────────────────────
            _h_acct = accounts.get(getattr(h, "default_account_id", "") or "")
            if _h_acct:
                _held = f"{_AR['detail_held_at']}: {_h_acct.account_name or ''}"
                if _h_acct.institution:
                    _held += f"  |  {_h_acct.institution}"
                pdf.detail_row(_held)
            # ── Notes sub-row ─────────────────────────────────────────────────
            _h_notes = getattr(h, "notes", "") or ""
            if _h_notes.strip():
                pdf.detail_row(f"{_AR['detail_note']}: {_h_notes.strip()}")

        pdf.total_row(
            _AR["total_hld"].format(n=len(holdings)),
            sum(_wids_r[1:]),                    # = sum(_wids_ltr[:-1])
            f"{base_ccy} {_m(_sec_total)}",
            _wids_r[0],                          # = _wids_ltr[-1]
            rtl=True,
        )

    # =========================================================================
    # SECTION 2 -- ALTERNATIVE INVESTMENTS
    # =========================================================================
    if igi:
        pdf.add_page()
        pdf.section_header(_AR["sec2_title"], _AR["sec2_sub"])

        # LTR: InvName(56) | Type(30) | Status(26) | Ccy(16) | Val CCY(26) | Val Base(28)
        # RTL: Val Base(28) | Val CCY(26) | Ccy(16) | Status(26) | Type(30) | InvName(56)
        _wids_ltr = [56, 30, 26, 16, 26, 28]
        _wids_r   = list(reversed(_wids_ltr))  # [28, 26, 16, 26, 30, 56]
        _cols_r   = [
            f"{_AR['col_val_base']} ({base_ccy})",
            _AR["col_val_ccy"],
            _AR["col_currency"],
            _AR["col_status"],
            _AR["col_type"],
            _AR["col_inv_name"],
        ]
        pdf.table_header(_cols_r, _wids_r)

        _sec_total = 0.0
        for i, inv in enumerate(sorted(igi.values(), key=lambda x: x.investment_name)):
            rate  = _rate(fx, inv.currency)
            val_b = inv.current_value * rate
            _sec_total += val_b
            vals_r = [
                _m(val_b),
                f"{inv.currency} {_m(inv.current_value)}",
                inv.currency,
                _clip(inv.status, 14),
                _clip(inv.sharia_structure or "N/A", 18),
                _clip(inv.investment_name, 34),
            ]
            pdf.table_row(vals_r, _wids_r, i % 2 == 0, ["R"] * 6)
            # ── Institution sub-row ───────────────────────────────────────────
            _inv_inst = getattr(inv, "institution", "") or ""
            if _inv_inst.strip():
                pdf.detail_row(f"{_AR['detail_inst']}: {_inv_inst.strip()}")
            # ── Notes sub-row ─────────────────────────────────────────────────
            _inv_notes = getattr(inv, "notes", "") or ""
            if _inv_notes.strip():
                pdf.detail_row(f"{_AR['detail_note']}: {_inv_notes.strip()}")

        pdf.total_row(
            _AR["total_inv"].format(n=len(igi)),
            sum(_wids_r[1:]),
            f"{base_ccy} {_m(_sec_total)}",
            _wids_r[0],
            rtl=True,
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
        pdf.section_header(_AR["sec3_title"], _AR["sec3_sub"])

        # LTR: AccName(50) | Inst(38) | Type(26) | Ccy(16) | Bal CCY(24) | Bal Base(28)
        # RTL: Bal Base(28) | Bal CCY(24) | Ccy(16) | Type(26) | Inst(38) | AccName(50)
        _wids_ltr = [50, 38, 26, 16, 24, 28]
        _wids_r   = list(reversed(_wids_ltr))  # [28, 24, 16, 26, 38, 50]
        _cols_r   = [
            f"{_AR['col_bal_base']} ({base_ccy})",
            _AR["col_bal_ccy"],
            _AR["col_currency"],
            _AR["col_acc_type"],
            _AR["col_inst"],
            _AR["col_acc_name"],
        ]
        pdf.table_header(_cols_r, _wids_r)

        _sec_total = 0.0
        all_rows = (
            sorted(_acct_rows, key=lambda r: r[0])
            + sorted(_cf_rows, key=lambda r: r[0])
        )
        for i, (nm, inst, typ, ccy, bal, bal_b) in enumerate(all_rows):
            _sec_total += bal_b
            vals_r = [
                _m(bal_b),
                f"{ccy} {_m(bal)}",
                ccy,
                typ,
                _clip(inst, 22),
                _clip(nm, 28),
            ]
            pdf.table_row(vals_r, _wids_r, i % 2 == 0, ["R"] * 6)

        pdf.total_row(
            _AR["total_accts"].format(n=len(all_rows)),
            sum(_wids_r[1:]),
            f"{base_ccy} {_m(_sec_total)}",
            _wids_r[0],
            rtl=True,
        )

    # =========================================================================
    # SECTION 4 -- PROPERTIES, VEHICLES & RETIREMENT
    # =========================================================================
    if fa:
        pdf.add_page()
        pdf.section_header(_AR["sec4_title"], _AR["sec4_sub"])

        # LTR: Name(44) | Cat(30) | Ccy(16) | CurVal(24) | Loan(24) | Equity(20) | EqBase(24)
        # RTL: EqBase(24) | Equity(20) | Loan(24) | CurVal(24) | Ccy(16) | Cat(30) | Name(44)
        _wids_ltr = [44, 30, 16, 24, 24, 20, 24]
        _wids_r   = list(reversed(_wids_ltr))  # [24, 20, 24, 24, 16, 30, 44]
        _cols_r   = [
            f"{_AR['col_eq_base']} ({base_ccy})",
            _AR["col_equity"],
            _AR["col_loan"],
            _AR["col_cur_val"],
            _AR["col_currency"],
            _AR["col_asset_cat"],
            _AR["col_asset"],
        ]
        pdf.table_header(_cols_r, _wids_r)

        _sec_total = 0.0
        for i, asset in enumerate(sorted(fa.values(), key=lambda a: a.name)):
            rate   = _rate(fx, asset.currency)
            eq_b   = asset.equity * rate
            _sec_total += eq_b
            vals_r = [
                _m(eq_b),
                _m(asset.equity),
                _m(asset.outstanding_liability),
                _m(asset.current_value),
                asset.currency,
                _clip(asset.asset_type, 18),
                _clip(asset.name, 26),
            ]
            pdf.table_row(vals_r, _wids_r, i % 2 == 0, ["R"] * 7)
            # ── Notes sub-row (physical location, custodian, etc.) ────────────
            _fa_notes = getattr(asset, "notes", "") or ""
            if _fa_notes.strip():
                pdf.detail_row(f"{_AR['detail_note']}: {_fa_notes.strip()}")

        pdf.total_row(
            _AR["total_assets"].format(n=len(fa)),
            sum(_wids_r[1:]),
            f"{base_ccy} {_m(_sec_total)}",
            _wids_r[0],
            rtl=True,
        )

    # =========================================================================
    # SECTION 5 -- LIABILITIES
    # =========================================================================
    if libs:
        pdf.add_page()
        pdf.section_header(_AR["sec5_liab_title"], _AR["sec5_liab_sub"])

        # LTR: Name(48) | Type(28) | Lender(32) | Ccy(14) | Balance(30) | Base(30)
        # RTL: Base(30) | Balance(30) | Ccy(14) | Lender(32) | Type(28) | Name(48)
        _wids_ltr = [48, 28, 32, 14, 30, 30]
        _wids_r   = list(reversed(_wids_ltr))
        _cols_r   = [
            f"{_AR['col_bal_base']} ({base_ccy})",
            _AR["col_bal_ccy"],
            _AR["col_currency"],
            _AR["col_lender"],
            _AR["col_type"],
            _AR["col_liab_name"],
        ]
        pdf.table_header(_cols_r, _wids_r)

        _sec_total = 0.0
        for i, lib in enumerate(sorted(libs.values(), key=lambda x: x.name)):
            rate   = _rate(fx, lib.currency)
            bal_b  = lib.outstanding_balance * rate
            _sec_total += bal_b
            vals_r = [
                _m(bal_b),
                _m(lib.outstanding_balance),
                lib.currency,
                _clip(lib.lender or "-", 18),
                _clip(lib.liability_type, 16),
                _clip(lib.name, 28),
            ]
            pdf.table_row(vals_r, _wids_r, i % 2 == 0, ["R"] * 6)

        pdf.total_row(
            _AR["total_liab"].format(n=len(libs)),
            sum(_wids_r[1:]),
            f"{base_ccy} {_m(_sec_total)}",
            _wids_r[0],
            rtl=True,
        )

    # =========================================================================
    # SECTION 6 -- CONSOLIDATED SUMMARY (was Section 5)
    # =========================================================================
    pdf.add_page()
    pdf.section_header(_AR["sec5_title"], _AR["sec5_sub"])

    # RTL: [total(52) | asset_group(_W-52)]
    _sw5_ltr = [_W - 52, 52]
    _sw5_r   = list(reversed(_sw5_ltr))   # [52, _W - 52]
    _sec5_assets = [
        (_AR["cat_port_mv"],  port_mv_base),
        (_AR["cat_alt_inv"],  igi_base),
        (_AR["cat_cash_brk"], cash_base),
        (_AR["cat_cf"],       cf_base),
        (_AR["cat_fa_sec"],   fa_base),
    ]
    pdf.table_header(
        [f"{_AR['col_total']} ({base_ccy})", _AR["col_asset_grp"]],
        _sw5_r,
    )
    for i, (lbl, amt) in enumerate(_sec5_assets):
        pdf.table_row([_m(amt), lbl], _sw5_r, i % 2 == 0, ["R", "R"])
    if liab_base > 0:
        row_idx = len(_sec5_assets)
        pdf.table_row([_m(-liab_base), _AR["cat_liab"]], _sw5_r, row_idx % 2 == 0, ["R", "R"])
    pdf.total_row(
        _AR["total_nw"], _sw5_r[1],
        f"{base_ccy} {_m(nw)}", _sw5_r[0],
        rtl=True,
    )

    pdf.ln(3)
    pdf._am("B", 9)
    pdf.set_text_color(*_MUTED)
    pdf.cell(0, 5, _ar_text(_AR["alloc"]), ln=True, align="R")
    pdf.set_text_color(0, 0, 0)

    if gross_nw > 0:
        pdf.table_header([_AR["col_alloc"], _AR["col_asset_grp"]], _sw5_r)
        for i, (lbl, amt) in enumerate(_sec5_assets):
            pct = amt / gross_nw * 100
            pdf.table_row([f"{pct:.1f}%", lbl], _sw5_r, i % 2 == 0, ["R", "R"])
    else:
        pdf._am("", 9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(0, 6, _ar_text(_AR["no_assets"]), ln=True, align="R")
        pdf.set_text_color(0, 0, 0)

    # =========================================================================
    # NOTES PAGE -- Account Directory & Personal Message
    # =========================================================================
    pdf.add_page()
    pdf.section_header(_AR["notes_title"])

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
            _dir_rows.append((
                f"{a.account_name} ({_AR['crowdfunding']})",
                inst,
            ))

    if _dir_rows:
        pdf._am("B", 9)
        pdf.set_text_color(*_TEXT)
        pdf.cell(0, 6, _ar_text(_AR["dir_heading"]), ln=True, align="R")
        pdf.ln(1)
        # RTL: institution(60) on left | account/investment(_W-60) on right
        _dir_wids_r = [60, _W - 60]
        pdf.table_header([_AR["col_inst2"], _AR["col_acc_inv"]], _dir_wids_r)
        for i, (acc, inst) in enumerate(_dir_rows):
            pdf.table_row(
                [_clip(inst, 34), _clip(acc, 55)],
                _dir_wids_r, i % 2 == 0, ["R", "R"],
            )
        pdf.ln(5)

    # Personal note box
    pdf.set_fill_color(*_LIGHT)
    pdf._am("B", 9)
    pdf.set_text_color(*_TEXT)
    pdf.cell(0, 7, _ar_text(_AR["note_heading"]), fill=True, ln=True, align="R")
    pdf.ln(2)
    if notes and notes.strip():
        pdf._smart_multicell(0, 6, notes.strip(), base_size=9)
    else:
        pdf._am("", 9)
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(0, 6, _ar_text(_AR["no_note"]), align="R", ln=True)
    pdf.set_text_color(0, 0, 0)

    # Legal disclaimer
    pdf.ln(8)
    pdf.set_draw_color(*_MUTED)
    pdf.line(_MARGIN, pdf.get_y(), _MARGIN + _W, pdf.get_y())
    pdf.ln(3)
    pdf._am("", 7)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(0, 5, _ar_text(_AR["disclaimer"]), align="R", ln=True)

    return bytes(pdf.output())
