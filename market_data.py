"""
market_data.py — yfinance data layer with in-process TTL caching.

Framework-agnostic: no UI imports here, safe to use from any server or script.
Covers two market universes: NASDAQ (US) and BSE (India, '.BO' suffix on Yahoo).
"""

import functools
import threading
import time

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

TAPE_TICKERS = (
    [t for t, _ in NASDAQ_INDICES]
    + [t for t, _ in NASDAQ_WATCHLIST[:6]]
    + [t for t, _ in BSE_INDICES[:2]]
    + [t for t, _ in BSE_WATCHLIST[:5]]
)

ALL_NAMES = dict(NASDAQ_INDICES + NASDAQ_WATCHLIST + BSE_INDICES + BSE_WATCHLIST)

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
    rows = []
    for t in tickers:
        row = dict(ticker=t, name=ALL_NAMES.get(t, t),
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


@ttl_cache(180)
def get_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    OHLCV history. Yahoo's BSE feed ('.BO') only serves the latest quote and
    returns a single row for historical ranges, so for '.BO' symbols we fall
    back to the same company's NSE listing ('.NS') — dual-listed, prices are
    virtually identical.
    """
    df = _fetch_history(ticker, period, interval)
    if len(df) <= 3 and ticker.upper().endswith(".BO"):
        alt = ticker[:-3] + ".NS"
        df_alt = _fetch_history(alt, period, interval)
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
