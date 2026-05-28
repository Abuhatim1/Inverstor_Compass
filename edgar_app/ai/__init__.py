"""
ai/__init__.py
--------------
AI analysis module — uses OpenAI to analyze SEC filings.
Set OPENAI_API_KEY in Replit Secrets to enable.
"""

from .analyzer import OPENAI_AVAILABLE, AnalysisResult, analyze_filing
from .fetcher import FetchError, fetch_filing_text

__all__ = [
    "OPENAI_AVAILABLE",
    "AnalysisResult",
    "analyze_filing",
    "FetchError",
    "fetch_filing_text",
]
