"""
portfolio/thesis_importer.py
----------------------------
Import a Core Thesis from a PDF / DOCX / TXT research document.

Pipeline:
  1. Extract raw text from the upload (pdfplumber for PDF; stdlib zipfile +
     XML for DOCX — avoids the python-docx native dependency; plain decode
     for TXT)
  2. Send the text to OpenAI with a strict JSON schema describing every
     thesis field plus bull/base/bear scenarios and the risk/return matrix
  3. Build a `CoreThesis` instance from the extracted data, tagged with
     provenance (source_type=Imported, imported_from, imported_at)
  4. The caller (UI) previews + lets the user edit before persisting

Nothing here writes to disk — persistence is owned by `core_thesis.save_*`.
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from dataclasses import asdict
from datetime import datetime
from xml.etree import ElementTree as ET

from .core_thesis import (
    RISK_CATEGORIES, RISK_KINDS, RISK_SEVERITIES, RISK_STATUSES,
    TIME_HORIZONS,
    CoreThesis, RiskMatrixItem, ScenarioCase,
)

# ── Limits ───────────────────────────────────────────────────────────────────
MAX_BYTES        = 8 * 1024 * 1024     # 8 MB upload cap
MAX_EXTRACT_CHARS = 60_000             # truncate extracted text for the LLM


class ImportError_(Exception):
    """Raised when the upload cannot be read or parsed."""


class ThesisQuotaExceeded(ImportError_):
    """Raised when the OpenAI account has no remaining quota / billing.

    The UI catches this specifically to offer the rule-based fallback,
    which works fully offline on DOCX/TXT/PDF-extracted text.
    """


# ── File → text extraction ───────────────────────────────────────────────────

def detect_kind(filename: str) -> str:
    """Return 'PDF' | 'DOCX' | 'TXT' | '' based on extension."""
    if not filename:
        return ""
    ext = os.path.splitext(filename.lower())[1]
    return {".pdf": "PDF", ".docx": "DOCX", ".txt": "TXT", ".md": "TXT"}.get(ext, "")


def extract_text(file_bytes: bytes, filename: str) -> tuple[str, str]:
    """Return (extracted_text, kind). Raises ImportError_ on failure."""
    if not file_bytes:
        raise ImportError_("Uploaded file is empty.")
    if len(file_bytes) > MAX_BYTES:
        raise ImportError_(
            f"File too large ({len(file_bytes)/1_000_000:.1f} MB). "
            f"Maximum is {MAX_BYTES // 1_000_000} MB."
        )

    kind = detect_kind(filename)
    if kind == "PDF":
        text = _extract_pdf(file_bytes)
    elif kind == "DOCX":
        text = _extract_docx(file_bytes)
    elif kind == "TXT":
        text = _extract_txt(file_bytes)
    else:
        raise ImportError_(
            f"Unsupported file type: '{filename}'. Upload PDF, DOCX, or TXT."
        )

    text = (text or "").strip()
    if not text:
        raise ImportError_(
            "Could not extract any text from this document. "
            "If it is a scanned PDF, please paste the thesis as TXT instead."
        )
    if len(text) > MAX_EXTRACT_CHARS:
        text = text[:MAX_EXTRACT_CHARS] + "\n\n[... document truncated ...]"
    return text, kind


def _extract_pdf(data: bytes) -> str:
    try:
        import pdfplumber
    except ImportError as e:
        raise ImportError_("pdfplumber is not installed.") from e
    out: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""
                if page_text:
                    out.append(page_text)
    except Exception as e:
        raise ImportError_(f"Could not parse PDF: {e}") from e
    return "\n\n".join(out)


def _extract_docx(data: bytes) -> str:
    """Read DOCX without python-docx — DOCX is a zip of XML.

    Walks the body in document order. Plain paragraphs are emitted as text
    lines. Tables are emitted as pipe-delimited rows ('| cell1 | cell2 |')
    so the rule-based extractor can rebuild the Risk/Return Matrix.
    """
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if "word/document.xml" not in z.namelist():
                raise ImportError_("DOCX archive is missing word/document.xml")
            xml_bytes = z.read("word/document.xml")
    except zipfile.BadZipFile as e:
        raise ImportError_(f"Not a valid DOCX file: {e}") from e

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ImportError_(f"DOCX XML could not be parsed: {e}") from e

    body = root.find(f"{ns}body")
    if body is None:
        return ""

    def _para_text(p) -> str:
        return "".join((t.text or "") for t in p.iter(f"{ns}t")).strip()

    def _cell_text(tc) -> str:
        # Join paragraphs inside the cell with " / " so a multi-line cell
        # like an "early warning indicators" list stays on one row.
        parts = [_para_text(p) for p in tc.findall(f"{ns}p")]
        parts = [p for p in parts if p]
        return " / ".join(parts)

    lines: list[str] = []
    for child in body:
        tag = child.tag
        if tag == f"{ns}p":
            line = _para_text(child)
            if line:
                lines.append(line)
        elif tag == f"{ns}tbl":
            lines.append("")  # table separator
            for row in child.findall(f"{ns}tr"):
                cells = [_cell_text(tc) for tc in row.findall(f"{ns}tc")]
                if any(cells):
                    lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
    return "\n".join(lines)


def _extract_txt(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# ── AI extraction ─────────────────────────────────────────────────────────────

_EXTRACTION_SYSTEM_PROMPT = """You are a senior buy-side equity analyst. \
You are reading an investment research document (research note, pitch memo, \
broker report, IC memo, etc.) and your job is to extract the original \
investment thesis as faithfully as possible into a strict JSON schema.

CRITICAL RULES:
- Extract ONLY what is plainly stated or strongly implied in the document.
- If a field is not present, return "" (string fields) or [] (list fields).
- Do NOT invent scenarios, probabilities, valuation targets, or risks that \
are not in the document. Leave them empty rather than guessing.
- Probabilities are integers 0-100; bull+base+bear should sum to ~100 if \
the document discusses probabilities, otherwise leave all three at 0.
- Keep each list item concise (one phrase per item).

You MUST return valid JSON matching exactly this schema:
{
  "rationale": "1-3 sentence summary of why this position exists",
  "thesis_drivers": ["short driver 1", "driver 2", ...],
  "expected_value_drivers": ["financial outcomes the thesis depends on"],
  "expected_catalysts": ["upcoming events that unlock value"],
  "key_risks": ["risks accepted at purchase"],
  "management_execution_assumptions": ["what mgmt must do for thesis to work"],
  "expected_moat": "one-liner on competitive advantage",
  "expected_management": "expected behavior of management team",
  "expected_margin_profile": "e.g. operating margin expanding to 30%+",
  "expected_growth_profile": "e.g. 15-20% revenue CAGR for 3 years",
  "time_horizon": "one of: 6-12 months | 1-3 years | 3-5 years | 5+ years",
  "valuation_thesis": "one-liner on valuation case",
  "bull_case": {
    "description": "bull scenario narrative",
    "probability": 0,
    "valuation_target": "e.g. $250/share at 25x FCF",
    "key_assumptions": ["assumption 1", "assumption 2"]
  },
  "base_case":  {"description": "...", "probability": 0, "valuation_target": "", "key_assumptions": []},
  "bear_case":  {"description": "...", "probability": 0, "valuation_target": "", "key_assumptions": []},
  "risk_matrix": [
    {
      "name": "Risk or opportunity name",
      "category": "one of: Regulatory | Competitive | Execution | Macro | Financial | Technology | ESG | Geopolitical | Other",
      "kind": "Risk | Opportunity",
      "severity": "Low | Medium | High | Critical",
      "current_status": "Active | Monitoring | Realized | Mitigated | Closed",
      "expected_impact": "narrative on financial / strategic impact",
      "early_warning_indicators": ["leading indicator 1", ...],
      "required_action": "what to do if this materialises",
      "possible_hedge": "hedging suggestion or empty"
    }
  ]
}
"""


def _coerce_str(x) -> str:
    if x is None: return ""
    if isinstance(x, str): return x.strip()
    return str(x).strip()


def _coerce_list(x) -> list[str]:
    if x is None: return []
    if isinstance(x, list):
        return [_coerce_str(i) for i in x if _coerce_str(i)]
    if isinstance(x, str):
        return [s.strip() for s in re.split(r"[\n;•·]+", x) if s.strip()]
    return []


def _coerce_probability(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, v))


def _coerce_horizon(x) -> str:
    s = _coerce_str(x)
    if not s:
        return "1-3 years"
    # Exact match first
    for h in TIME_HORIZONS:
        if h.lower() == s.lower():
            return h
    # Numeric fingerprint match — pull all ints, compare to each horizon's ints
    nums = [int(n) for n in re.findall(r"\d+", s)]
    months = "month" in s.lower()
    plus   = "+" in s
    for h in TIME_HORIZONS:
        h_nums = [int(n) for n in re.findall(r"\d+", h)]
        if "month" in h.lower():
            if months and nums == h_nums:
                return h
        elif "+" in h:
            if plus and nums == h_nums:
                return h
        else:
            # ranges like "1-3" or "3-5" — exact int-set match
            if not months and set(nums) == set(h_nums):
                return h
    return "1-3 years"


def _coerce_scenario_dict(d: dict) -> dict:
    if not isinstance(d, dict): d = {}
    return {
        "description":      _coerce_str(d.get("description")),
        "probability":      _coerce_probability(d.get("probability")),
        "valuation_target": _coerce_str(d.get("valuation_target")),
        "key_assumptions":  _coerce_list(d.get("key_assumptions")),
    }


def _coerce_risk_dict(d: dict) -> dict | None:
    if not isinstance(d, dict): return None
    name = _coerce_str(d.get("name"))
    if not name:
        return None
    cat = _coerce_str(d.get("category")) or "Other"
    if cat not in RISK_CATEGORIES: cat = "Other"
    kind = _coerce_str(d.get("kind")) or "Risk"
    if kind not in RISK_KINDS: kind = "Risk"
    sev = _coerce_str(d.get("severity")) or "Medium"
    if sev not in RISK_SEVERITIES: sev = "Medium"
    status = _coerce_str(d.get("current_status")) or "Monitoring"
    if status not in RISK_STATUSES: status = "Monitoring"
    return {
        "name":                     name,
        "category":                 cat,
        "kind":                     kind,
        "severity":                 sev,
        "current_status":           status,
        "expected_impact":          _coerce_str(d.get("expected_impact")),
        "early_warning_indicators": _coerce_list(d.get("early_warning_indicators")),
        "required_action":          _coerce_str(d.get("required_action")),
        "possible_hedge":           _coerce_str(d.get("possible_hedge")),
    }


def _resolve_api_key(explicit: str | None = None, st_secrets=None) -> str:
    """Mirror `ai/analyzer.get_api_key` so importer & analyzer agree on
    whether AI is configured (env first, then st.secrets fallback)."""
    if explicit:
        k = explicit.strip()
        if k:
            return k
    k = os.environ.get("OPENAI_API_KEY", "").strip()
    if k:
        return k
    if st_secrets is not None:
        try:
            k = (st_secrets.get("OPENAI_API_KEY") or "").strip()
            if k:
                return k
        except Exception:
            pass
    return ""


def extract_thesis_from_text(
    text:         str,
    ticker:       str,
    company_name: str,
    *,
    api_key:      str | None = None,
    st_secrets=None,
    model:        str = "gpt-4o-mini",
) -> dict:
    """Call OpenAI to extract a thesis dict from the supplied document text.

    Returns a dict whose keys match `CoreThesis` fields plus `bull_case`,
    `base_case`, `bear_case`, and `risk_matrix`. Never raises on AI failure —
    raises only on hard config errors (missing API key).
    """
    api_key = _resolve_api_key(api_key, st_secrets)
    if not api_key:
        raise ImportError_(
            "OpenAI API key not configured. Set OPENAI_API_KEY in Secrets "
            "to use AI thesis extraction."
        )

    user_prompt = (
        f"Ticker: {ticker}\nCompany: {company_name}\n\n"
        f"--- INVESTMENT RESEARCH DOCUMENT ---\n{text}"
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=3000,
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        # Detect quota / billing failure and surface a specific exception so
        # the UI can offer the rule-based fallback (Demo Mode for import).
        err = str(e).lower()
        if (
            "insufficient_quota" in err
            or "exceeded your current quota" in err
            or "billing" in err and "quota" in err
            or type(e).__name__ in ("RateLimitError", "APIStatusError")
            and ("quota" in err or "429" in err)
        ):
            raise ThesisQuotaExceeded(
                "OpenAI quota exhausted — no remaining credits on this API key."
            ) from e
        raise ImportError_(f"AI extraction failed: {e}") from e

    return _normalize_extraction(data)


# ── Rule-based fallback (Demo Mode for thesis import) ────────────────────────
#
# Recognises bilingual (English + Arabic) research-note structure. Extracts:
#   • Core thesis fields (rationale, drivers, catalysts, risks, horizon, …)
#   • Bull / Base / Bear scenarios with sub-fields (description, probability,
#     valuation target, key assumptions)
#   • Risk/Return Matrix from both Markdown/DOCX-style tables AND from
#     labeled risk blocks (Name → Category → Severity → Status → Impact →
#     Early Warning → Action → Hedge)
#   • Recommendation block (final recommendation, target price, entry zone,
#     stop loss, action plan) consolidated into valuation_thesis +
#     management_execution_assumptions
# Fields that aren't present in the document are left blank — no placeholders.

# Map of label → canonical section key. Sorted longest-first so "key risks"
# wins over "risks". Matching is case-insensitive and Unicode-safe.
_SECTION_LABELS: list[tuple[str, str]] = sorted([
    # ── rationale / summary / overview ────────────────────────────────
    ("investment thesis",       "rationale"),
    ("thesis summary",          "rationale"),
    ("summary",                 "rationale"),
    ("overview",                "rationale"),
    ("thesis",                  "rationale"),
    ("الملخص التنفيذي",         "rationale"),
    ("الملخص",                  "rationale"),
    ("نظرة عامة",               "rationale"),
    ("الأطروحة الاستثمارية",    "rationale"),
    ("التقييم الاستراتيجي",     "rationale"),
    # ── drivers ───────────────────────────────────────────────────────
    ("expected value drivers",  "value_drivers"),
    ("value drivers",           "value_drivers"),
    ("thesis drivers",          "drivers"),
    ("key drivers",             "drivers"),
    ("drivers",                 "drivers"),
    ("المحركات الرئيسية",       "drivers"),
    ("محركات الأطروحة",         "drivers"),
    ("محركات النمو",            "drivers"),
    ("محركات القيمة",           "value_drivers"),
    ("محركات القيمة المتوقعة",  "value_drivers"),
    # ── catalysts ─────────────────────────────────────────────────────
    ("near-term catalysts",     "catalysts"),
    ("near term catalysts",     "catalysts"),
    ("expected catalysts",      "catalysts"),
    ("catalysts",               "catalysts"),
    ("catalyst",                "catalysts"),
    ("المحفزات",                "catalysts"),
    ("المحفزات المتوقعة",       "catalysts"),
    ("المحفزات قصيرة المدى",    "catalysts"),
    # ── risks (section-level — for free-text bullet list) ─────────────
    ("key risks",               "risks"),
    ("risk factors",            "risks"),
    ("downside risks",          "risks"),
    ("principal risks",         "risks"),
    ("risks",                   "risks"),
    ("risk",                    "risks"),
    ("المخاطر",                 "risks"),
    ("المخاطر الرئيسية",        "risks"),
    ("عوامل المخاطر",           "risks"),
    # ── Risk/Return Matrix (table + labeled blocks) ───────────────────
    ("risk / return matrix",    "risk_matrix"),
    ("risk return matrix",      "risk_matrix"),
    ("risk/return matrix",      "risk_matrix"),
    ("risk matrix",             "risk_matrix"),
    ("المصفوفة المحدثة",        "risk_matrix"),
    ("المصفوفة المحدّثة",       "risk_matrix"),
    ("مصفوفة المخاطر",          "risk_matrix"),
    ("مصفوفة المخاطر والعوائد", "risk_matrix"),
    # ── scenarios (parent block + individual cases) ───────────────────
    ("scenarios",               "scenarios"),
    ("scenario analysis",       "scenarios"),
    ("السيناريوهات",            "scenarios"),
    ("تحليل السيناريوهات",      "scenarios"),
    ("bull scenario",           "bull_case"),
    ("bull case",               "bull_case"),
    ("upside scenario",         "bull_case"),
    ("upside case",             "bull_case"),
    ("upside",                  "bull_case"),
    ("bull",                    "bull_case"),
    ("السيناريو الصاعد",        "bull_case"),
    ("السيناريو الإيجابي",      "bull_case"),
    ("السيناريو المتفائل",      "bull_case"),
    ("base scenario",           "base_case"),
    ("base case",               "base_case"),
    ("base",                    "base_case"),
    ("السيناريو الأساسي",       "base_case"),
    ("السيناريو المعتدل",       "base_case"),
    ("bear scenario",           "bear_case"),
    ("bear case",               "bear_case"),
    ("downside scenario",       "bear_case"),
    ("downside case",           "bear_case"),
    ("downside",                "bear_case"),
    ("bear",                    "bear_case"),
    ("السيناريو الهابط",        "bear_case"),
    ("السيناريو السلبي",        "bear_case"),
    ("السيناريو المتشائم",      "bear_case"),
    # ── recommendation block ──────────────────────────────────────────
    ("final recommendation",    "recommendation"),
    ("recommendation",          "recommendation"),
    ("rating",                  "recommendation"),
    ("التوصية النهائية",        "recommendation"),
    ("التوصية",                 "recommendation"),
    # ── valuation / target ────────────────────────────────────────────
    ("12-month target",         "target_price"),
    ("price target",            "target_price"),
    ("target price",            "target_price"),
    ("fair value",              "target_price"),
    ("intrinsic value",         "target_price"),
    ("valuation thesis",        "valuation_thesis"),
    ("valuation",               "valuation_thesis"),
    ("السعر المستهدف",          "target_price"),
    ("الهدف السعري",            "target_price"),
    ("القيمة العادلة",          "target_price"),
    ("التقييم",                 "valuation_thesis"),
    # ── trade plan ────────────────────────────────────────────────────
    ("entry zone",              "entry_zone"),
    ("entry range",             "entry_zone"),
    ("buy zone",                "entry_zone"),
    ("منطقة الدخول",            "entry_zone"),
    ("نطاق الدخول",             "entry_zone"),
    ("stop loss",               "stop_loss"),
    ("stop-loss",               "stop_loss"),
    ("وقف الخسارة",             "stop_loss"),
    ("حد الخسارة",              "stop_loss"),
    ("action plan",             "action_plan"),
    ("execution plan",          "action_plan"),
    ("خطة العمل",               "action_plan"),
    ("خطة الإجراءات",           "action_plan"),
    # ── horizon / moat / mgmt / margin / growth ───────────────────────
    ("competitive advantage",   "moat"),
    ("competitive moat",        "moat"),
    ("moat",                    "moat"),
    ("الميزة التنافسية",        "moat"),
    ("الخندق التنافسي",         "moat"),
    ("management execution",    "mgmt_assumptions"),
    ("execution assumptions",   "mgmt_assumptions"),
    ("افتراضات تنفيذ الإدارة",  "mgmt_assumptions"),
    ("management",              "management"),
    ("الإدارة",                 "management"),
    ("time horizon",            "horizon"),
    ("holding period",          "horizon"),
    ("horizon",                 "horizon"),
    ("الأفق الزمني",            "horizon"),
    ("مدة الاحتفاظ",            "horizon"),
    ("margin profile",          "margin_profile"),
    ("ملف الهامش",              "margin_profile"),
    ("growth profile",          "growth_profile"),
    ("ملف النمو",               "growth_profile"),
], key=lambda kv: -len(kv[0]))

_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•·●▪◦◯■◇►▶✔✓]|\d+[.)\-])\s+")

# Currency-prefixed OR currency-suffixed numbers. Supports $/€/£/¥, also
# Arabic suffixes: ر.س (SAR), د.إ (AED), ج.م (EGP), دينار/درهم/ريال/جنيه.
_PRICE_RE = re.compile(
    r"(?:"
    r"(?:\$|€|£|¥)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:bn|mn|m|b|k))?"
    r"|"
    r"\d[\d,]*(?:\.\d+)?\s?(?:ر\.س|د\.إ|ج\.م|ريال|درهم|دينار|جنيه|SAR|AED|EGP|USD|EUR)"
    r")",
    re.IGNORECASE,
)

# Section-header separators we'll split on. Includes ASCII colon, Arabic
# colon-like punctuation, en/em dashes.
_HEADER_SEP_CHARS = r":：\-—–"
_HEADER_SEP_RE    = re.compile(rf"[{_HEADER_SEP_CHARS}]")
_TRIM_TRAIL_RE    = re.compile(r"[\s:：.。؟،;؛\-—–]+$")

# Arabic ↔ Western digit map (so "٣٠٪" → "30%").
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _strip_bullet(line: str) -> str:
    return _BULLET_PREFIX_RE.sub("", line).strip()


def _norm_digits(s: str) -> str:
    return (s or "").translate(_AR_DIGITS)


def _detect_section_label(line: str) -> tuple[str, str] | None:
    """If `line` looks like a section header, return (canonical_key, body_on_same_line)."""
    s = _strip_bullet(line).strip()
    if not s:
        return None
    md = re.match(r"^#{1,6}\s+(.+?)\s*[:：]?\s*$", s)
    if md:
        s = md.group(1).strip()
    # Also strip surrounding markdown bold (**heading**)
    s = re.sub(r"^\*{1,3}(.+?)\*{1,3}$", r"\1", s).strip()
    low = s.lower().strip()
    low_trim = _TRIM_TRAIL_RE.sub("", low).strip()

    for label, key in _SECTION_LABELS:
        if low_trim == label:
            return key, ""
        if low.startswith(label):
            # Require a separator (`:` `-` `—` …) so we don't match prose
            sep_match = re.match(
                rf"^{re.escape(label)}\s*[{_HEADER_SEP_CHARS}]", s, re.I
            )
            if sep_match:
                tail = _HEADER_SEP_RE.split(s, maxsplit=1)
                body = tail[1].strip() if len(tail) > 1 else ""
                return key, body
    return None


_SCENARIO_KEYS              = {"bull_case", "base_case", "bear_case"}
# Labels that look like section headers globally but commonly appear AS
# SUB-FIELDS inside a scenario block (e.g. "Target Price: $45",
# "Key Drivers: …", "Summary: …"). When we're already inside a scenario,
# absorb these lines as scenario content instead of starting a new
# top-level section. The per-scenario parser (`_parse_scenario`) then
# extracts target/probability/assumptions from this absorbed text.
_SCENARIO_ABSORB_KEYS       = {
    "target_price", "valuation_thesis",
    "drivers", "value_drivers",
    "rationale",
}


def _split_sections(text: str) -> dict[str, str]:
    """Parse raw text into a {canonical_key: section_body} dict using
    label-based heuristics. Later occurrences of the same section append."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    buf: list[str] = []
    intro_buf: list[str] = []

    def flush():
        nonlocal buf
        if current and buf:
            sections.setdefault(current, []).append("\n".join(buf).strip())
        buf = []

    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        hit = _detect_section_label(line)
        if hit is not None:
            new_key = hit[0]
            # Inside a scenario, treat target/valuation sub-labels as content.
            if current in _SCENARIO_KEYS and new_key in _SCENARIO_ABSORB_KEYS:
                buf.append(line)
                continue
            flush()
            current = new_key
            if hit[1]:
                buf.append(hit[1])
        else:
            if current is None:
                if line.strip():
                    intro_buf.append(line.strip())
            else:
                buf.append(line)
    flush()

    out = {k: "\n".join(v).strip() for k, v in sections.items()}
    # Only fall back to intro-as-rationale when the document is otherwise
    # structured (at least one labeled section detected). For sparse /
    # unlabeled text we leave rationale blank, per the "no placeholders"
    # contract.
    if "rationale" not in out and intro_buf and len(out) >= 1:
        out["rationale"] = " ".join(intro_buf[:5])[:600]
    return out


def _split_bullets(body: str) -> list[str]:
    """Split a section body into bullet items."""
    if not body:
        return []
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if any(_BULLET_PREFIX_RE.match(ln) for ln in lines) or len(lines) > 1:
        items = [_strip_bullet(ln) for ln in lines]
        return [i for i in items if i]
    # Otherwise split on semicolons / Arabic comma / newlines
    parts = [p.strip(" .;–—-،؛") for p in re.split(r"[;؛\n]+", body)]
    return [p for p in parts if p and len(p) > 2]


def _extract_first_price(s: str) -> str:
    if not s: return ""
    m = _PRICE_RE.search(_norm_digits(s))
    return m.group(0).strip() if m else ""


def _coerce_horizon_from_text(text: str) -> str:
    """Detect time horizon from common English/Arabic phrases. Defaults to
    '1-3 years' since the field is a required closed-vocab dropdown."""
    low = _norm_digits((text or "").lower())
    pairs = [
        ("6-12 months",   ("6-12 months", "6 to 12 months", "6 الى 12 شهر",
                           "6 إلى 12 شهر", "ستة إلى اثني عشر شهر")),
        ("3-5 years",     ("3-5 years", "3 to 5 years", "3-5 سنوات",
                           "ثلاث إلى خمس سنوات")),
        ("5+ years",      ("5+ years", "5 plus years", "five plus years",
                           "أكثر من 5 سنوات", "اكثر من 5 سنوات", "5+ سنوات")),
        ("1-3 years",     ("1-3 years", "1 to 3 years", "1-3 سنوات",
                           "سنة إلى ثلاث سنوات")),
    ]
    for canonical, phrases in pairs:
        if any(p in low for p in phrases):
            return _coerce_horizon(canonical)
    return "1-3 years"


# ── Risk/Return Matrix taxonomy translation (English + Arabic) ───────────────

_CATEGORY_MAP = {
    "regulatory": "Regulatory", "regulation": "Regulatory",
    "competitive": "Competitive", "competition": "Competitive",
    "execution": "Execution", "operational": "Execution",
    "macro": "Macro", "macroeconomic": "Macro", "economic": "Macro",
    "financial": "Financial", "finance": "Financial",
    "technology": "Technology", "tech": "Technology",
    "esg": "ESG", "environmental": "ESG",
    "geopolitical": "Geopolitical", "political": "Geopolitical",
    "other": "Other",
    # Arabic
    "تنظيمي": "Regulatory", "تنظيمية": "Regulatory",
    "تنافسي": "Competitive", "تنافسية": "Competitive",
    "تنفيذي": "Execution",   "تنفيذية": "Execution", "تشغيلي": "Execution",
    "اقتصاد كلي": "Macro", "كلي": "Macro", "كلية": "Macro", "اقتصادي": "Macro",
    "مالي": "Financial", "مالية": "Financial",
    "تقني": "Technology", "تكنولوجي": "Technology", "تكنولوجيا": "Technology",
    "بيئي": "ESG", "حوكمة": "ESG",
    "جيوسياسي": "Geopolitical", "سياسي": "Geopolitical",
    "أخرى": "Other", "اخرى": "Other",
}

_SEVERITY_MAP = {
    "low": "Low", "medium": "Medium", "med": "Medium",
    "moderate": "Medium", "high": "High", "critical": "Critical", "severe": "Critical",
    "منخفض": "Low", "منخفضة": "Low",
    "متوسط": "Medium", "متوسطة": "Medium",
    "عالي": "High", "عالية": "High", "مرتفع": "High", "مرتفعة": "High",
    "حرج": "Critical", "حرجة": "Critical", "خطير": "Critical",
}

_STATUS_MAP = {
    "active": "Active", "monitoring": "Monitoring", "monitor": "Monitoring",
    "watch": "Monitoring", "realized": "Realized", "realised": "Realized",
    "mitigated": "Mitigated", "closed": "Closed", "resolved": "Closed",
    "نشط": "Active", "نشطة": "Active", "فعّال": "Active", "فعال": "Active",
    "مراقبة": "Monitoring", "متابعة": "Monitoring", "قيد المراقبة": "Monitoring",
    "تحقق": "Realized", "متحقق": "Realized",
    "مخفف": "Mitigated", "مخففة": "Mitigated", "معالج": "Mitigated",
    "مغلق": "Closed", "مغلقة": "Closed", "منتهي": "Closed",
}

_KIND_MAP = {
    "risk": "Risk", "threat": "Risk",
    "opportunity": "Opportunity", "opp": "Opportunity",
    "مخاطرة": "Risk", "خطر": "Risk", "تهديد": "Risk",
    "فرصة": "Opportunity",
}


def _map_value(val: str, mapping: dict[str, str], default: str) -> str:
    if not val:
        return default
    v = val.strip().lower().rstrip(":.,،;؛")
    if v in mapping:
        return mapping[v]
    for k, mapped in mapping.items():
        if k in v:
            return mapped
    return default


# Column-header aliases for table-based risk matrices.
_COL_ALIASES: dict[str, list[str]] = {
    "name":           ["name", "risk", "risk name", "opportunity", "item",
                       "المخاطرة", "الخطر", "العامل", "البند", "الاسم"],
    "category":       ["category", "type", "التصنيف", "النوع", "الفئة"],
    "kind":           ["kind", "risk/opp", "risk or opportunity",
                       "النوع", "خطر / فرصة"],
    "severity":       ["severity", "impact level", "الشدة", "الخطورة", "مستوى التأثير"],
    "current_status": ["status", "current status", "state",
                       "الحالة", "الحالة الحالية", "الوضع"],
    "expected_impact":["impact", "expected impact", "consequence",
                       "الأثر", "الأثر المتوقع", "التأثير"],
    "early_warning_indicators": [
        "early warning", "early warning indicator",
        "early warning indicators", "leading indicator", "warning",
        "مؤشر الإنذار المبكر", "مؤشرات الإنذار المبكر",
        "إنذار مبكر", "مؤشر الإنذار",
    ],
    "required_action":["action", "required action", "response", "mitigation",
                       "الإجراء المطلوب", "الإجراء", "الاستجابة"],
    "possible_hedge": ["hedge", "possible hedge", "hedging",
                       "التحوط الممكن", "التحوط", "خيار التحوط"],
}


def _col_key(header: str) -> str | None:
    h = re.sub(r"\s+", " ", header.strip().lower()).rstrip(":.")
    for canonical, aliases in _COL_ALIASES.items():
        for a in aliases:
            if h == a.lower() or h.startswith(a.lower()):
                return canonical
    return None


def _split_pipe_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"): s = s[1:]
    if s.endswith("|"):   s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_table_row(line: str) -> bool:
    return "|" in line and line.count("|") >= 3


def _is_table_separator(line: str) -> bool:
    # Markdown header separator like "|---|---|"
    return bool(re.match(r"^\s*\|?[\s|:\-]+\|[\s|:\-]+\|?\s*$", line))


def _parse_risk_matrix_from_table(body: str) -> list[dict]:
    """Find any pipe-delimited table whose header row maps to known
    risk-matrix columns and return list of row dicts."""
    if not body:
        return []
    lines = [ln for ln in body.splitlines() if ln.strip()]
    out: list[dict] = []
    i = 0
    while i < len(lines):
        if not _is_table_row(lines[i]):
            i += 1
            continue
        header_cells = _split_pipe_row(lines[i])
        col_map: dict[int, str] = {}
        for idx, h in enumerate(header_cells):
            key = _col_key(h)
            if key:
                col_map[idx] = key
        # Need at least the "name" column to be useful
        if "name" not in col_map.values():
            i += 1
            continue
        j = i + 1
        if j < len(lines) and _is_table_separator(lines[j]):
            j += 1
        while j < len(lines) and _is_table_row(lines[j]):
            cells = _split_pipe_row(lines[j])
            row: dict = {}
            for idx, val in enumerate(cells):
                key = col_map.get(idx)
                if not key or not val:
                    continue
                if key == "early_warning_indicators":
                    items = [
                        p.strip(" -•·–—") for p in re.split(r"[•·\n;؛]| - | / ", val)
                        if p.strip(" -•·–—")
                    ]
                    row[key] = items
                else:
                    row[key] = val
            if row.get("name"):
                out.append(row)
            j += 1
        i = j
    return out


# Within-block label patterns for "labeled" risk blocks
_RISK_BLOCK_LABELS: list[tuple[str, str]] = [
    ("name",           r"(?:name|risk|opportunity|item|المخاطرة|الخطر|العامل|الاسم|البند)"),
    ("category",       r"(?:category|type|التصنيف|النوع|الفئة)"),
    ("kind",           r"(?:kind|risk/opp|خطر\s*/\s*فرصة)"),
    ("severity",       r"(?:severity|impact level|الشدة|الخطورة|مستوى التأثير)"),
    ("current_status", r"(?:status|current status|الحالة|الحالة الحالية|الوضع)"),
    ("expected_impact",r"(?:expected impact|impact|الأثر المتوقع|الأثر|التأثير)"),
    ("early_warning_indicators",
        r"(?:early warning(?: indicators?)?|leading indicators?|"
        r"مؤشرات? الإنذار(?:\s*المبكر)?|إنذار مبكر)"),
    ("required_action",r"(?:required action|action|response|mitigation|الإجراء المطلوب|الإجراء|الاستجابة)"),
    ("possible_hedge", r"(?:possible hedge|hedge|hedging|التحوط الممكن|التحوط|خيار التحوط)"),
]


def _parse_risk_matrix_from_blocks(body: str) -> list[dict]:
    """Parse risk rows when the section uses labeled lines, e.g.:
        Risk: Customer concentration
        Category: Competitive
        Severity: High
        ...
    Multiple blocks may be separated by blank lines OR by a fresh `Risk:`/
    `name:` line. Returns rows that have at least a `name`.
    """
    if not body:
        return []
    # Build per-field regex once
    field_res = [(key, re.compile(rf"^\s*{pat}\s*[:：\-—–]\s*(.+)$", re.IGNORECASE))
                 for key, pat in _RISK_BLOCK_LABELS]

    rows: list[dict] = []
    current: dict = {}

    def commit():
        nonlocal current
        if current.get("name"):
            rows.append(current)
        current = {}

    for raw in body.splitlines():
        line = _strip_bullet(raw)
        if not line.strip():
            # Blank line ends current block
            if current.get("name"):
                commit()
            continue
        if _is_table_row(raw):
            continue  # tables handled separately
        matched = False
        for key, regex in field_res:
            m = regex.match(line)
            if m:
                val = m.group(1).strip()
                # A new `name` starts a new block
                if key == "name" and current.get("name"):
                    commit()
                if key == "early_warning_indicators":
                    items = [
                        p.strip(" -•·–—") for p in re.split(r"[•·;؛]| - | / ", val)
                        if p.strip(" -•·–—")
                    ]
                    current[key] = items
                else:
                    current[key] = val
                matched = True
                break
        if not matched and current.get("name"):
            # Continuation line — append to most recent narrative field
            for prefer in ("expected_impact", "required_action",
                           "possible_hedge", "name"):
                if prefer in current and isinstance(current[prefer], str):
                    current[prefer] = (current[prefer] + " " + line).strip()
                    break
    commit()
    return rows


def _coerce_risk_row(raw: dict) -> dict:
    """Map a raw row (English or Arabic values) into the CoreThesis
    RiskMatrixItem schema."""
    name = (raw.get("name") or "").strip(" -•·")
    if not name:
        return {}
    category = _map_value(raw.get("category", ""), _CATEGORY_MAP, "Other")
    kind_raw = raw.get("kind", "")
    # Infer kind from the name if not explicit (e.g. "Opportunity: ...")
    if not kind_raw:
        n_low = name.lower()
        if any(t in n_low for t in ("opportunity", "فرصة")):
            kind_raw = "Opportunity"
        else:
            kind_raw = "Risk"
    kind = _map_value(kind_raw, _KIND_MAP, "Risk")
    severity = _map_value(raw.get("severity", ""), _SEVERITY_MAP, "Medium")
    status   = _map_value(raw.get("current_status", ""), _STATUS_MAP, "Monitoring")
    ewi      = raw.get("early_warning_indicators") or []
    if isinstance(ewi, str):
        ewi = [ewi]
    ewi = [str(x).strip() for x in ewi if str(x).strip()]
    return {
        "name":                     name,
        "category":                 category,
        "kind":                     kind,
        "severity":                 severity,
        "current_status":           status,
        "expected_impact":          (raw.get("expected_impact") or "").strip(),
        "early_warning_indicators": ewi,
        "required_action":          (raw.get("required_action") or "").strip(),
        "possible_hedge":           (raw.get("possible_hedge") or "").strip(),
    }


# ── Per-scenario sub-field parsing ───────────────────────────────────────────

_SCN_SUB_LABELS = {
    "description": [
        "description", "narrative", "summary", "case",
        "الوصف", "السرد", "الملخص",
    ],
    "probability": [
        "probability", "prob", "likelihood",
        "الاحتمال", "الاحتمالية", "احتمالية",
    ],
    "valuation_target": [
        "target", "valuation target", "price target", "target price",
        "fair value", "intrinsic value",
        "الهدف السعري", "السعر المستهدف", "القيمة العادلة", "الهدف",
    ],
    "key_assumptions": [
        "key assumptions", "assumptions", "drivers", "key drivers",
        "الافتراضات الرئيسية", "الافتراضات", "المحركات",
    ],
}


def _parse_scenario(body: str, fallback_target: str = "") -> dict:
    """Extract description / probability / valuation_target / key_assumptions
    from one scenario block. Sub-fields may be labeled or implicit."""
    if not body:
        return {"description": "", "probability": 0,
                "valuation_target": "", "key_assumptions": []}

    text = _norm_digits(body)
    sub: dict = {}

    # Build per-sub-field regex (line-anchored "Label: value")
    for key, labels in _SCN_SUB_LABELS.items():
        pat = "|".join(re.escape(l) for l in sorted(labels, key=len, reverse=True))
        m = re.search(
            rf"(?im)^\s*(?:{pat})\s*[:：\-—–]\s*(.+?)\s*$",
            text,
        )
        if m:
            sub[key] = m.group(1).strip()

    # Probability: pull first integer 0-100
    prob = 0.0
    pm_text = sub.get("probability") or ""
    pm = re.search(r"(\d{1,3})\s*%?", pm_text)
    if not pm:
        pm = re.search(
            r"(?:probability|likelihood|prob|الاحتمال|احتمالية)"
            r"[^0-9]{0,15}(\d{1,3})\s*%?",
            text, re.IGNORECASE,
        )
    if pm:
        try:
            prob = max(0.0, min(100.0, float(pm.group(1))))
        except ValueError:
            prob = 0.0

    # Target: explicit sub-field, then anywhere in body, then fallback
    target = _extract_first_price(sub.get("valuation_target", "")) \
          or _extract_first_price(text) \
          or fallback_target

    # Description: explicit field, else first non-label line
    description = sub.get("description", "").strip()
    if not description:
        for ln in text.splitlines():
            s = _strip_bullet(ln).strip()
            if not s: continue
            # Skip lines that look like sub-field labels
            is_label = any(
                re.match(rf"(?i)^\s*{re.escape(l)}\s*[:：\-—–]", s)
                for labels in _SCN_SUB_LABELS.values() for l in labels
            )
            if not is_label:
                description = s
                break

    # Key assumptions: explicit bullet list field, else any bullets in body
    assumptions: list[str] = []
    if sub.get("key_assumptions"):
        # If on the same line, it might be comma-separated; otherwise next lines
        assumptions = [a.strip() for a in re.split(r"[,;؛\n]+", sub["key_assumptions"])
                       if a.strip()]
    if not assumptions:
        for ln in text.splitlines():
            if _BULLET_PREFIX_RE.match(ln):
                item = _strip_bullet(ln)
                if item and item != description:
                    assumptions.append(item)
    assumptions = assumptions[:6]

    return {
        "description":      description,
        "probability":      prob,
        "valuation_target": target,
        "key_assumptions":  assumptions,
    }


def _split_scenarios_from_parent(body: str) -> dict[str, str]:
    """Some docs put bull/base/bear under a single 'Scenarios' parent
    section. Split it into per-case sub-bodies."""
    out = {"bull_case": "", "base_case": "", "bear_case": ""}
    if not body:
        return out
    # Use the same label detector but only consider scenario keys
    current: str | None = None
    buf: list[str] = []

    def flush():
        if current and buf:
            out[current] = (out[current] + "\n" + "\n".join(buf)).strip()

    for raw in body.splitlines():
        hit = _detect_section_label(raw)
        if hit and hit[0] in ("bull_case", "base_case", "bear_case"):
            flush()
            current = hit[0]
            buf.clear()
            if hit[1]:
                buf.append(hit[1])
        elif current is not None:
            buf.append(raw)
    flush()
    return out


# ── Recommendation block ─────────────────────────────────────────────────────

def _extract_recommendation_block(sections: dict[str, str]) -> dict:
    """Parse the final recommendation, target price, entry zone, stop loss,
    and action plan from the relevant sections."""
    rec_body = sections.get("recommendation", "")
    rec_first = ""
    if rec_body:
        for ln in rec_body.splitlines():
            s = _strip_bullet(ln).strip()
            if s:
                rec_first = s
                break

    target = _extract_first_price(sections.get("target_price", "")) \
          or _extract_first_price(rec_body)
    entry  = sections.get("entry_zone", "").splitlines()[0].strip() \
        if sections.get("entry_zone") else ""
    stop   = sections.get("stop_loss", "").splitlines()[0].strip() \
        if sections.get("stop_loss") else ""
    action_plan = _split_bullets(sections.get("action_plan", ""))

    return {
        "final_recommendation": rec_first,
        "target_price":         target,
        "entry_zone":           entry,
        "stop_loss":            stop,
        "action_plan":          action_plan,
    }


# ── Main rule-based extractor ────────────────────────────────────────────────

def extract_thesis_rule_based(text: str) -> dict:
    """Offline / no-AI extractor (Demo Mode). Parses bilingual research notes
    into the same normalized dict shape as `extract_thesis_from_text`.
    Fields that aren't detected are left blank — no placeholder text.
    """
    raw_text = text or ""
    sections = _split_sections(raw_text)

    # Rationale (trim to ~3 sentences)
    rationale = sections.get("rationale", "").strip()
    if rationale:
        sent_split = re.split(r"(?<=[.!?。؟])\s+", rationale)
        rationale = " ".join(sent_split[:3]).strip()

    drivers       = _split_bullets(sections.get("drivers", ""))
    value_drivers = _split_bullets(sections.get("value_drivers", ""))
    catalysts     = _split_bullets(sections.get("catalysts", ""))
    risks         = _split_bullets(sections.get("risks", ""))
    mgmt_items    = _split_bullets(sections.get("mgmt_assumptions", ""))

    # Scenarios — accept either dedicated bull/base/bear sections, or one
    # parent "Scenarios" block that contains them.
    parent = _split_scenarios_from_parent(sections.get("scenarios", ""))
    bull_body = sections.get("bull_case", "") or parent["bull_case"]
    base_body = sections.get("base_case", "") or parent["base_case"]
    bear_body = sections.get("bear_case", "") or parent["bear_case"]
    global_target = _extract_first_price(sections.get("target_price", ""))
    bull = _parse_scenario(bull_body, global_target)
    base = _parse_scenario(base_body, global_target)
    bear = _parse_scenario(bear_body)

    # Recommendation block → consolidate into valuation_thesis + action items
    rec = _extract_recommendation_block(sections)

    # Risk/Return Matrix — try table parsing first (on the whole document so
    # tables that drift outside a labeled section still get picked up), then
    # fall back to labeled blocks inside the risk_matrix / risks sections.
    rm_section = sections.get("risk_matrix", "")
    risk_rows: list[dict] = []
    seen_names: set[str] = set()

    def _add_rows(rows: list[dict]) -> None:
        for r in rows:
            coerced = _coerce_risk_row(r)
            if not coerced:
                continue
            key = coerced["name"].lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            risk_rows.append(coerced)

    _add_rows(_parse_risk_matrix_from_table(rm_section))
    _add_rows(_parse_risk_matrix_from_table(raw_text))
    _add_rows(_parse_risk_matrix_from_blocks(rm_section))
    _add_rows(_parse_risk_matrix_from_blocks(sections.get("risks", "")))

    # Single-liners (only set if explicitly present)
    def _first_line(key: str) -> str:
        v = sections.get(key, "")
        return v.splitlines()[0].strip() if v else ""

    moat       = _first_line("moat")
    management = _first_line("management")
    margin     = _first_line("margin_profile")
    growth     = _first_line("growth_profile")
    valuation  = _first_line("valuation_thesis")

    # Compose the valuation_thesis line from the recommendation block when
    # the doc didn't include an explicit "Valuation" section.
    rec_bits: list[str] = []
    if rec["final_recommendation"]:
        rec_bits.append(f"Rec: {rec['final_recommendation']}")
    if rec["target_price"]:
        rec_bits.append(f"Target: {rec['target_price']}")
    elif global_target:
        rec_bits.append(f"Target: {global_target}")
    if rec["entry_zone"]:
        rec_bits.append(f"Entry: {rec['entry_zone']}")
    if rec["stop_loss"]:
        rec_bits.append(f"Stop: {rec['stop_loss']}")
    rec_line = " | ".join(rec_bits)
    if valuation and rec_line:
        valuation = f"{valuation} — {rec_line}"
    elif rec_line:
        valuation = rec_line

    # Action plan bullets land in management_execution_assumptions
    if rec["action_plan"]:
        mgmt_items = list(rec["action_plan"]) + [
            x for x in mgmt_items if x not in rec["action_plan"]
        ]

    raw = {
        "rationale":                        rationale,
        "thesis_drivers":                   drivers,
        "expected_value_drivers":           value_drivers,
        "expected_catalysts":               catalysts,
        "key_risks":                        risks,
        "management_execution_assumptions": mgmt_items,
        "expected_moat":                    moat,
        "expected_management":              management,
        "expected_margin_profile":          margin,
        "expected_growth_profile":          growth,
        "time_horizon":                     _coerce_horizon_from_text(raw_text),
        "valuation_thesis":                 valuation,
        "bull_case":                        bull,
        "base_case":                        base,
        "bear_case":                        bear,
        "risk_matrix":                      risk_rows,
    }
    return _normalize_extraction(raw)


def _normalize_extraction(data: dict) -> dict:
    """Coerce a raw LLM JSON response into a clean, validated dict."""
    if not isinstance(data, dict):
        data = {}

    risks_raw = data.get("risk_matrix") or []
    if not isinstance(risks_raw, list):
        risks_raw = []
    risks = [r for r in (_coerce_risk_dict(d) for d in risks_raw) if r is not None]

    return {
        "rationale":                        _coerce_str(data.get("rationale")),
        "thesis_drivers":                   _coerce_list(data.get("thesis_drivers")),
        "expected_value_drivers":           _coerce_list(data.get("expected_value_drivers")),
        "expected_catalysts":               _coerce_list(data.get("expected_catalysts")),
        "key_risks":                        _coerce_list(data.get("key_risks")),
        "management_execution_assumptions": _coerce_list(data.get("management_execution_assumptions")),
        "expected_moat":                    _coerce_str(data.get("expected_moat")),
        "expected_management":              _coerce_str(data.get("expected_management")),
        "expected_margin_profile":          _coerce_str(data.get("expected_margin_profile")),
        "expected_growth_profile":          _coerce_str(data.get("expected_growth_profile")),
        "time_horizon":                     _coerce_horizon(data.get("time_horizon")),
        "valuation_thesis":                 _coerce_str(data.get("valuation_thesis")),
        "bull_case":                        _coerce_scenario_dict(data.get("bull_case")),
        "base_case":                        _coerce_scenario_dict(data.get("base_case")),
        "bear_case":                        _coerce_scenario_dict(data.get("bear_case")),
        "risk_matrix":                      risks,
    }


# ── Convert extracted dict → preview CoreThesis (not persisted) ──────────────

def normalize_scenario_probabilities(
    bull: float, base: float, bear: float,
) -> tuple[float, float, float]:
    """Rescale bull/base/bear to sum to 100. Falls back to 25/55/20 if all
    zero. Each value clamped 0-100 first."""
    b = max(0.0, min(100.0, float(bull or 0)))
    m = max(0.0, min(100.0, float(base or 0)))
    r = max(0.0, min(100.0, float(bear or 0)))
    total = b + m + r
    if total <= 0:
        return 25.0, 55.0, 20.0
    if abs(total - 100.0) < 0.5:
        return b, m, r
    scale = 100.0 / total
    return round(b * scale, 1), round(m * scale, 1), round(r * scale, 1)


def build_preview_thesis(
    ticker:       str,
    company_name: str,
    extracted:    dict,
    *,
    filename:     str,
    source_kind:  str,
) -> CoreThesis:
    """Return a *non-persisted* CoreThesis instance representing the import.

    Scenario probabilities default to a sensible split (25/55/20) when the
    document didn't supply any — caller can edit before saving.
    """
    b = dict(extracted.get("bull_case") or {})
    m = dict(extracted.get("base_case") or {})
    r = dict(extracted.get("bear_case") or {})

    # Normalize probabilities: rescale to sum=100 (or default if all zero)
    b["probability"], m["probability"], r["probability"] = (
        normalize_scenario_probabilities(
            b.get("probability", 0),
            m.get("probability", 0),
            r.get("probability", 0),
        )
    )

    scn_bull = ScenarioCase(
        description=b.get("description", ""),
        probability=float(b.get("probability", 0)),
        valuation_target=b.get("valuation_target", ""),
        key_assumptions=list(b.get("key_assumptions") or []),
    )
    scn_base = ScenarioCase(
        description=m.get("description", ""),
        probability=float(m.get("probability", 0)),
        valuation_target=m.get("valuation_target", ""),
        key_assumptions=list(m.get("key_assumptions") or []),
    )
    scn_bear = ScenarioCase(
        description=r.get("description", ""),
        probability=float(r.get("probability", 0)),
        valuation_target=r.get("valuation_target", ""),
        key_assumptions=list(r.get("key_assumptions") or []),
    )

    risk_items = [RiskMatrixItem(**r) for r in (extracted.get("risk_matrix") or [])]

    return CoreThesis(
        ticker=ticker.upper(),
        company_name=company_name,
        rationale=extracted.get("rationale", ""),
        thesis_drivers=list(extracted.get("thesis_drivers") or []),
        expected_value_drivers=list(extracted.get("expected_value_drivers") or []),
        expected_catalysts=list(extracted.get("expected_catalysts") or []),
        key_risks=list(extracted.get("key_risks") or []),
        management_execution_assumptions=list(
            extracted.get("management_execution_assumptions") or []
        ),
        expected_moat=extracted.get("expected_moat", ""),
        expected_management=extracted.get("expected_management", ""),
        expected_margin_profile=extracted.get("expected_margin_profile", ""),
        expected_growth_profile=extracted.get("expected_growth_profile", ""),
        time_horizon=extracted.get("time_horizon", "1-3 years"),
        valuation_thesis=extracted.get("valuation_thesis", ""),
        scenario_bull=scn_bull,
        scenario_base=scn_base,
        scenario_bear=scn_bear,
        risk_matrix=risk_items,
        source_type="Imported",
        imported_from=filename,
        imported_at=datetime.now().isoformat(timespec="seconds"),
        import_source_kind=source_kind,
    )


def preview_summary(preview: CoreThesis) -> dict:
    """Compact summary for the UI preview card."""
    return {
        "rationale_present":     bool(preview.rationale),
        "drivers_count":         len(preview.thesis_drivers),
        "value_drivers_count":   len(preview.expected_value_drivers),
        "catalysts_count":       len(preview.expected_catalysts),
        "risks_count":           len(preview.key_risks),
        "mgmt_assumptions_count": len(preview.management_execution_assumptions),
        "risk_matrix_count":     len(preview.risk_matrix),
        "bull_prob":             preview.scenario_bull.probability,
        "base_prob":             preview.scenario_base.probability,
        "bear_prob":             preview.scenario_bear.probability,
        "moat_present":          bool(preview.expected_moat),
        "valuation_present":     bool(preview.valuation_thesis),
    }
