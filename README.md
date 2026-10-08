# B&S Terminal — NASDAQ and BSE

A command-driven market and options terminal for **NASDAQ (National Association
of Securities Dealers Automated Quotations, US)** and **BSE (Bombay Stock
Exchange, India)**. FastAPI backend, no frontend framework. The interesting
part is the quant stack: Black-Scholes, implied vol, GARCH (Generalized
Autoregressive Conditional Heteroskedasticity) with no look-ahead, Monte Carlo,
and a historical delta-hedge backtest.

> Market data comes from Yahoo Finance (delayed). For research and education
> only — not investment advice.

For a full walkthrough of every feature, command, API (Application Programming
Interface), and module function, see **[PROJECT.md](PROJECT.md)**.

---

## Screenshots

Files live in [`shots/`](shots/) and are linked with relative paths
(`shots/….png`). 

### Market monitor — NASDAQ and BSE

![Market monitor, dark theme](shots/markets_dark.png)

### Light theme

![Market monitor, light theme](shots/markets_light.png)

### Price chart — candles, volume, moving averages

![Price chart for RELIANCE.BO](shots/chart_bse.png)

### Volatility monitor — realized vol + GARCH(1,1)

![Volatility monitor for NVDA](shots/volatility.png)

### Historical delta-hedge backtest

![Delta-hedge backtest](shots/backtest.png)

### Customizable watchlists

![Custom watchlist](shots/watchlist_custom.png)

---

## Features

**Markets**

- **MKT (Markets)** — global monitor with two dedicated sections: NASDAQ
  (Composite, NASDAQ-100, S&P 500 (Standard & Poor's 500), VIX (CBOE Volatility
  Index) + mega-cap watchlist) and BSE (SENSEX (Sensitive Index), NIFTY 50
  (National Stock Exchange Fifty), USD/INR (US Dollar / Indian Rupee) +
  large-cap `.BO` watchlist), each with live status, movers, and a benchmark
  chart.
- **Customizable watchlists** — add or remove symbols per section straight
  from the UI (User Interface) (`+ ADD` in the watchlist header, `✕` on any
  row). Symbols are validated against Yahoo before being added; bare symbols
  in the BSE section get the `.BO` suffix automatically (`TITAN` →
  `TITAN.BO`). Changes persist server-side in `watchlists.json`, and the
  movers, relative-performance chart, and ticker tape follow your custom
  lists.
- **NDQ (NASDAQ) / BSE (Bombay Stock Exchange)** — focused views per exchange
  with relative-performance charts and headlines.
- **GP (Price Chart)** — candlestick price charts with volume and MA20/MA50
  (Moving Average 20 / 50), ranges from intraday (1D) to MAX. SECURITY boxes
  autocomplete as you type (`N` → `NVDA [ NVIDIA ]`); click or Enter to load
  that name.
- **DES (Profile)** — company profile: valuation multiples, margins, 52-week
  range, business description, headlines.
- **VOL (Volatility)** — realized volatility (21d / 63d rolling) plus a
  rolling GARCH(1,1) (Generalized Autoregressive Conditional
  Heteroskedasticity) one-day-ahead forecast, fit with no look-ahead.
- **IV (Implied Volatility)** — implied volatility from listed option chains:
  Newton-Raphson inversion of Black-Scholes on bid/ask mids, OTM (Out of The
  Money) smile/skew, ATM (At The Money) term structure, and live ATM IV vs
  realized vs GARCH (the volatility risk premium). Indices map to ETF
  (Exchange-Traded Fund) chains (`^GSPC` → SPY); `.BO` names use NSE (National
  Stock Exchange).
- **N (News)** — news router: keyword, ticker, India vs US mega-cap scopes.
  Click a headline or ticker chip to load that name's price chart (`GP`).

**Quant lab**

- **OV (Option Valuation)** — Black-Scholes price and full greeks, with
  price/delta/gamma/vega curves across spot.
- **GBM (Geometric Brownian Motion)** — geometric Brownian motion path
  simulator.
- **MC (Monte Carlo)** — risk-neutral Monte Carlo pricer benchmarked against
  the closed form. Terminal prices are sampled exactly in one step, so cost
  is O(paths).
- **HB (Hedge Backtest)** — historical delta-hedge backtest: short an option
  on a real price window (2008 crisis, COVID crash, SVB (Silicon Valley Bank)
  2023, …) and compare hedging under a static vol (the trailing vol known on
  the start date) vs rolling-window vs GARCH(1,1) forecasts, including
  transaction costs and rebalancing frequency. Forecasts warm up on up to a
  year of history before the start date (at least 63 sessions required).

**Terminal UX (User Experience)**

- Bloomberg-style command line: `GP RELIANCE.BO`, `IV NVDA`, `VOL TCS.BO`,
  `HB`, or just a bare ticker. Press `/` to focus the command line.
- Dark and light themes (toggle in the top bar, persisted across sessions).
- Scrolling ticker tape, New York + Mumbai market clocks with open/closed
  status, clickable watchlists.

---

## Getting started

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app:app --port 8000
```

Open <http://localhost:8000>. Interactive API (Application Programming
Interface) docs are at <http://localhost:8000/docs>.

---

## Commands

| Command         | Function                                              |
| --------------- | ----------------------------------------------------- |
| `MKT` (Markets) | Global markets — NASDAQ + BSE sections                |
| `NDQ` (NASDAQ)  | NASDAQ section                                        |
| `BSE` (Bombay Stock Exchange) | BSE India section                           |
| `GP` (Price Chart) `<ticker>` | Price chart (candles, volume, moving averages) |
| `DES` (Profile) `<ticker>` | Security profile                                   |
| `VOL` (Volatility) `<ticker>` | Volatility monitor (realized + GARCH forecast) |
| `IV` (Implied Volatility) `<ticker>` | Implied vol smile, term structure, vs realized/GARCH |
| `N` (News) `<ticker>` | News router (keyword / India / mega-cap → GP)     |
| `OV` (Option Valuation) | Black-Scholes option valuation                  |
| `GBM` (Geometric Brownian Motion) | GBM path simulator                      |
| `MC` (Monte Carlo) | Monte Carlo option pricer                          |
| `HB` (Hedge Backtest) | Historical delta-hedge backtest                 |
| `HELP` (Help)   | Command reference                                     |

BSE symbols use Yahoo's `.BO` suffix (`RELIANCE.BO`, `TCS.BO`,
`HDFCBANK.BO`, …). US symbols are plain (`AAPL`, `NVDA`). Indices:
`^IXIC`, `^BSESN`, `^NSEI`, `^GSPC`.

> Note: Yahoo's BSE feed only serves live quotes; historical charts for `.BO`
> symbols transparently fall back to the company's NSE (National Stock
> Exchange) listing (`.NS`), which is dual-listed at virtually identical
> prices. SENSEX (`^BSESN`) history works natively.

---

## Architecture

```
app.py           FastAPI app — JSON (JavaScript Object Notation) API + serves the frontend
quant.py         Pure-numpy quant engines (Black-Scholes, GBM, Monte Carlo,
                 variable-sigma delta-hedge engine, rolling & GARCH vol)
market_data.py   yfinance data layer with in-process TTL (Time To Live) caching,
                 NASDAQ + BSE universes
static/
  index.html     Terminal shell
  css/terminal.css   Dark/light themes via CSS (Cascading Style Sheets) variables
  js/app.js      SPA (Single-Page Application) router, command parser, Plotly rendering
tests/           pytest suite — put-call parity, hedge-bias, API contracts
archive/         Early Streamlit prototypes — not used at runtime
```

The backend is stateless; all market data is cached in-process with short
TTLs (Time To Live) (quotes 90 s, history 3 min, profiles 1 h). The quant
module has no framework dependencies and is directly unit-testable.

```bash
pytest -q
```

GitHub Actions runs the same suite on every push to `main`. Live Yahoo
endpoints are mocked so CI (Continuous Integration) stays offline and
deterministic.

### Key API (Application Programming Interface) endpoints

| Endpoint         | Description                                    |
| ---------------- | ---------------------------------------------- |
| `/api/markets`   | NASDAQ + BSE indices, watchlists, market state |
| `/api/watchlist/add`, `/api/watchlist/remove` | Customize section watchlists (POST) |
| `/api/history`   | OHLCV (Open, High, Low, Close, Volume) for any Yahoo symbol, `range=1D…MAX` |
| `/api/vol`       | Realized + GARCH volatility series             |
| `/api/news/feed` | Filtered news tape (keyword, ticker, india/mega)  |
| `/api/ov`        | Black-Scholes greeks + curves                  |
| `/api/mc`        | Monte Carlo pricing vs closed form             |
| `/api/backtest`  | Delta-hedge backtest on historical windows     |

---

## Methodology

Three details that are in the code, not the theme toggle.

**Look-ahead.** Rolling realized vol and GARCH(1,1) (Generalized Autoregressive
Conditional Heteroskedasticity) are causal. At step *t* the forecast uses only
prices `≤ t`. GARCH is refit on a trailing window, never the whole sample. A
“GARCH hedge” that peeks at future returns is not a forecast. In the
backtest, both forecasts are warmed up on history *before* the start date,
and the static σ is the trailing vol known on that date, so no strategy
sees a price from later in the window. `test_backtest_no_lookahead` shocks
late-window prices and checks that earlier hedge vols do not move.

**Vega units.** `bs_price_delta_greeks` returns vega as ∂Price / ∂(1 vol
point), i.e. per 1%. Newton–Raphson implied vol needs ∂Price / ∂σ, so the
update is `σ ← σ − (model − market) / (vega × 100)`. Mixing those units
makes IV (Implied Volatility) explode or refuse to converge. Rho is also per
1% rate; theta is per trading day (`/ 252`).

**Hedge P&L (Profit and Loss).** The backtester is short one European, long Δ
shares, financed with a cash account. Each step, `cash *= exp(r·dt)` before
rebalancing, then transaction costs hit the cash. At expiry you pay the option
payout and unwind the stock. Hedged P&L is the final cash; unhedged P&L is
`premium − payout`. Under the true vol, zero costs, and interest on cash,
mean hedged P&L should sit near zero (the test that caught a ~0.55 bias when
interest was omitted). Lower variance vs the naked short is the hedge working;
static σ vs rolling vs GARCH is whether the vol forecast earns its keep in a
crisis window.
