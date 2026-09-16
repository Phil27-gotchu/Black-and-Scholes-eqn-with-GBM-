"""
B&S TERMINAL — FastAPI backend.

Run with:
    uvicorn app:app --reload --port 8000

Serves the single-page terminal frontend from /static and a JSON API:

    /api/markets            NASDAQ + BSE sections (indices, watchlists, status)
    /api/tape               ticker-tape quotes
    /api/history            OHLCV history for any Yahoo symbol
    /api/profile            company fundamentals
    /api/news               headlines for one ticker
    /api/news/feed          filtered tape (keyword, ticker, india / mega-cap)
    /api/vol                realized + GARCH volatility series
    /api/ov                 Black-Scholes valuation + greek curves
    /api/iv                 implied vol smile, term structure, vs realized/GARCH
    /api/gbm                GBM path simulation
    /api/mc                 Monte Carlo option pricing
    /api/backtest           historical delta-hedge backtest
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import market_data as md
import quant

app = FastAPI(title="B&S Terminal API", version="2.0")

STATIC_DIR = Path(__file__).parent / "static"


# ------------------------------------------------------------
# helpers
# ------------------------------------------------------------

def jlist(arr):
    """numpy array -> JSON-safe list (NaN -> None)."""
    out = []
    for v in np.asarray(arr, dtype=float):
        out.append(None if np.isnan(v) else round(float(v), 6))
    return out


def market_status(tz_name, open_hm, close_hm):
    now = datetime.now(ZoneInfo(tz_name))
    is_weekday = now.weekday() < 5
    minutes = now.hour * 60 + now.minute
    is_open = is_weekday and open_hm <= minutes < close_hm
    return {
        "local_time": now.strftime("%H:%M"),
        "open": is_open,
        "label": "OPEN" if is_open else "CLOSED",
    }


def hist_payload(df: pd.DataFrame) -> dict:
    idx = df.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    return {
        "t": [ts.isoformat() for ts in idx.to_pydatetime()],
        "o": jlist(df["Open"].values),
        "h": jlist(df["High"].values),
        "l": jlist(df["Low"].values),
        "c": jlist(df["Close"].values),
        "v": jlist(df["Volume"].values) if "Volume" in df else [],
    }


# ------------------------------------------------------------
# market data endpoints
# ------------------------------------------------------------

@app.get("/api/markets")
def api_markets():
    return {
        "nasdaq": {
            "label": "NASDAQ · NEW YORK",
            "status": market_status("America/New_York", 9 * 60 + 30, 16 * 60),
            "indices": md.get_quotes(tuple(t for t, _ in md.NASDAQ_INDICES)),
            "watchlist": md.get_quotes(tuple(md.watchlist_tickers("nasdaq"))),
            "benchmark": "^IXIC",
        },
        "bse": {
            "label": "BSE · MUMBAI",
            "status": market_status("Asia/Kolkata", 9 * 60 + 15, 15 * 60 + 30),
            "indices": md.get_quotes(tuple(t for t, _ in md.BSE_INDICES)),
            "watchlist": md.get_quotes(tuple(md.watchlist_tickers("bse"))),
            "benchmark": "^BSESN",
        },
    }


@app.post("/api/watchlist/add")
def api_watchlist_add(section: str, ticker: str):
    if section not in ("nasdaq", "bse"):
        raise HTTPException(400, "section must be 'nasdaq' or 'bse'")
    result = md.add_watchlist_ticker(section, ticker)
    if not result["ok"]:
        raise HTTPException(404, result["msg"])
    return result


@app.post("/api/watchlist/remove")
def api_watchlist_remove(section: str, ticker: str):
    if section not in ("nasdaq", "bse"):
        raise HTTPException(400, "section must be 'nasdaq' or 'bse'")
    result = md.remove_watchlist_ticker(section, ticker)
    if not result["ok"]:
        raise HTTPException(404, result["msg"])
    return result


@app.get("/api/watchlist/search")
def api_watchlist_search(q: str, section: str = "nasdaq"):
    if section not in ("nasdaq", "bse"):
        raise HTTPException(400, "section must be 'nasdaq' or 'bse'")
    return md.search_symbols(q, section=section, limit=8)


@app.get("/api/tape")
def api_tape():
    return md.get_quotes(tuple(md.tape_tickers()))


@app.get("/api/history")
def api_history(ticker: str, range: str = Query("1Y", alias="range")):
    rng = range.upper()
    if rng not in md.RANGE_MAP:
        raise HTTPException(400, f"range must be one of {list(md.RANGE_MAP)}")
    period, interval = md.RANGE_MAP[rng]
    df = md.get_history(ticker.upper(), period, interval)
    if df.empty:
        raise HTTPException(404, f"No data for '{ticker}'")
    payload = hist_payload(df)
    payload["ticker"] = ticker.upper()
    payload["range"] = rng
    payload["interval"] = interval
    return payload


@app.get("/api/profile")
def api_profile(ticker: str):
    t = ticker.upper()
    info = md.get_profile(t)
    if not info:
        raise HTTPException(404, f"No profile for '{t}'")
    dy = info.get("dividendYield")
    if isinstance(dy, (int, float)) and dy > 1:  # yfinance sometimes returns percent
        dy = dy / 100
    fields = {
        "name": info.get("longName") or info.get("shortName") or t,
        "last": info.get("regularMarketPrice") or info.get("currentPrice"),
        "market_cap": md.fmt_big(info.get("marketCap")),
        "pe_ttm": info.get("trailingPE"),
        "pe_fwd": info.get("forwardPE"),
        "high_52w": info.get("fiftyTwoWeekHigh"),
        "low_52w": info.get("fiftyTwoWeekLow"),
        "beta": info.get("beta"),
        "div_yield": dy,
        "revenue": md.fmt_big(info.get("totalRevenue")),
        "net_margin": info.get("profitMargins"),
        "roe": info.get("returnOnEquity"),
        "employees": info.get("fullTimeEmployees"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "exchange": info.get("exchange"),
        "currency": info.get("currency"),
        "summary": info.get("longBusinessSummary"),
    }
    return {"ticker": t, **fields}


@app.get("/api/news")
def api_news(ticker: str, limit: int = 10):
    return md.get_news(ticker.upper(), limit=limit)


@app.get("/api/news/feed")
def api_news_feed(scope: str = "all", q: str = "", ticker: str = "", limit: int = 40):
    if scope not in ("all", "india", "mega", "name"):
        raise HTTPException(400, "scope must be all, india, mega, or name")
    return md.get_news_feed(scope=scope, query=q, ticker=ticker, limit=min(limit, 60))


@app.get("/api/vol")
def api_vol(ticker: str, garch: bool = True):
    t = ticker.upper()
    df = md.get_history(t, "2y", "1d")
    if df.empty or len(df) < 130:
        raise HTTPException(404, f"Not enough history for '{t}'")
    prices = df["Close"].values
    idx = df.index.tz_localize(None) if df.index.tz is not None else df.index

    vol21 = quant.rolling_vol_forecast(prices, window=21)
    vol63 = quant.rolling_vol_forecast(prices, window=63)
    garch_fc = None
    if garch:
        garch_fc = quant.garch_vol_forecast(prices, refit_every=10,
                                            window=min(252, len(prices) - 10))

    v21 = vol21[~np.isnan(vol21)]
    cur21 = float(v21[-1])
    cur63 = float(vol63[~np.isnan(vol63)][-1])
    pctile = float((v21 < cur21).mean() * 100)
    garch_next = None
    if garch_fc is not None:
        g = garch_fc[~np.isnan(garch_fc)]
        garch_next = float(g[-1]) if len(g) else None

    return {
        "ticker": t,
        "dates": [ts.isoformat() for ts in idx.to_pydatetime()],
        "close": jlist(prices),
        "vol21": jlist(vol21),
        "vol63": jlist(vol63),
        "garch": jlist(garch_fc) if garch_fc is not None else None,
        "metrics": {
            "realized_21d": cur21,
            "realized_63d": cur63,
            "percentile_2y": pctile,
            "garch_next_day": garch_next,
        },
    }


def _finite(x):
    return x is not None and not (isinstance(x, float) and (np.isnan(x) or np.isinf(x)))


def _invert_chain_side(rows, S, T, r, option_type):
    out = []
    for row in rows:
        k = row.get("strike")
        if k is None:
            continue
        mid = quant.option_mid(row.get("bid"), row.get("ask"), row.get("last"))
        iv = quant.implied_vol(mid, S, k, T, r, option_type) if mid else float("nan")
        out.append({
            "strike": round(float(k), 4),
            "mid": None if mid is None else round(float(mid), 4),
            "iv": round(float(iv), 6) if _finite(iv) else None,
            "yahoo_iv": row.get("yahoo_iv"),
            "volume": row.get("volume") or 0,
            "oi": row.get("oi") or 0,
        })
    return out


def _atm_iv(calls, puts, spot):
    """OTM convention: put IV below spot, call IV above; ATM = closest strike."""
    by_k = {}
    for row in puts:
        if row["iv"] is not None and row["strike"] <= spot:
            by_k[row["strike"]] = row["iv"]
    for row in calls:
        if row["iv"] is not None and row["strike"] >= spot:
            by_k[row["strike"]] = row["iv"]
    if not by_k:
        pool = [row for row in calls + puts if row["iv"] is not None]
        if not pool:
            return None, None
        nearest = min(pool, key=lambda row: abs(row["strike"] - spot))
        return nearest["strike"], nearest["iv"]
    k = min(by_k, key=lambda x: abs(x - spot))
    return k, by_k[k]


@app.get("/api/iv")
def api_iv(ticker: str, expiry: str | None = None, r: float = 0.04, garch: bool = True):
    t = ticker.upper()
    symbol = md.option_chain_symbol(t)
    expiries = list(md.get_option_expiries(t))
    if not expiries:
        raise HTTPException(404, f"No listed options for '{t}' (tried {symbol}).")

    if expiry:
        expiry = expiry[:10]
        if expiry not in expiries:
            raise HTTPException(400, f"expiry must be one of {expiries[:12]}")
    else:
        expiry = expiries[0]

    spot = md.get_spot(t)
    if spot is None:
        raise HTTPException(404, f"No spot price for '{t}'.")

    exp_dt = pd.Timestamp(expiry).normalize()
    today = pd.Timestamp.now(tz=None).normalize()
    cal_days = max(int((exp_dt - today).days), 1)
    T = cal_days / 365.25

    chain = md.get_option_chain(t, expiry)
    calls = _invert_chain_side(chain.get("calls") or [], spot, T, r, "call")
    puts = _invert_chain_side(chain.get("puts") or [], spot, T, r, "put")
    atm_k, atm_iv = _atm_iv(calls, puts, spot)

    otm = []
    for row in puts:
        if row["iv"] is not None and row["strike"] <= spot:
            otm.append({"strike": row["strike"], "iv": row["iv"], "side": "put"})
    for row in calls:
        if row["iv"] is not None and row["strike"] >= spot:
            otm.append({"strike": row["strike"], "iv": row["iv"], "side": "call"})
    otm.sort(key=lambda x: x["strike"])

    term = []
    for exp in expiries[:8]:
        if exp == expiry:
            term.append({"expiry": exp, "atm_iv": atm_iv, "T_days": cal_days})
            continue
        exp_i = pd.Timestamp(exp).normalize()
        days_i = max(int((exp_i - today).days), 1)
        T_i = days_i / 365.25
        ch_i = md.get_option_chain(t, exp)
        c_i = _invert_chain_side(ch_i.get("calls") or [], spot, T_i, r, "call")
        p_i = _invert_chain_side(ch_i.get("puts") or [], spot, T_i, r, "put")
        _, iv_i = _atm_iv(c_i, p_i, spot)
        term.append({"expiry": exp, "atm_iv": iv_i, "T_days": days_i})

    df = md.get_history(t, "2y", "1d")
    vol21 = garch_fc = None
    realized_21d = garch_next = None
    dates, close = [], []
    if not df.empty and len(df) >= 30:
        prices = df["Close"].values
        idx = df.index.tz_localize(None) if df.index.tz is not None else df.index
        dates = [ts.isoformat() for ts in idx.to_pydatetime()]
        close = jlist(prices)
        vol21 = quant.rolling_vol_forecast(prices, window=21)
        v21 = vol21[~np.isnan(vol21)]
        realized_21d = float(v21[-1]) if len(v21) else None
        if garch and len(prices) >= 130:
            garch_fc = quant.garch_vol_forecast(
                prices, refit_every=10, window=min(252, len(prices) - 10))
            g = garch_fc[~np.isnan(garch_fc)]
            garch_next = float(g[-1]) if len(g) else None

    premium = None
    if atm_iv is not None and realized_21d is not None:
        premium = atm_iv - realized_21d

    return {
        "ticker": t,
        "chain_symbol": chain.get("symbol") or symbol,
        "spot": round(float(spot), 4),
        "r": r,
        "expiries": expiries,
        "expiry": expiry,
        "T_days": cal_days,
        "metrics": {
            "atm_strike": atm_k,
            "atm_iv": atm_iv,
            "realized_21d": realized_21d,
            "garch_next_day": garch_next,
            "vol_premium": premium,
        },
        "calls": calls,
        "puts": puts,
        "otm_skew": otm,
        "term": term,
        "history": {
            "dates": dates,
            "close": close,
            "vol21": jlist(vol21) if vol21 is not None else [],
            "garch": jlist(garch_fc) if garch_fc is not None else None,
        },
    }


# ------------------------------------------------------------
# quant endpoints
# ------------------------------------------------------------

@app.get("/api/ov")
def api_ov(S: float, K: float, T_days: int, r: float, sigma: float,
           opt_type: str = "call"):
    if opt_type not in ("call", "put"):
        raise HTTPException(400, "opt_type must be call or put")
    T = T_days / 252
    g = quant.bs_price_delta_greeks(S, K, T, r, sigma, opt_type)

    spots = np.linspace(S * 0.5, S * 1.5, 120)
    curves = {k: [] for k in ("price", "delta", "gamma", "vega")}
    for s in spots:
        gg = quant.bs_price_delta_greeks(float(s), K, T, r, sigma, opt_type)
        for k in curves:
            curves[k].append(round(float(gg[k]), 6))

    return {
        "greeks": {k: round(float(v), 6) for k, v in g.items()},
        "spots": jlist(spots),
        "curves": curves,
    }


@app.get("/api/gbm")
def api_gbm(S0: float, mu: float, sigma: float, T_days: int,
            n_paths: int = 20, seed: int = 42):
    n_paths = min(n_paths, 200)
    n_steps = int(T_days)
    paths = quant.simulate_gbm_paths(S0, mu, sigma, T_days, n_steps, n_paths, seed)
    finals = paths[:, -1]
    return {
        "t": list(range(n_steps + 1)),
        "paths": [jlist(p) for p in paths],
        "mean_path": jlist(paths.mean(axis=0)),
        "stats": {
            "mean_final": float(finals.mean()),
            "std_final": float(finals.std()),
            "min_final": float(finals.min()),
            "max_final": float(finals.max()),
        },
    }


@app.get("/api/mc")
def api_mc(S0: float, K: float, r: float, sigma: float, T_days: int,
           n_steps: int = 63, n_paths: int = 10000,
           opt_type: str = "call", seed: int = 42):
    n_paths = min(n_paths, 200_000)
    price, stderr, _, finals, payoffs = quant.monte_carlo_price(
        S0, K, r, sigma, T_days, n_steps, n_paths, opt_type, seed)
    bs = quant.bs_price_delta_greeks(S0, K, T_days / 252, r, sigma, opt_type)
    return {
        "mc_price": float(price),
        "ci95": float(1.96 * stderr),
        "bs_price": float(bs["price"]),
        "diff": float(price - bs["price"]),
        "final_prices": jlist(finals[:20000]),
        "payoffs": jlist(payoffs[:20000]),
    }


@app.get("/api/backtest")
def api_backtest(ticker: str, start: str, window_days: int = 63,
                 k_mult: float = 1.0, r: float = 0.04, tc: float = 0.001,
                 rebalance: int = 1, opt_type: str = "call"):
    t = ticker.upper()
    window_days = int(np.clip(window_days, 20, 252))

    df = md.get_history(t, "max", "1d")
    if df.empty:
        raise HTTPException(404, f"No data for '{t}'")
    idx = df.index.tz_localize(None) if df.index.tz is not None else df.index
    try:
        start_ts = pd.to_datetime(start)
    except Exception:
        raise HTTPException(400, f"Bad start date '{start}'")
    sub = df.loc[idx >= start_ts].iloc[:window_days]
    if len(sub) < window_days:
        raise HTTPException(400, f"Only {len(sub)} sessions for {t} from {start} "
                                 f"(need {window_days})")

    prices = sub["Close"].values.astype(float)
    sub_idx = sub.index.tz_localize(None) if sub.index.tz is not None else sub.index
    dates = [ts.isoformat() for ts in sub_idx.to_pydatetime()]

    S0 = float(prices[0])
    K = round(S0 * k_mult, 2)
    T_total = window_days / 252
    n_steps = window_days - 1
    static_sigma = float(np.diff(np.log(prices)).std() * np.sqrt(252))

    roll_fc = quant.clean_sigma_series(
        quant.rolling_vol_forecast(prices, window=21), static_sigma)
    garch_fc = quant.clean_sigma_series(
        quant.garch_vol_forecast(prices, window=min(126, window_days - 5)),
        static_sigma)
    static_series = np.full(len(prices), static_sigma)

    strategies = {}
    for key, label, sigma_series in [
        ("static", "STATIC σ (NAIVE)", static_series),
        ("rolling", "ROLLING-WINDOW FORECAST", roll_fc),
        ("garch", "GARCH(1,1) FORECAST", garch_fc),
    ]:
        hedged, unhedged, hist = quant.hedge_path_variable_sigma(
            prices, K, r, sigma_series, T_total, n_steps, tc, rebalance,
            opt_type, return_history=True)
        strategies[key] = {
            "label": label,
            "hedged_pnl": round(float(hedged), 4),
            "unhedged_pnl": round(float(unhedged), 4),
            "portfolio_value": jlist(hist["portfolio_value"]),
            "sigma_series": jlist(sigma_series),
        }

    return {
        "ticker": t,
        "dates": dates,
        "prices": jlist(prices),
        "start_price": S0,
        "strike": K,
        "realized_vol": static_sigma,
        "strategies": strategies,
    }


# ------------------------------------------------------------
# frontend
# ------------------------------------------------------------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")
