# B&S Terminal — NASDAQ and BSE

A command-driven market and options terminal for **NASDAQ (US)** and
**BSE (India)**. FastAPI backend, no frontend framework. The interesting
part is the quant stack: Black-Scholes, implied vol, GARCH with no
look-ahead, Monte Carlo, and a historical delta-hedge backtest.

> Market data comes from Yahoo Finance (delayed). For research and education
> only — not investment advice.

---

## Screenshots

Files live in [`shots/`](shots/) and are linked with relative paths
(`shots/….png`). They render in this folder and on GitHub once those files
are on the branch you are viewing. If the GitHub copy is **private**,
logged-out visitors will see broken images — that is access, not a missing
file.

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

- **MKT** — global monitor with two dedicated sections: NASDAQ (Composite,
  NASDAQ-100, S&P 500, VIX + mega-cap watchlist) and BSE (SENSEX, NIFTY 50,
  USD/INR + large-cap `.BO` watchlist), each with live status, movers, and a
  benchmark chart.
- **Customizable watchlists** — add or remove symbols per section straight
  from the UI (`+ ADD` in the watchlist header, `✕` on any row). Symbols are
  validated against Yahoo before being added; bare symbols in the BSE section
  get the `.BO` suffix automatically (`TITAN` → `TITAN.BO`). Changes persist
  server-side in `watchlists.json`, and the movers, relative-performance
  chart, and ticker tape follow your custom lists.
- **NDQ / BSE** — focused views per exchange with relative-performance charts
  and headlines.
- **GP** — candlestick price charts with volume and MA20/MA50, ranges from
  intraday (1D) to MAX. SECURITY boxes autocomplete as you type
  (`N` → `NVDA [ NVIDIA ]`); click or Enter to load that name.
- **DES** — company profile: valuation multiples, margins, 52-week range,
  business description, headlines.
- **VOL** — realized volatility (21d / 63d rolling) plus a rolling
  GARCH(1,1) one-day-ahead forecast, fit with no look-ahead.
- **IV** — implied volatility from listed option chains: Newton-Raphson
  inversion of Black-Scholes on bid/ask mids, OTM smile/skew, ATM term
  structure, and live ATM IV vs realized vs GARCH (the volatility risk
  premium). Indices map to ETF chains (`^GSPC` → SPY); `.BO` names use NSE.
- **N** — news router: keyword, ticker, India vs US mega-cap scopes.
  Click a headline or ticker chip to load that name's price chart (`GP`).

**Quant lab**

- **OV** — Black-Scholes price and full greeks, with price/delta/gamma/vega
  curves across spot.
- **GBM** — geometric Brownian motion path simulator.
- **MC** — risk-neutral Monte Carlo pricer benchmarked against the closed form.
- **HB** — historical delta-hedge backtest: short an option on a real price
  window (2008 crisis, COVID crash, SVB 2023, …) and compare hedging under a
  static vol assumption vs rolling-window vs GARCH(1,1) forecasts, including
  transaction costs and rebalancing frequency.

**Terminal UX**

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

Open <http://localhost:8000>. Interactive API docs are at
<http://localhost:8000/docs>.

---

## Commands

| Command         | Function                                              |
| --------------- | ----------------------------------------------------- |
| `MKT`           | Global markets — NASDAQ + BSE sections                |
| `NDQ`           | NASDAQ section                                        |
| `BSE`           | BSE India section                                     |
| `GP <ticker>`   | Price chart (candles, volume, moving averages)        |
| `DES <ticker>`  | Security profile                                      |
| `VOL <ticker>`  | Volatility monitor (realized + GARCH forecast)        |
| `IV <ticker>`   | Implied vol smile, term structure, vs realized/GARCH  |
| `N <ticker>`    | News router (keyword / India / mega-cap → GP)         |
| `OV`            | Black-Scholes option valuation                        |
| `GBM`           | GBM path simulator                                    |
| `MC`            | Monte Carlo option pricer                             |
| `HB`            | Historical delta-hedge backtest                       |
| `HELP`          | Command reference                                     |

BSE symbols use Yahoo's `.BO` suffix (`RELIANCE.BO`, `TCS.BO`,
`HDFCBANK.BO`, …). US symbols are plain (`AAPL`, `NVDA`). Indices:
`^IXIC`, `^BSESN`, `^NSEI`, `^GSPC`.

> Note: Yahoo's BSE feed only serves live quotes; historical charts for `.BO`
> symbols transparently fall back to the company's NSE listing (`.NS`), which
> is dual-listed at virtually identical prices. SENSEX (`^BSESN`) history
> works natively.

---

## Architecture

```
app.py           FastAPI app — JSON API + serves the frontend
quant.py         Pure-numpy quant engines (Black-Scholes, GBM, Monte Carlo,
                 variable-sigma delta-hedge engine, rolling & GARCH vol)
market_data.py   yfinance data layer with in-process TTL caching,
                 NASDAQ + BSE universes
static/
  index.html     Terminal shell
  css/terminal.css   Dark/light themes via CSS variables
  js/app.js      SPA router, command parser, Plotly rendering
tests/           pytest suite — put-call parity, hedge-bias, API contracts
archive/         Early Streamlit prototypes — not used at runtime
```

The backend is stateless; all market data is cached in-process with short
TTLs (quotes 90 s, history 3 min, profiles 1 h). The quant module has no
framework dependencies and is directly unit-testable.

```bash
pytest -q
```

GitHub Actions runs the same suite on every push to `main`. Live Yahoo
endpoints are mocked so CI stays offline and deterministic.

### Key API endpoints

| Endpoint         | Description                                    |
| ---------------- | ---------------------------------------------- |
| `/api/markets`   | NASDAQ + BSE indices, watchlists, market state |
| `/api/watchlist/add`, `/api/watchlist/remove` | Customize section watchlists (POST) |
| `/api/history`   | OHLCV for any Yahoo symbol, `range=1D…MAX`     |
| `/api/vol`       | Realized + GARCH volatility series             |
| `/api/news/feed` | Filtered news tape (keyword, ticker, india/mega)  |
| `/api/ov`        | Black-Scholes greeks + curves                  |
| `/api/mc`        | Monte Carlo pricing vs closed form             |
| `/api/backtest`  | Delta-hedge backtest on historical windows     |

---

## Methodology

Three details that are in the code, not the theme toggle.

**Look-ahead.** Rolling realized vol and GARCH(1,1) are causal. At step
*t* the forecast uses only prices `≤ t`. GARCH is refit on a trailing
window, never the whole sample. A “GARCH hedge” that peeks at future
returns is not a forecast.

**Vega units.** `bs_price_delta_greeks` returns vega as ∂Price / ∂(1 vol
point), i.e. per 1%. Newton–Raphson implied vol needs ∂Price / ∂σ, so the
update is `σ ← σ − (model − market) / (vega × 100)`. Mixing those units
makes IV explode or refuse to converge. Rho is also per 1% rate; theta is
per trading day (`/ 252`).

**Hedge P&L.** The backtester is short one European, long Δ shares,
financed with a cash account. Each step, `cash *= exp(r·dt)` before
rebalancing, then transaction costs hit the cash. At expiry you pay the
option payout and unwind the stock. Hedged P&L is the final cash;
unhedged P&L is `premium − payout`. Under the true vol, zero costs, and
interest on cash, mean hedged P&L should sit near zero (the test that
caught a ~0.55 bias when interest was omitted). Lower variance vs the
naked short is the hedge working; static σ vs rolling vs GARCH is whether
the vol forecast earns its keep in a crisis window.
