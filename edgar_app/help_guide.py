"""
Bousala — Help & User Guide
Beginner-friendly reference covering every feature of the app.
No accounting or finance background assumed.
"""
from __future__ import annotations
import streamlit as st


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _section(icon: str, title: str, content_fn, expanded: bool = False) -> None:
    with st.expander(f"{icon}  {title}", expanded=expanded):
        content_fn()


def _tip(text: str) -> None:
    st.info(text, icon="💡")


def _warn(text: str) -> None:
    st.warning(text, icon="⚠️")


def _note(text: str) -> None:
    st.info(text, icon="ℹ️")


# ══════════════════════════════════════════════════════════════════════════════
# Section content functions
# ══════════════════════════════════════════════════════════════════════════════

def _s_welcome() -> None:
    st.markdown("""
**بوصلة** *(Bousala, "compass" in Arabic)* is a personal investment tracker
and research tool built for individual investors — especially in Saudi Arabia
and the Gulf region.

You do **not** need any accounting or finance knowledge to use it.
This guide explains every feature from scratch.

---

### What can Bousala do?

| Feature | What it means for you |
|---|---|
| 💼 Track your portfolio | See all your stocks and investments in one place |
| 💵 Cash accounts | Track money sitting in your brokerage accounts |
| 📈 Performance | Understand how much your portfolio has grown |
| 📊 Allocation | See which sectors or assets you're over/under-invested in |
| 🕌 Zakat | Estimate how much Zakat is due on your investments |
| 📄 Tax report | Summary of profits and losses from positions you've closed |
| 📑 Wealth statement PDF | A printable document showing your full net worth |
| 🔍 Research | Read the official financial filings of any US-listed company |
| 🤖 AI analysis | Get plain-English explanations of complex financial reports |

---

### Quick-start checklist

1. **Create an account** → go to **💳 Accounts** tab → *New Account*
2. **Add a position** → go to **💼 Portfolio** tab → *Add New Position*
3. **Refresh prices** → tap **Refresh Prices** button in the sidebar
4. **View your dashboard** → go to **🧭 Analysis** → *Command Center*
5. **Generate a PDF** → tap **Download Wealth Statement PDF** in the sidebar
""")


def _s_glossary() -> None:
    st.markdown("""
This app uses words from finance and investing. Here's what every term means
in plain English.

---

#### 💰 Money terms

| Term | Plain-English meaning |
|---|---|
| **Portfolio** | The whole collection of investments you own |
| **Holding** | One investment you currently own (e.g. "I hold 10 shares of ARAMCO") |
| **Position** | Same as holding — one slot in your portfolio |
| **Asset** | Anything you own that has value: stocks, crypto, real estate, etc. |
| **Ticker / Symbol** | A short code for a company on the stock market (e.g. `2222` for Saudi Aramco, `AAPL` for Apple) |
| **Quantity (Qty)** | How many units/shares you own |
| **Base Currency** | The single currency you want everything converted to for comparison (default: **SAR**). Like choosing SAR as your "measuring stick". |
| **Market Value (MV)** | What your holding is worth *today* at current prices |
| **Cost Basis** | What you *originally paid* for your holding, in total |
| **Avg Cost** | Average price per share you paid across all your purchases |
| **P&L** | *Profit and Loss* — the difference between what you paid and what it's worth now |
| **Unrealized P&L** | Profit/loss on a position you still *own* (not yet sold — it's "on paper") |
| **Realized P&L** | Profit/loss you actually *locked in* by selling a position |
| **Weight (Wt %)** | What percentage of your total portfolio this one holding represents |

---

#### 📈 Performance terms

| Term | Plain-English meaning |
|---|---|
| **Return** | How much your investment grew, as a percentage |
| **Total Return** | (Current value − what you put in) ÷ what you put in, as a % |
| **Net Contributions** | The total cash you personally deposited into your portfolio (deposits minus withdrawals) |
| **Growth** | Current portfolio value minus your net contributions — the "profit" portion |
| **XIRR** | *Extended Internal Rate of Return* — an annualized return that accounts for *when* you added or withdrew money. Think of it as "what interest rate would a bank need to give you to match your results?" It is labeled **approximate** because historical currency conversions use today's exchange rate. |
| **Annualized return** | How much you earned per year on average, so you can compare investments that ran for different lengths of time |

---

#### 💳 Account terms

| Term | Plain-English meaning |
|---|---|
| **Account** | A brokerage or crypto account that holds your investments and cash |
| **Cash Balance** | How much cash (uninvested money) is sitting in an account |
| **Cash Ledger** | A running history of every deposit, withdrawal, and fee in an account — like a bank statement |
| **Opening Balance** | The starting cash amount when you created the account in Bousala |
| **INITIAL_BALANCE** | The first cash entry when you open an account |
| **DEPOSIT** | Cash you put *in* to an account |
| **WITHDRAWAL** | Cash you take *out* of an account |
| **FEE** | Brokerage commission, transaction fee, or Zakat paid |
| **DIVIDEND** | Cash income paid by a company to its shareholders |

---

#### 📊 Allocation terms

| Term | Plain-English meaning |
|---|---|
| **Allocation** | How your money is spread across different categories |
| **Sector** | The industry a company belongs to (e.g. Technology, Energy, Healthcare) |
| **Asset Type** | The *kind* of investment: Stock, Bond, ETF, Crypto, Real Estate, etc. |
| **Geographic region** | Where the company is based (Saudi Arabia, USA, Europe, etc.) |
| **Concentration** | Having too much of your money in one thing — considered a risk |
| **Diversification** | Spreading money across many investments to reduce risk |

---

#### 🕌 Zakat terms

| Term | Plain-English meaning |
|---|---|
| **Zakat** | Islamic obligatory annual charity on eligible wealth |
| **Zakatable base** | The total amount that Zakat is calculated on (portfolio value + cash) |
| **Lunar rate (2.5%)** | The standard Zakat rate based on the Islamic (Hijri) calendar year |
| **Gregorian rate (2.5775%)** | Slightly higher rate used when calculating Zakat on a solar calendar year |
| **Nisab** | The minimum threshold of wealth above which Zakat becomes obligatory |

---

#### 🔍 Research terms

| Term | Plain-English meaning |
|---|---|
| **SEC** | *Securities and Exchange Commission* — the US government body that requires publicly listed companies to publish their financial reports |
| **EDGAR** | The SEC's free public database of all company filings |
| **10-K** | A company's annual report — a deep summary of the whole year |
| **10-Q** | A company's quarterly (every 3 months) financial update |
| **8-K** | A company's announcement of important news (merger, CEO change, etc.) |
| **CIK** | A unique ID number the SEC assigns to every listed company |
| **SAHMK** | The Saudi stock exchange (Tadawul) ticker prefix for Saudi-listed companies |
| **Filing** | An official document a company submits to the SEC |

---

#### ⚙️ Other terms

| Term | Plain-English meaning |
|---|---|
| **FX / Forex** | *Foreign Exchange* — converting money from one currency to another |
| **FX Rate** | The exchange rate between two currencies at a given moment |
| **Pegged currency** | A currency whose exchange rate is fixed to another (e.g. SAR, AED, QAR are pegged to USD, so the rate never changes) |
| **ETF** | *Exchange-Traded Fund* — a basket of many stocks packaged as one tradeable unit |
| **Lot** | One purchase event of shares. If you buy 10 shares today and 5 next month, you have 2 lots |
| **Closed lot** | Shares you have sold — the trade is complete |
| **Voided** | A transaction that was entered in error and manually cancelled |
| **FIFO** | *First In, First Out* — when you sell shares, the shares you bought *earliest* are counted as sold first (this is the standard accounting method used here) |
""")


def _s_layout() -> None:
    st.markdown("""
### The Sidebar (left panel)

The sidebar is always visible on the left side of the screen.

| Sidebar item | What it does |
|---|---|
| **📄 Family Wealth Statement** | Type an optional personal note, then click to download a professional PDF showing your entire net worth |
| **📡 Market Price Refresh** | Shows whether the stock market is currently open, and lets you auto-refresh prices at regular intervals |
| **⚙️ Settings** | Toggle Demo Mode, see your AI API key status, enable Developer Mode |

---

### Main Tabs (top of the screen)

The main area is divided into **8 tabs**. Click any tab name to switch to it.

| Tab | What's inside |
|---|---|
| **🏦 Balance Sheet** | Your complete financial picture: assets, liabilities, and net worth all in one view |
| **💼 Portfolio** | Your current investments — holdings, allocation charts, and sold positions |
| **🏦 Alt Investments** | Investments outside the stock market: real estate, private equity, collectibles, etc. |
| **💳 Accounts** | Brokerage and crypto accounts + cash balances |
| **📜 Activity** | History of every transaction and a cashflow summary |
| **🧭 Analysis** | AI command center, performance metrics, portfolio risk, decision queue, and more |
| **🔍 Research** | Search SEC EDGAR filings for any US company, discover Saudi stocks |
| **🧪 Test Runner** | *Developer use only* — runs automated quality checks on the app |

---

### Sub-pages (pills inside each tab)

Some tabs have sub-pages shown as clickable pills just below the tab name.
For example, inside **💼 Portfolio** you'll see:

> **💼 Holdings** · **📊 Allocation** · **📁 Closed Holdings**

Click any pill to switch between sub-pages within that tab.

---

### The header bar

At the top of the main content area you'll see key metrics:
- **Total portfolio value** in your base currency
- **Cash balance** across all accounts
- **Unrealized P&L** — the total profit/loss on positions you still hold
- **FX indicator** — a small warning appears if any exchange rates are estimates rather than live data
- **Base currency selector** — change the currency everything is measured in (default: SAR)
""")


def _s_balance_sheet() -> None:
    st.markdown("""
**Tab: 🏦 Balance Sheet**

This is your complete financial snapshot — similar to what a bank or accountant
would prepare for you, but automatically calculated.

### What it shows

| Section | Meaning |
|---|---|
| **Assets** | Everything you own that has value (stocks, cash, property, etc.) |
| **Liabilities** | Debts you owe (loans, credit card balances, mortgages) |
| **Net Worth** | Assets minus Liabilities — the single most important number |

### How to read it

- Green numbers = assets (things you own)
- Red numbers = liabilities (things you owe)
- **Net Worth** at the bottom is your true financial position

### Fixed Assets sub-section

This section shows non-investment assets like:
- 🏠 Real estate / property
- 🚗 Vehicles
- 💍 Jewelry or collectibles
- 📦 Other physical items of value

You can add these under **🏦 Alt Investments** tab.

---
""")
    _tip("Net Worth = Assets − Liabilities. If your net worth is positive, you own more than you owe.")


def _s_portfolio() -> None:
    st.markdown("""
**Tab: 💼 Portfolio** has three sub-pages:

---

## 💼 Holdings

This is the main list of every investment you currently hold.

### The view toggle

At the top of the holdings list you'll see two options:
- **📋 Table** — a spreadsheet-style grid, best on desktop
- **🃏 Cards** — stacked cards, easier to read on a phone

### What each column means (Table view)

| Column | Meaning |
|---|---|
| (status dot) | 🟢 you're in profit · 🔴 you're at a loss · ⚪ flat (no change) |
| **Company** | The company name |
| **Ticker** | The stock code (e.g. `AAPL`, `2222`) |
| **Qty** | How many shares/units you own |
| **Avg Cost** | The average price you paid per share across all your purchases |
| **Price** | Today's market price per share |
| **MV (SAR)** | Market Value — what your holding is worth *right now*, converted to your base currency |
| **P&L %** | Profit or loss as a percentage. +10% means you're up 10% from your purchase price |
| **Wt %** | What portion of your total portfolio this holding represents |
| **CCY** | The currency the stock trades in (e.g. USD, SAR) |
| **Src** | Where the price came from (Yahoo Finance, manual, etc.) |
| **Account** | Which of your accounts holds this investment |

### Action bar (below the table)

Four buttons let you act on your holdings:

| Button | What it does |
|---|---|
| **➕ Add New Position** | Enter a brand-new investment |
| **📈 Buy More** | Add shares to an existing holding |
| **📉 Sell / Close** | Record a sale — moves to Closed Holdings |
| **💰 Cash Settlement** | Record cash dividends or other cash movements |

### Refreshing prices

Click **🔄 Refresh Prices** to fetch the latest market price for all your holdings.
Prices are fetched from Yahoo Finance.

---

## 📊 Allocation

Shows how your money is spread across different categories, as pie and bar charts.

Use the **filters** at the top to view by:
- **Sector** (Technology, Energy, Healthcare…)
- **Asset Type** (Stock, ETF, Crypto…)
- **Geography** (Saudi Arabia, USA, Europe…)
- **Account** (which brokerage)

### Why this matters

If 90% of your portfolio is in one company or one sector, you have high
*concentration risk* — if that one thing drops, your entire portfolio suffers.
A healthy portfolio is usually diversified across multiple sectors and regions.

---

## 📁 Closed Holdings

All the investments you have *sold*. For each closed position you'll see:

| Column | Meaning |
|---|---|
| **Ticker** | The stock code |
| **Qty sold** | How many shares you sold |
| **Proceeds** | The total cash you received from the sale |
| **Cost** | What you originally paid |
| **Realized P&L** | The actual profit or loss you locked in |
| **Close date** | When you sold |

This list is the foundation for your **Tax Report** under Analysis.
""")


def _s_accounts() -> None:
    st.markdown("""
**Tab: 💳 Accounts** has two sub-pages:

---

## 💳 Accounts

An *account* in Bousala is a brokerage or crypto account where your investments live.
Examples: "Al Rajhi Brokerage", "Binance", "Interactive Brokers".

### Creating an account

1. Go to **💳 Accounts** tab
2. Click **New Account**
3. Fill in:
   - **Account name** — any label you like (e.g. "Tadawul Brokerage")
   - **Institution** — the bank or broker (e.g. "Al Rajhi Capital")
   - **Account type** — Brokerage, Crypto, or Other
   - **Base currency** — the default currency of this account (e.g. SAR, USD)
   - **Opening cash** — how much cash was already in this account when you set it up in Bousala. *This creates an INITIAL_BALANCE entry in your cash ledger automatically.*
4. Click **Create Account**

> 💡 You can also create an account *while* adding a new position — there's an inline
> "➕ Create a new account" expander inside the Add Position dialog.

### Editing an account

Use the **✏️ Edit Account** expander at the bottom of the Accounts page to update
an existing account's details.

---

## 💵 Cash Ledger

The cash ledger is a complete history of every cash movement in each account —
like a bank statement for your investment accounts.

### Entry types

| Type | Meaning |
|---|---|
| **INITIAL_BALANCE** | The opening cash balance when you created the account |
| **DEPOSIT** | Cash you transferred *into* the account |
| **WITHDRAWAL** | Cash you took *out* of the account |
| **BUY** | Cash used to purchase shares (reduces cash balance) |
| **SELL** | Cash received from selling shares (increases cash balance) |
| **DIVIDEND** | Dividend cash credited to the account |
| **FEE** | Brokerage commission, Zakat, or other fee (reduces cash balance) |
| **FX_CONVERSION** | Currency exchange between accounts |

### Why the cash ledger matters

The cash ledger is the **single source of truth** for all cash in Bousala.
Every cash balance, performance calculation, and Zakat estimate reads from it.
If a cash number looks wrong, check the ledger for missing or duplicate entries.

---
""")
    _tip("Always record your opening cash balance when creating an account — this ensures your performance and Zakat calculations are correct from day one.")


def _s_activity() -> None:
    st.markdown("""
**Tab: 📜 Activity** has two sub-pages:

---

## 📜 Transaction History

A complete list of every trade, dividend, and fee you've recorded.

### Transaction types

| Type | What it means |
|---|---|
| **BUY** | You purchased shares |
| **SELL** | You sold shares |
| **DIVIDEND** | A dividend payment was received |
| **FEE** | A fee was charged (commission, Zakat, management fee) |
| **TRANSFER_IN** | Shares transferred *into* this account from another account |
| **TRANSFER_OUT** | Shares transferred *out* of this account |
| **FX_CONVERSION** | Currency was exchanged |
| **CORPORATE_ACTION** | Stock split, merger, rights issue, etc. |

### Columns explained

| Column | Meaning |
|---|---|
| **Date** | When the transaction happened |
| **Ticker** | Which investment it relates to |
| **Type** | BUY, SELL, DIVIDEND, etc. (see above) |
| **Qty** | Number of shares/units |
| **Price** | Price per share at the time |
| **Amount** | Total cash value of the transaction |
| **CCY** | Currency of the transaction |
| **Account** | Which account this happened in |
| **Notes** | Any extra notes you added |

---

## 💹 Cashflow

A visual summary of your cash inflows and outflows over time — deposits,
dividends received, withdrawals, and fees paid.

Useful for understanding whether your portfolio is generating income
(dividends, distributions) or requiring ongoing cash injections.

---
""")
    _note("Transactions are the most important data in Bousala. Everything — performance, Zakat, tax reports — is calculated from your transaction history.")


def _s_analysis() -> None:
    st.markdown("""
**Tab: 🧭 Analysis** has six sub-pages:

---

## 🧭 Command Center

Your AI-powered investment dashboard. It summarizes your current portfolio
situation and flags anything worth your attention.

Use the **Analyze** button to get an AI-generated plain-English assessment
of your portfolio's health, risks, and opportunities.

> *Requires an OpenAI API key. If you don't have one, enable **Demo Mode** in
> the sidebar to see sample output.*

---

## 📈 Performance

Shows how well your portfolio has done over time.

| Metric | What it means |
|---|---|
| **Current Value** | What your portfolio is worth today |
| **Net Contributions** | Total cash you personally put in (deposits minus withdrawals) |
| **Growth** | Current value minus what you put in — your "profit" in base currency |
| **Total Return %** | Growth as a percentage of what you put in |
| **XIRR** | Annualized return accounting for the timing of your deposits/withdrawals *(labeled approximate — see glossary)* |
| **Dividends received** | Total dividends lifetime, this year, and last 12 months |
| **Yield on cost** | Dividends ÷ what you originally paid — how much income your original investment generates |
| **Zakat estimate** | Estimated Zakat due on your current zakatable wealth |
| **Tax report** | Realized gains/losses from closed positions by year and month |
| **Reconciliation** | Checks whether your recorded holdings match your transaction history |

---

## 🛡️ Portfolio Risk

Analyzes the risk profile of your portfolio:

- **Concentration** — is too much in one holding or sector?
- **Volatility** — how much do your holdings typically fluctuate?
- **Geographic risk** — are you over-exposed to one country?
- **Currency risk** — do currency moves affect your portfolio?

---

## 🎯 Decision Queue

A personal watchlist where you note investments you're *watching* but haven't
bought yet, or positions you're *considering* selling. You can:

- Add a ticker with your target price and reasoning
- Mark items as *Actionable*, *Monitoring*, or *Done*
- Review and clear resolved items

---

## 📝 Thesis Memory

A place to write down *why* you own each investment —
your personal investment thesis. For example:
> "Holding ARAMCO because oil demand remains strong in 2025–2026 and the
> dividend yield exceeds 4%."

Writing down your reasoning helps you stay disciplined and not panic-sell
when prices dip temporarily.

---

## 🌍 Market Intel

Market data and economic indicators to provide context for your portfolio.
Useful for understanding the broader market environment before making decisions.

---
""")
    _tip("The Performance tab is most useful once you've been tracking your portfolio for at least a few months and have a history of deposits and transactions.")


def _s_research() -> None:
    st.markdown("""
**Tab: 🔍 Research** has four sub-pages:

---

## 📄 Filing Search (US companies via SEC EDGAR)

Search for any US-listed company by its ticker symbol and read its official
financial reports — for free, directly from the SEC.

### How to search

1. Type a US ticker into the search box (e.g. `AAPL`, `TSLA`, `MSFT`)
2. Press **Search**
3. Select the type of filing you want to read:
   - **10-K** — full annual report
   - **10-Q** — quarterly update
   - **8-K** — special announcement
   - **DEF 14A** — shareholder meeting proxy
4. Click any filing to read it, or click **Analyze with AI** for a plain-English summary

### What the AI analysis does

The AI reads the filing and tells you:
- What the company does
- Key financial highlights
- Major risks mentioned
- Changes from the previous period
- Important news announcements

---

## 🔍 SAHMK Discovery

Discover Saudi-listed companies (Tadawul exchange) from the SAHMK data feed.

- Browse all Saudi sectors and their component stocks
- View key metrics for each company
- Add interesting discoveries directly to your portfolio or Decision Queue

---

## 🔬 Research Watchlist

Companies you've flagged for further research. Lets you track firms you're
analyzing before you decide whether to invest.

---

## 📂 Upload Filing

If you have a filing document saved locally (PDF or text), you can upload it
here for AI analysis — useful for reports from Saudi exchanges or documents
not in EDGAR.

---
""")
    _note("SEC EDGAR data is free and public. Bousala fetches it live — no subscription required.")


def _s_add_position() -> None:
    st.markdown("""
This is the most common thing you'll do in Bousala — recording a new investment
you've purchased.

### Step-by-step

1. Go to the **💼 Portfolio** tab
2. Click **➕ Add New Position** in the action bar below the holdings table
3. A dialog box will appear. Fill in:

   **Step 1 — Identify the stock:**
   - **Ticker** — the stock code (e.g. `2222` for Aramco, `AAPL` for Apple)
   - Click **Validate** to auto-fill the company name and current price

   **Step 2 — Enter your position details:**
   - **Quantity** — how many shares you own
   - **Average cost per share** — what you paid on average (if you bought in
     multiple purchases, enter the weighted average)
   - **Currency** — the currency the stock trades in
   - **Asset type** — Stock, ETF, Crypto, Bond, etc.

   **Step 3 — Link to an account:**
   - Select which account holds this investment
   - If you haven't created an account yet, click **➕ Create a new account**
     right inside the dialog — no need to leave

4. Click **Save Position**

---

### Mode A vs Mode B

When adding a position you haven't previously tracked in Bousala (e.g. shares
you already owned before starting to use the app), you have two modes:

| Mode | When to use |
|---|---|
| **Mode A — Opening position** | You already own these shares and are recording them for the first time. Enter current quantity and average purchase price. No transaction history required. |
| **Mode B — From transactions** | You want to build a full transaction history (BUY orders) to support accurate performance and Zakat calculations. |

> 💡 **Recommendation for new users:** Start with Mode A for positions you
> already own. Use Mode B going forward for new purchases.

---

### What about existing holdings?

If you already own shares and are just adding them to Bousala for the first time,
use **Mode A**. Enter:
- Your total quantity
- Your average purchase price (cost per share across all your purchases)
- An approximate purchase date (used for XIRR calculations)

---
""")
    _tip("After saving, click 🔄 Refresh Prices to fetch the current market value of your new position.")


def _s_transactions() -> None:
    st.markdown("""
After your initial positions are set up, record every trade as a transaction
to keep your history accurate.

---

## Recording a BUY

1. In the **💼 Holdings** table, tap the row of the holding you want to add to
2. An action bar appears — click **📈 Buy More**
3. Enter: date, quantity purchased, price per share, total fees paid
4. Click **Save**

> The system updates your quantity and recalculates your average cost automatically.

---

## Recording a SELL

1. Tap the holding row in the Holdings table
2. Click **📉 Sell / Close**
3. Enter: date, quantity sold, price you received per share, fees
4. Click **Save**

> The sold shares move to **📁 Closed Holdings** with your realized P&L calculated.
> The FIFO method is used — the shares you bought *earliest* are counted as sold first.

---

## Recording a DIVIDEND

1. Click **💰 Cash Settlement** in the action bar
2. Select **Dividend** as the type
3. Enter the dividend amount and the date received
4. Click **Save**

> Dividends are recorded in your cash ledger and counted in the income section
> of the Performance tab.

---

## Recording a FEE

Fees (brokerage commissions, account maintenance fees) can be entered as
a **FEE** type cash entry from the **Cash Ledger** tab:

1. Go to **💳 Accounts** → **💵 Cash Ledger**
2. Click **Add Entry**
3. Select **FEE** type, enter the amount and date

---

## Recording DEPOSITS and WITHDRAWALS

Same as fees, but from the Cash Ledger tab, using **DEPOSIT** or **WITHDRAWAL** types.
Deposits are money you added to your brokerage account; withdrawals are money
you took out.

> ⚠️ **Always record deposits and withdrawals.** The XIRR performance calculation
> depends on this data. If you deposited SAR 50,000 in month 3 but don't record
> it, your performance will look much better than it actually is.

---
""")
    _warn("Recording deposits and withdrawals accurately is essential for correct performance (XIRR) calculations.")


def _s_zakat() -> None:
    st.markdown("""
The **Zakat Calculator** is inside **🧭 Analysis → 📈 Performance**.

---

### How Bousala calculates Zakat

**Zakatable base = Holdings Market Value + Cash Balance**

Zakat due = Zakatable base × Rate

You choose the rate:
- **Lunar (2.5%)** — based on the Islamic (Hijri) calendar — *default*
- **Gregorian (2.5775%)** — slightly higher, based on the solar calendar

---

### Zakat already paid

If you've paid Zakat previously (recorded as **FEE** transactions in your cash
ledger), Bousala shows you the total paid as *informational* — it is **not**
subtracted from the current base again. This is correct because:

- When you paid Zakat, it left your cash — your cash balance already reflects it
- Your current zakatable base is based on your current cash, which already excludes paid Zakat

---

### Important disclaimer

Bousala's Zakat estimate is a **starting point**, not a fatwa. Please consult
a qualified Islamic scholar or Zakat authority for your specific circumstances.

Factors that might affect your actual Zakat include:
- Nisab threshold (minimum qualifying wealth)
- Whether holdings have been held for a full lunar year (hawl)
- Treatment of dividends, loans, and liabilities
- Whether stocks are in trading companies or industrial companies

---

### What about liabilities?

If you owe short-term debts (credit card balance, current portion of a loan),
you may deduct them from your zakatable base. Record your liabilities in the
**🏦 Balance Sheet** tab and they will be factored in.

---
""")
    _note("Bousala labels its Zakat estimate as approximate — always verify with a scholar.")


def _s_tax() -> None:
    st.markdown("""
The **Tax Report** is inside **🧭 Analysis → 📈 Performance → Tax Report section**.

---

### What it shows

A summary of **realized gains and losses** — profit or loss from positions
you have already *sold* — grouped by:

- **Year** — useful for annual tax filing
- **Month** — useful for monitoring within a year

### Reading the report

| Column | Meaning |
|---|---|
| **Period** | The year or month |
| **Currency** | The currency the stock traded in |
| **Proceeds** | Total cash received from sales |
| **Cost** | What you originally paid for the shares sold |
| **Realized P&L** | Proceeds minus Cost — your actual profit or loss |
| **Fees** | Transaction costs related to the sale |
| **Lots** | Number of individual purchase batches sold |

### Two types of totals

1. **Native currency totals** (exact) — the exact numbers in the original currency
2. **Base currency total** (approximate) — the sum converted to your base currency at *today's* exchange rate

The base currency total is labeled **approximate** because Bousala does not
store historical exchange rates. The actual amount in your base currency at the
time of the sale may have been different.

---

### Tax advice

Bousala shows you the data, but does not provide tax advice.
Saudi residents are generally exempt from capital gains tax on personal
investments, but rules vary. Consult a tax professional in your jurisdiction.

---
""")
    _note("The native currency totals are exact. Use them as your primary reference. The base-currency total is approximate and for reference only.")


def _s_wealth_statement() -> None:
    st.markdown("""
The **Wealth Statement PDF** is generated from the sidebar.

---

### What it contains

A single, professionally formatted PDF with:
- Your total net worth (assets minus liabilities)
- Breakdown of each account with current balance
- Summary of portfolio holdings and their values
- Cash positions
- A personal note (optional — you can write things like bank names, contacts, and instructions for your family)

---

### How to generate it

1. In the sidebar, find the **📄 Family Wealth Statement** section
2. Optionally type a personal note (e.g. account access instructions for your family)
3. Click **📥 Download Wealth Statement PDF**
4. The PDF opens or downloads in your browser

---

### When to use it

- **Annual review** — keep a dated copy for your records
- **Estate planning** — give a copy to your spouse or trusted family member
- **Meeting a financial advisor** — share your current position clearly
- **Applying for a loan** — proof of assets

---
""")
    _tip("Click Download once per session. The PDF is generated on the fly from your current data — no data leaves your device.")


def _s_faq() -> None:
    st.markdown("""

**Q: Can I use Bousala without an OpenAI API key?**

Yes. Enable **Demo Mode** in the sidebar (⚙️ Settings). You'll see sample AI
analysis output and can use all non-AI features fully.

---

**Q: Where is my data stored?**

All your data (holdings, transactions, accounts) is stored in JSON files on
the server where Bousala is running — your Replit workspace. Nothing is sent
to external servers except: (1) market price requests to Yahoo Finance, and
(2) AI analysis text sent to OpenAI if you use that feature.

---

**Q: Why does it say "approximate" next to my XIRR or Zakat?**

Bousala does not store historical currency exchange rates. When it converts
past cash flows (e.g. a deposit made 2 years ago in USD) to your base currency,
it uses *today's* exchange rate. This introduces a small approximation, which
is why the label says "approximate". For SAR, AED, and QAR it's exact because
those currencies are pegged to the USD (fixed exchange rate).

---

**Q: What's the difference between "unrealized" and "realized" P&L?**

- **Unrealized** = profit/loss on shares you *still own*. It's "on paper" —
  it can go up or down tomorrow.
- **Realized** = profit/loss from shares you have *sold*. It's done — that
  amount is locked in.

---

**Q: I sold a position but it's not showing in Closed Holdings. Why?**

Make sure you recorded the sale as a **Sell** transaction in the Holdings table
(tap the holding → **📉 Sell / Close**). Simply deleting the holding does not
create a closed lot record.

---

**Q: My portfolio value looks wrong. How do I troubleshoot?**

1. Check that prices are up to date — click **🔄 Refresh Prices**
2. Check that all your holdings have a **valid ticker** that Yahoo Finance recognizes
3. Check the **Cash Ledger** for any duplicate or missing entries
4. Enable **🔧 Developer Mode** in Settings → you'll see an FX reconciliation
   table showing exactly how each holding's value is being calculated

---

**Q: How do I record a stock split?**

Go to **📜 Activity → Transaction History** → Add a transaction of type
**CORPORATE_ACTION**. Set the quantity adjustment (e.g. for a 2-for-1 split,
add +100% of your current quantity) and the effective date. Your average cost
will need to be updated manually to reflect the post-split price.

---

**Q: What is SAHMK Discovery?**

It's a feature that lets you browse Saudi-listed companies (Tadawul) from the
SAHMK data feed. You can discover companies by sector, view metrics, and add
them to your portfolio or research watchlist.

---

**Q: Can I import my transactions from my broker?**

Use the **📂 Upload Filing** sub-page in the Research tab to upload documents.
Bulk-import from broker CSV files requires the CSV format matching Bousala's
expected columns — see the **Upload** tab for the template.

---

**Q: How do I delete a holding I entered by mistake?**

Go to **💼 Holdings**, select the holding in the table, then look for the
**Delete / Remove** option in the action bar. Note: this only removes the
holding record. If you have related transactions, those remain in
Transaction History and should be voided separately.

---

**Q: I'm getting an FX warning in the header — what does it mean?**

A yellow FX warning means Bousala is using a **default/fallback exchange rate**
for one or more currencies, rather than a live rate. This can happen if:
- Yahoo Finance rate fetch failed temporarily
- The market is closed and rates are stale

Refresh prices to try fetching live rates again.

---
""")


def _s_settings() -> None:
    st.markdown("""
Open the **⚙️ Settings** expander in the sidebar to access:

---

### Demo Analysis Mode

When **on** (blue toggle): AI analysis returns pre-written sample data
instantly — no API key required, no cost. Perfect for exploring the app.

When **off**: AI analysis calls OpenAI for real results. Requires a valid
`OPENAI_API_KEY` secret.

---

### API Key Status

Shows whether your OpenAI API key is configured. If it shows ❌ missing:

1. Get an API key at [platform.openai.com](https://platform.openai.com)
2. Add it to Replit Secrets with the name `OPENAI_API_KEY`
3. Click **🔄 Reload secrets**

---

### Daily Usage Limit

Shows how many AI analyses you've run today. There's a daily cap to prevent
runaway API costs. The bar fills as you use analyses — when full, switch to
Demo Mode or wait until midnight.

---

### Analysis Cache

Analyses you've already run are cached locally. Re-analyzing the same filing
is instant and free (reads from cache). The cache count shows how many filings
are stored.

---

### Developer Mode

Turns on extra technical detail throughout the app:
- FX reconciliation tables in the header
- Raw valuation data breakdowns
- The **🧪 Test Runner** tab

Leave this off unless you're debugging a specific issue.

---
""")


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def render_help_tab() -> None:
    """Render the full user guide page (English or Arabic based on language selector)."""

    # ── Language selector ─────────────────────────────────────────────────────
    # Placed first so the Arabic version can take over before any EN widgets render.
    _lang = st.pills(
        "help_language",
        ["🇬🇧 English", "🇸🇦 العربية"],
        default=st.session_state.get("help_lang_sel", "🇬🇧 English"),
        label_visibility="collapsed",
        key="help_lang_sel",
    )
    if _lang == "🇸🇦 العربية":
        from help_guide_ar import render_help_tab_ar
        render_help_tab_ar()
        return

    # ── English content below ─────────────────────────────────────────────────

    # Back button at the very top so it's always visible
    col_back, col_title = st.columns([1, 5])
    with col_back:
        if st.button("← Back to App", key="help_back_btn", type="primary"):
            st.session_state["show_help"] = False
            st.rerun()
    with col_title:
        st.markdown("## 📖  Help & User Guide")

    st.caption(
        "This guide covers every feature of Bousala — no finance background required. "
        "Tap any section below to expand it."
    )
    st.divider()

    _section("🧭", "What is Bousala? — Start here",       _s_welcome,         expanded=True)
    _section("💡", "Key Terms Explained (plain English)",  _s_glossary)
    _section("📱", "Understanding the App Layout",         _s_layout)
    _section("🏦", "Balance Sheet Tab",                    _s_balance_sheet)
    _section("💼", "Portfolio Tab — Holdings, Allocation & Closed Positions", _s_portfolio)
    _section("💳", "Accounts & Cash Ledger",               _s_accounts)
    _section("📜", "Activity — Transactions & Cashflow",   _s_activity)
    _section("🧭", "Analysis — Performance, Risk & AI",   _s_analysis)
    _section("🔍", "Research — SEC Filings & SAHMK",       _s_research)
    _section("➕", "How to Add a Position (step-by-step)", _s_add_position)
    _section("📝", "How to Record Transactions (Buy / Sell / Dividend)", _s_transactions)
    _section("⚙️", "Settings & Demo Mode",                 _s_settings)
    _section("🕌", "Zakat Calculator",                     _s_zakat)
    _section("📊", "Tax Report — Realized Gains & Losses", _s_tax)
    _section("📄", "Wealth Statement PDF",                  _s_wealth_statement)
    _section("❓", "Frequently Asked Questions",            _s_faq)

    st.divider()
    st.caption("بوصلة — Investor Compass · All data stays on your device · v2.0")

    # Second back button at the bottom for long pages
    if st.button("← Back to App", key="help_back_btn_bottom"):
        st.session_state["show_help"] = False
        st.rerun()
