"""
market_data.py — yfinance data layer with in-process TTL caching.

Framework-agnostic: no UI imports here, safe to use from any server or script.
Covers two market universes: NASDAQ (US) and BSE (India, '.BO' suffix on Yahoo).
"""

import functools
import json
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


# ------------------------------------------------------------
# TTL cache (thread-safe, per-function)
# ------------------------------------------------------------

def ttl_cache(ttl_seconds: int):
    def deco(fn):
        cache, lock = {}, threading.Lock()

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            with lock:
                hit = cache.get(key)
                if hit and hit[0] > now:
                    return hit[1]
            val = fn(*args, **kwargs)
            with lock:
                cache[key] = (now + ttl_seconds, val)
            return val

        return wrapper
    return deco


# ------------------------------------------------------------
# Universes
# ------------------------------------------------------------

NASDAQ_INDICES = [
    ("^IXIC", "NASDAQ COMPOSITE"),
    ("^NDX", "NASDAQ 100"),
    ("^GSPC", "S&P 500"),
    ("^VIX", "VIX"),
]

NASDAQ_WATCHLIST = [
    ("AAPL", "APPLE"),
    ("MSFT", "MICROSOFT"),
    ("NVDA", "NVIDIA"),
    ("GOOGL", "ALPHABET"),
    ("AMZN", "AMAZON"),
    ("META", "META PLATFORMS"),
    ("TSLA", "TESLA"),
    ("AVGO", "BROADCOM"),
    ("NFLX", "NETFLIX"),
    ("AMD", "ADV MICRO DEVICES"),
    ("INTC", "INTEL"),
    ("QCOM", "QUALCOMM"),
]

BSE_INDICES = [
    ("^BSESN", "S&P BSE SENSEX"),
    ("^NSEI", "NIFTY 50 (NSE)"),
    ("INR=X", "USD/INR"),
]

BSE_WATCHLIST = [
    ("RELIANCE.BO", "RELIANCE INDUSTRIES"),
    ("TCS.BO", "TATA CONSULTANCY"),
    ("HDFCBANK.BO", "HDFC BANK"),
    ("INFY.BO", "INFOSYS"),
    ("ICICIBANK.BO", "ICICI BANK"),
    ("SBIN.BO", "STATE BANK OF INDIA"),
    ("BHARTIARTL.BO", "BHARTI AIRTEL"),
    ("ITC.BO", "ITC"),
    ("LT.BO", "LARSEN & TOUBRO"),
    ("HINDUNILVR.BO", "HINDUSTAN UNILEVER"),
    ("TATAMOTORS.BO", "TATA MOTORS"),
    ("WIPRO.BO", "WIPRO"),
]

ALL_NAMES = dict(NASDAQ_INDICES + NASDAQ_WATCHLIST + BSE_INDICES + BSE_WATCHLIST)


# ------------------------------------------------------------
# Customizable watchlists (persisted to watchlists.json)
# ------------------------------------------------------------

WATCHLIST_FILE = Path(__file__).parent / "watchlists.json"
_wl_lock = threading.Lock()

DEFAULT_WATCHLISTS = {
    "nasdaq": [{"ticker": t, "name": n} for t, n in NASDAQ_WATCHLIST],
    "bse": [{"ticker": t, "name": n} for t, n in BSE_WATCHLIST],
}


def load_watchlists() -> dict:
    with _wl_lock:
        if WATCHLIST_FILE.exists():
            try:
                data = json.loads(WATCHLIST_FILE.read_text())
                if all(k in data for k in DEFAULT_WATCHLISTS):
                    return data
            except Exception:
                pass
        return json.loads(json.dumps(DEFAULT_WATCHLISTS))  # deep copy


def _save_watchlists(data: dict):
    with _wl_lock:
        WATCHLIST_FILE.write_text(json.dumps(data, indent=2))


def watchlist_tickers(section: str) -> list:
    return [w["ticker"] for w in load_watchlists()[section]]


def _watchlist_names() -> dict:
    wl = load_watchlists()
    return {w["ticker"]: w["name"] for sec in wl.values() for w in sec}


def name_for(ticker: str, custom_names: dict = None) -> str:
    names = custom_names if custom_names is not None else _watchlist_names()
    return names.get(ticker) or ALL_NAMES.get(ticker, ticker)


def _resolve_symbol(section: str, raw: str):
    """
    Validate a symbol against Yahoo; for the BSE section a bare symbol like
    'RELIANCE' is tried as 'RELIANCE.BO' first. Returns (ticker, name) or
    (None, error_message).
    """
    t = raw.strip().upper()
    if not t or len(t) > 14:
        return None, "Invalid symbol."
    candidates = [t]
    if section == "bse" and "." not in t and not t.startswith("^"):
        candidates = [t + ".BO", t]
    for cand in candidates:
        try:
            tk = yf.Ticker(cand)
            last = tk.fast_info.last_price
            if last is None or (isinstance(last, float) and np.isnan(last)):
                continue
            name = cand
            try:
                info = tk.info or {}
                name = (info.get("shortName") or info.get("longName") or cand)
            except Exception:
                pass
            return cand, str(name).upper()[:24]
        except Exception:
            continue
    return None, f"'{raw.strip().upper()}' not found on Yahoo Finance."


def add_watchlist_ticker(section: str, raw: str) -> dict:
    ticker, name_or_err = _resolve_symbol(section, raw)
    if ticker is None:
        return {"ok": False, "msg": name_or_err}
    data = load_watchlists()
    if any(w["ticker"] == ticker for w in data[section]):
        return {"ok": False, "msg": f"{ticker} is already in the watchlist."}
    if len(data[section]) >= 24:
        return {"ok": False, "msg": "Watchlist is full (24 symbols max)."}
    data[section].append({"ticker": ticker, "name": name_or_err})
    _save_watchlists(data)
    return {"ok": True, "ticker": ticker, "name": name_or_err}


def remove_watchlist_ticker(section: str, ticker: str) -> dict:
    t = ticker.strip().upper()
    data = load_watchlists()
    before = len(data[section])
    data[section] = [w for w in data[section] if w["ticker"] != t]
    if len(data[section]) == before:
        return {"ok": False, "msg": f"{t} is not in the watchlist."}
    _save_watchlists(data)
    return {"ok": True, "ticker": t}


def tape_tickers() -> list:
    """Tape follows the current (customized) watchlists."""
    return (
        [t for t, _ in NASDAQ_INDICES]
        + watchlist_tickers("nasdaq")[:6]
        + [t for t, _ in BSE_INDICES[:2]]
        + watchlist_tickers("bse")[:5]
    )

RANGE_MAP = {
    "1D": ("1d", "5m"),
    "5D": ("5d", "15m"),
    "1M": ("1mo", "1h"),
    "6M": ("6mo", "1d"),
    "YTD": ("ytd", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1wk"),
    "MAX": ("max", "1mo"),
}


# ------------------------------------------------------------
# Data fetchers
# ------------------------------------------------------------

@ttl_cache(90)
def get_quotes(tickers: tuple) -> list:
    """Last price + daily change for a batch of tickers. Returns list of dicts."""
    raw = yf.download(list(tickers), period="5d", interval="1d",
                      progress=False, auto_adjust=True, group_by="ticker",
                      threads=True)
    custom_names = _watchlist_names()
    rows = []
    for t in tickers:
        row = dict(ticker=t, name=name_for(t, custom_names),
                   last=None, chg=None, chg_pct=None)
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                closes = raw[t]["Close"].dropna()
            else:
                closes = raw["Close"].dropna()
            last = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) > 1 else last
            row.update(last=round(last, 4), chg=round(last - prev, 4),
                       chg_pct=round((last / prev - 1) * 100, 4) if prev else 0.0)
        except Exception:
            pass
        rows.append(row)
    return rows


def _fetch_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period, interval=interval,
                                   auto_adjust=True)
    if df.empty:
        return df
    return df.dropna(subset=["Close"])


def _fetch_smart(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """
    Like _fetch_history, but works around a Yahoo quirk where period='1d'
    returns nothing for some exchanges (e.g. Indian symbols after the session
    rolls over): fall back to 5 days of intraday bars and keep the last session.
    """
    df = _fetch_history(ticker, period, interval)
    if df.empty and period == "1d":
        df5 = _fetch_history(ticker, "5d", interval)
        if not df5.empty:
            last_day = df5.index[-1].date()
            df = df5[df5.index.date == last_day]
    return df


@ttl_cache(180)
def get_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    OHLCV history. Yahoo's BSE feed ('.BO') only serves the latest quote and
    returns a single row for historical ranges, so for '.BO' symbols we fall
    back to the same company's NSE listing ('.NS') — dual-listed, prices are
    virtually identical.
    """
    df = _fetch_smart(ticker, period, interval)
    if len(df) <= 3 and ticker.upper().endswith(".BO"):
        alt = ticker[:-3] + ".NS"
        df_alt = _fetch_smart(alt, period, interval)
        if len(df_alt) > len(df):
            return df_alt
    return df


@ttl_cache(3600)
def get_profile(ticker: str) -> dict:
    tk = yf.Ticker(ticker)
    info = {}
    try:
        info = tk.info or {}
    except Exception:
        pass
    if not info.get("regularMarketPrice"):
        try:
            fi = tk.fast_info
            info.setdefault("regularMarketPrice", fi.last_price)
            info.setdefault("marketCap", fi.market_cap)
            info.setdefault("fiftyTwoWeekHigh", fi.year_high)
            info.setdefault("fiftyTwoWeekLow", fi.year_low)
        except Exception:
            pass
    return info


@ttl_cache(600)
def get_news(ticker: str, limit: int = 10) -> list:
    """Normalize yfinance news across old/new schema versions."""
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        return []
    out = []
    for it in items[:limit]:
        c = it.get("content", it)  # new schema nests under 'content'
        title = c.get("title")
        if not title:
            continue
        link = ""
        if isinstance(c.get("canonicalUrl"), dict):
            link = c["canonicalUrl"].get("url", "")
        link = link or it.get("link", "")
        provider = ""
        if isinstance(c.get("provider"), dict):
            provider = c["provider"].get("displayName", "")
        provider = provider or it.get("publisher", "")
        when = c.get("pubDate") or ""
        out.append(dict(title=title, link=link, provider=provider,
                        when=str(when)[:16].replace("T", " ")))
    return out


def fmt_big(x):
    """1234567890 -> '1.23B'"""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    for unit, div in [("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)]:
        if abs(x) >= div:
            return f"{x / div:.2f}{unit}"
    return f"{x:,.2f}"
