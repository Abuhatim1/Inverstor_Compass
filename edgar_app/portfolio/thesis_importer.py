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
    """Read DOCX without python-docx — DOCX is a zip of XML."""
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

    paragraphs: list[str] = []
    for para in root.iter(f"{ns}p"):
        texts = [t.text or "" for t in para.iter(f"{ns}t")]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


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
        raise ImportError_(f"AI extraction failed: {e}") from e

    return _normalize_extraction(data)


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
