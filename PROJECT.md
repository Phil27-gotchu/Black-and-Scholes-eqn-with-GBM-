# B&S Terminal — Project Reference

A complete description of what this project is, what it does, and how each
piece works. Written so a reader who has never opened the repo can understand
the system to the core.

> **Stack:** FastAPI + vanilla HTML/CSS/JS (no React/Streamlit).  
> **Data:** Yahoo Finance via `yfinance` (delayed). Research / education only.  
> **Markets:** NASDAQ (US) and BSE (India, `.BO` symbols).

---



A command-driven **market and options terminal**. The user types Bloomberg-like
commands (`GP AAPL`, `IV NVDA`, `HB`, …) and gets live quotes, charts, company
profiles, filtered news, realized/GARCH volatility, implied-vol smiles, Black–
Scholes pricing, GBM/Monte Carlo sims, and a historical **delta-hedge backtest**
that compares static vs rolling vs GARCH hedge vol. Quant math lives in pure
NumPy (`quant.py`); market I/O and caching live in `market_data.py`; the API and
SPA sit on top.

---

## 2. Repository layout

| Path | Role |
|------|------|
| `app.py` | FastAPI server: JSON API + serves the SPA |
| `quant.py` | Pricing, vol forecasts, hedge engine, GBM, Monte Carlo |
| `market_data.py` | yfinance layer, watchlists, news tagging, option chains |
| `static/index.html` | Terminal shell (header, command bar, main pane) |
| `static/css/terminal.css` | Dark/light themes (CSS variables), layout |
| `static/js/app.js` | SPA router, command parser, Plotly charts, autocomplete |
| `tests/` | pytest: quant invariants, API contracts, market helpers |
| `shots/` | README screenshots |
| `archive/` | Old Streamlit prototypes (not used at runtime) |
| `watchlists.json` | User watchlists (created at runtime; gitignored) |
| `requirements.txt` | Python dependencies |
| `.github/workflows/ci.yml` | Runs `pytest -q` on every push/PR to `main` |
| `README.md` | Quick start + methodology notes |
| `PROJECT.md` | This document |

---

## 3. How to run

```bash
cd ~/B_N_S
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Interactive API docs: <http://127.0.0.1:8000/docs>.  
Tests: `pytest -q`.

---

## 4. Terminal commands (frontend)

Navigation is **command-driven**. Type in the command bar (or press `/` to focus).

| Command | Alias | Screen | What it does |
|---------|-------|--------|--------------|
| `MKT` | `W`, `MON` | Markets | Global monitor: NASDAQ + BSE sections, indices, watchlists, movers, benchmark chart |
| `NDQ` | `NASDAQ` | NASDAQ | Focused US view + relative performance + headlines |
| `BSE` | `INDIA`, `SENSEX` | BSE India | Focused India view + relative performance + headlines |
| `GP <ticker>` | `G` | Price chart | Candles, volume, MA20/MA50; ranges 1D…MAX |
| `DES <ticker>` | — | Profile | Fundamentals, description, 1Y chart, headlines |
| `VOL <ticker>` | — | Volatility | Realized 21d/63d + GARCH(1,1) forecast (2Y, no look-ahead) |
| `IV <ticker>` | `IMPLIED`, `SMILE` | Implied vol | Smile/skew, ATM term structure, IV vs realized vs GARCH |
| `N <ticker>` | `NEWS` | News router | Keyword / ticker / India / mega-cap filters; click → GP |
| `OV` | — | Option val | Black–Scholes price + greeks + curves vs spot |
| `GBM` | — | GBM sim | Simulated geometric Brownian motion paths |
| `MC` | — | Monte Carlo | Risk-neutral MC price vs closed-form BS |
| `HB` | `BT` | Hedge backtest | Historical delta-hedge: static vs rolling vs GARCH |
| `HELP` | `?` | Help | Command reference |

Bare ticker (single token, e.g. `NVDA`) jumps to that name’s **GP** chart.

### Frontend state (`static/js/app.js`)

| Attribute | Default | Meaning |
|-----------|---------|---------|
| `func` | `"MKT"` | Active command / page |
| `ticker` | `"AAPL"` | Active security |
| `gpRange` | `"1Y"` | Chart range for GP |
| `theme` | from `localStorage` | `"dark"` or `"light"` |
| `renderToken` | `0` | Cancels stale async renders |
| `newsScope` | `"all"` | News filter: `all` / `mega` / `india` / `name` |
| `newsQ` | `""` | News keyword |
| `newsFilter` | `""` | Extra ticker filter on news |

### UX features

- **Dark / light theme** — toggle in the top bar; persisted in `localStorage`.
- **Ticker tape** — scrolling quotes from indices + watchlists; refreshes ~90s.
- **Market clocks** — New York and Mumbai with open/closed status.
- **Watchlist add/remove** — per section (`nasdaq` / `bse`); persists in `watchlists.json`.
- **SECURITY autocomplete** — type `N` → rows like `NVDA [ NVIDIA ]` (GP, VOL, IV, N, HB).
- **News click-through** — headline or ticker chip navigates to `GP` for that name.
- **Function keys** — buttons under the command bar for every command.

### Crisis scenarios on HB

| Label | Start date |
|-------|------------|
| 2008 Financial Crisis | 2008-09-01 |
| Calm Period (2017) | 2017-01-03 |
| COVID Crash (2020) | 2020-02-14 |
| SVB / Regional Bank Crisis (2023) | 2023-03-01 |

---

## 5. Feature deep-dive

### 5.1 Markets (`MKT` / `NDQ` / `BSE`)

- Two universes with separate indices and watchlists.
- **NASDAQ indices:** `^IXIC`, `^NDX`, `^GSPC`, `^VIX`.
- **BSE / India indices:** `^BSESN`, `^NSEI`, `INR=X`.
- Default mega-cap US watchlist and large-cap `.BO` India watchlist (customizable).
- Movers (top gainers / losers), relative-performance overlay for up to 6 names.
- BSE history for `.BO` falls back to the dual-listed `.NS` symbol when Yahoo’s BSE history is empty.

### 5.2 Price chart (`GP`)

- OHLCV candlesticks via Plotly.
- Ranges: `1D`, `5D`, `1M`, `6M`, `YTD`, `1Y`, `5Y`, `MAX`.
- MA20 / MA50 when interval is daily/weekly and enough bars exist.
- Volume subplot colored by up/down days.

### 5.3 Profile (`DES`)

Fields shown: last, market cap, P/E (TTM & forward), 52w high/low, beta, dividend yield, revenue, net margin, ROE, employees, sector, industry, exchange, currency, long business summary, plus a 1Y chart and headlines.

### 5.4 Volatility (`VOL`)

- **Realized 21d / 63d** rolling annualized vol (causal).
- **GARCH(1,1)** one-day-ahead forecast, refit periodically on a trailing window (no look-ahead).
- Metrics: current realized levels, 2Y percentile of 21d vol, GARCH next-day forecast.

### 5.5 Implied volatility (`IV`)

- Pulls listed option chain; mid = (bid+ask)/2 (else last).
- **Newton–Raphson** implied vol via `quant.implied_vol` (uses vega × 100 — see §8).
- OTM smile: puts below spot, calls above.
- ATM strike = closest strike with IV; term structure across up to 8 expiries.
- **Vol risk premium** = ATM IV − realized 21d.
- Index/BSE underlyings map to liquid option symbols (e.g. `^GSPC` → SPY; `.BO` → NSE).
- Historical single-stock IV is **not** available on Yahoo — the IV history chart uses **today’s** ATM IV as a dashed reference vs realized/GARCH.

### 5.6 News router (`N`)

Not a raw dump. Headlines are **tagged** with tickers from title aliases, then filtered:

| Scope | Meaning |
|-------|---------|
| `all` | Combined tape |
| `mega` | US mega-caps (+ SPY/QQQ) |
| `india` | Indian names + Sensex/Nifty |
| `name` | Only the SECURITY in the box |

Also: keyword (`q`) and ticker filter. Click headline/chip → that name’s GP.

### 5.7 Option valuation (`OV`)

User inputs: spot `S`, strike `K`, expiry in trading days, rate `r`, vol `σ`, call/put.  
Returns price, delta, gamma, vega (per 1%), theta (per day), rho (per 1% rate), and curves of price/delta/gamma/vega vs spot.

### 5.8 GBM (`GBM`)

Simulates geometric Brownian motion paths. Inputs: `S0`, drift `μ`, `σ`, horizon days, number of paths (≤200), seed. Shows mean path and final-price stats.

### 5.9 Monte Carlo (`MC`)

Risk-neutral MC option price vs Black–Scholes closed form; returns 95% CI half-width and histograms of finals/payoffs. A European payoff only depends on S_T, and under GBM S_T is exactly lognormal, so terminal prices are sampled in one step: O(paths) time and memory, no path matrix.

### 5.10 Hedge backtest (`HB`)

1. Load historical closes for `ticker`: `window_days` sessions from `start`, plus up to 252 sessions of **lookback** before it (minimum 63, otherwise HTTP 400).
2. Short one European option (strike = `k_mult × S0`).
3. Delta-hedge along the path under three σ series, all causal:
   - **Static** — trailing realized vol over the lookback, i.e. the vol known at inception (constant).
   - **Rolling** — 21d realized, computed on lookback + window and sliced to the window.
   - **GARCH** — GARCH(1,1) fit on a trailing window that sits inside the lookback, so every day of the window has a real forecast.
4. Cash earns/pays interest: `cash *= exp(r·dt)` each step; transaction costs on trades.
5. Compare hedged P&L (final cash) vs unhedged (`premium − payout`).

**HB form attributes:** security, scenario (sets start date), start date, window days, strike % of S0, rate `r`, txn cost, rebalance every N days, call/put.

---

## 6. HTTP API reference

Base URL: `http://127.0.0.1:8000`. All market endpoints use uppercase tickers.

### Markets & watchlists

| Method | Path | Parameters | Returns |
|--------|------|------------|---------|
| GET | `/api/markets` | — | `nasdaq` / `bse` objects: `label`, `status`, `indices`, `watchlist`, `benchmark` |
| POST | `/api/watchlist/add` | `section`, `ticker` | `{ok, ticker, …}` or 404 |
| POST | `/api/watchlist/remove` | `section`, `ticker` | `{ok, ticker, …}` or 404 |
| GET | `/api/watchlist/search` | `q`, `section`=`nasdaq`\|`bse` | Up to 8 `{ticker, name, exchange, type}` |
| GET | `/api/symbols/search` | `q`, `limit` (1–20) | Cross-market autocomplete, prefix-ranked |
| GET | `/api/tape` | — | Quote list for tape symbols |

`section` must be `nasdaq` or `bse`.

### Security data

| Method | Path | Parameters | Returns |
|--------|------|------------|---------|
| GET | `/api/history` | `ticker`, `range` ∈ RANGE_MAP | `t,o,h,l,c,v`, ticker, range, interval |
| GET | `/api/profile` | `ticker` | Fundamentals object (see §5.3) |
| GET | `/api/news` | `ticker`, `limit` | Headlines for one name |
| GET | `/api/news/feed` | `scope`, `q`, `ticker`, `limit` | Filtered, tagged headlines |
| GET | `/api/vol` | `ticker`, `garch` | Dates, close, vol21, vol63, garch series, metrics |
| GET | `/api/iv` | `ticker`, `expiry?`, `r`, `garch` | Spot, chain IVs, smile, term, history, metrics |

### Quant lab

| Method | Path | Main parameters | Returns |
|--------|------|-----------------|---------|
| GET | `/api/ov` | `S,K,T_days,r,sigma,opt_type` | `greeks`, `spots`, `curves` |
| GET | `/api/gbm` | `S0,mu,sigma,T_days,n_paths,seed` | `paths`, `mean_path`, `stats` |
| GET | `/api/mc` | `S0,K,r,sigma,T_days,n_paths,opt_type,seed` | `mc_price`, `ci95`, `bs_price`, `diff`, samples |
| GET | `/api/backtest` | `ticker,start,window_days,k_mult,r,tc,rebalance,opt_type` | prices, dates, three `strategies` with P&L |

### Chart ranges (`RANGE_MAP`)

| Key | Yahoo period | Interval |
|-----|--------------|----------|
| 1D | 1d | 5m |
| 5D | 5d | 15m |
| 1M | 1mo | 1h |
| 6M | 6mo | 1d |
| YTD | ytd | 1d |
| 1Y | 1y | 1d |
| 5Y | 5y | 1wk |
| MAX | max | 1mo |

---

## 7. Module: `quant.py` (pure math)

No UI imports. Safe to unit-test offline.

### Volatility

| Function | Arguments | Behavior |
|----------|-----------|----------|
| `rolling_vol_forecast` | `price_series`, `window=21`, `annualize=252` | Trailing std of log returns × √252; **causal** (only data ≤ t) |
| `garch_vol_forecast` | `price_series`, `horizon=1`, `refit_every=5`, `window=252` | Rolling GARCH(1,1) one-step forecast; **causal**; falls back to rolling if `arch` missing |
| `clean_sigma_series` | `sigma_array`, `fallback_sigma` | Replaces NaN/≤0 with fallback for the hedge engine |

### Black–Scholes

| Function | Arguments | Returns |
|----------|-----------|---------|
| `bs_price_delta_greeks` | `S,K,T,r,sigma,option_type` | `dict`: `price`, `delta`, `gamma`, **`vega` (per 1% vol)**, `theta` (per trading day), `rho` (per 1% rate) |
| `implied_vol` | `market_price,S,K,T,r,option_type`, Newton params | σ such that BS = market; uses `dPrice/dσ = vega×100`; NaN if unusable |
| `option_mid` | `bid,ask,last` | Mid quote, else last, else bid |

### Hedge engine

| Function | Role |
|----------|------|
| `_bs_price_and_delta` | Internal price + delta only |
| `hedge_path_variable_sigma` | Short option, hedge with `sigma_hedge_series[t]`; cash interest `exp(r·dt)`; txn costs; returns hedged P&L, unhedged P&L, optional history |

**`hedge_path_variable_sigma` parameters:**  
`prices`, `K`, `r`, `sigma_hedge_series`, `T_total`, `n_steps`, `transaction_cost_rate`, `rebalance_every`, `option_type`, `option_premium`, `return_history`.

### Simulation

| Function | Role |
|----------|------|
| `simulate_gbm_paths` | `S0,μ,σ,T_days,n_steps,n_paths,seed` → path matrix |
| `monte_carlo_price` | `S0,K,r,σ,T_days,n_paths,option_type,seed` → price, stderr, finals, payoffs (exact terminal sampling) |

---

## 8. Module: `market_data.py` (data layer)

### Important constants

| Name | Meaning |
|------|---------|
| `NASDAQ_INDICES` / `NASDAQ_WATCHLIST` | Default US universe |
| `BSE_INDICES` / `BSE_WATCHLIST` | Default India universe |
| `MEGA_NEWS_TICKERS` / `INDIA_NEWS_TICKERS` | News scope sets |
| `WATCHLIST_FILE` | `watchlists.json` |
| `DEFAULT_WATCHLISTS` | Seed lists if file missing |
| `US_EXCHANGES` / `IN_EXCHANGES` | Filters for Yahoo Search |
| `OPTION_UNDERLYING` | Maps indices → optionable ETF/symbol |
| TTL caches | Quotes ~90s, history ~3 min, profiles ~1 h (via `@ttl_cache`; expired entries purged, 256 entries max per function) |
| `parallel_map` | Runs blocking Yahoo calls on a thread pool (news sources, IV term-structure chains), keeping input order |
| `YAHOO_SEARCH_TIMEOUT` | 3 s cap on Yahoo Search; one search per query serves both NASDAQ and BSE |

### Watchlists & search

| Function | Role |
|----------|------|
| `load_watchlists` / `_save_watchlists` | Persist custom lists |
| `watchlist_tickers` | Tickers for a section |
| `add_watchlist_ticker` / `remove_watchlist_ticker` | Validate vs Yahoo; BSE bare symbols get `.BO` |
| `_resolve_symbol` | Normalize user input per section |
| `_catalog` | Local name/ticker catalog for autocomplete |
| `_rank_symbol_hit` | Prefix rank: ticker > name > substring |
| `_local_symbol_search` | Local catalog search (1-letter = prefix only) |
| `search_symbols` | Local + Yahoo Search for one section |
| `search_symbols_all` | NASDAQ + BSE merged autocomplete |
| `tape_tickers` | Symbols for the scrolling tape |

### Quotes, history, profile, news

| Function | Role |
|----------|------|
| `get_quotes` | Batch last / chg / chg% |
| `get_history` | OHLCV; smart fallbacks for thin `.BO` / 1D India |
| `get_profile` | yfinance `info` dict |
| `tag_tickers` | Extract tickers from headline text via aliases |
| `filter_news_items` | Keyword + ticker + scope filter |
| `get_news` / `get_news_feed` | Single-name or multi-scope news tape |
| `fmt_big` | Human market-cap / revenue strings |

### Options

| Function | Role |
|----------|------|
| `resolve_option_ticker` / `option_chain_symbol` | Map request ticker → chain symbol |
| `get_option_expiries` | Listed expiry dates |
| `get_option_chain` | Calls/puts for an expiry |
| `get_spot` | Spot for IV / chain work |

---

## 9. Methodology (core interview points)

These are design choices, not UI chrome.

### Look-ahead

Rolling and GARCH vol forecasts at step *t* use **only** prices up to *t*. GARCH is refit on a trailing window, never the full sample including the future. That makes the HB “forecast” strategies honest.

### Vega units

`bs_price_delta_greeks` returns **vega per 1 percentage point** of vol (`∂Price / ∂(σ×100)`). Newton–Raphson needs `∂Price / ∂σ`, so implied vol updates with **`vega × 100`**. Mixing the units breaks IV. Rho is per 1% rate; theta is per trading day (`/252`).

### Hedge P&L

- Short one European at model (or given) premium.
- Hold Δ shares; rebalance every N steps.
- Cash: `cash *= exp(r·dt)` each step, then pay trade + fee.
- At expiry: pay option payout, unwind stock.
- **Hedged P&L** = final cash. **Unhedged P&L** = premium − payout.
- Under true vol, zero costs, and interest, mean hedged P&L should be near zero (regression-tested; missing interest once biased mean ≈ 0.55).

---

## 10. Tests & CI

| File | Covers |
|------|--------|
| `tests/test_quant.py` | Put-call parity, greeks, IV round-trip, hedge interest invariant, txn costs |
| `tests/test_api.py` | Endpoint contracts with Yahoo **mocked** |
| `tests/test_market_data.py` | Watchlists, search filters, news tagging/filtering |

GitHub Actions (`.github/workflows/ci.yml`): Python 3.12, `pip install -r requirements.txt`, `pytest -q` on push/PR to `main`.

---

## 11. Dependencies

| Package | Use |
|---------|-----|
| `fastapi` / `uvicorn` | HTTP API + static SPA |
| `yfinance` | Quotes, history, news, Search, option chains |
| `numpy` / `pandas` / `scipy` | Numerics, Series, normal CDF |
| `arch` | GARCH(1,1) |
| `statsmodels` | Supporting econometrics stack |
| `pytest` / `httpx` | Tests + FastAPI TestClient |

Frontend CDN: Plotly, IBM Plex Mono (Google Fonts).

---

## 12. Explicit limitations

- Data is **delayed** Yahoo Finance — not a trading venue.
- Indian listed options are often missing or thin on Yahoo.
- No historical single-stock IV series from Yahoo (IV page uses live ATM as a reference line).
- No user accounts, auth, or paper portfolio yet.
- In-process TTL cache only (one server process).
- Calling it “Bloomberg” is a UX metaphor; it is an educational terminal, not a replacement for a professional feed.

---

## 13. Suggested talking points for demos / interviews

1. **Architecture split:** pure `quant.py` vs cached `market_data.py` vs thin `app.py` + SPA.  
2. **Causal vol + hedge backtest** with cash interest and the P&L invariant test.  
3. **IV pipeline:** mid quotes → Newton–Raphson with correct vega units → smile + vol risk premium.  
4. **News as a router**, not a dump (tag → filter → click to chart).  
5. **Dual-market design:** NASDAQ vs BSE, `.BO`/`.NS` history fallback, separate watchlists.  
6. **Engineering hygiene:** pytest + GitHub Actions with mocked live data.

---

*End of project reference. For a shorter overview, see `README.md`.*
