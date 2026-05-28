"""
ai/analyzer.py
--------------
Stub for AI-powered filing analysis.

This module is intentionally minimal — it defines the interface that the
Streamlit UI already calls, so you only need to fill in the implementation
when you are ready to add OpenAI (or another LLM).

HOW TO CONNECT OPENAI
---------------------
1. pip install openai
2. Add OPENAI_API_KEY to Replit Secrets
3. Replace the stub below with something like:

    from openai import OpenAI
    import os

    _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def analyze_filing(filing_url: str, form_type: str, company_name: str) -> str:
        prompt = (
            f"You are a financial analyst. Summarize the key takeaways from "
            f"this SEC {form_type} filing for {company_name}. "
            f"Focus on revenue, risks, and outlook. Filing: {filing_url}"
        )
        response = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
"""

from edgar.filings import Filing


def analyze_filing(filing: Filing, company_name: str) -> str:
    """
    Analyze a filing and return a summary string.

    Currently returns a placeholder message.
    Replace this function body with real OpenAI calls when ready.
    """
    return (
        f"AI analysis is not yet enabled.\n\n"
        f"To activate it, open **edgar_app/ai/analyzer.py** and follow "
        f"the instructions at the top of the file."
    )
