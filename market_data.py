"""
market_data.py — yfinance data layer with in-process TTL caching.

Framework-agnostic: no UI imports here, safe to use from any server or script.
Covers two market universes: NASDAQ (US) and BSE (India, '.BO' suffix on Yahoo).
"""

import functools
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


# ------------------------------------------------------------
# TTL cache (thread-safe, per-function)
# ------------------------------------------------------------

def ttl_cache(ttl_seconds: int, maxsize: int = 256):
    """Expired entries are purged on insert; beyond `maxsize` the oldest go first."""
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
                cache.pop(key, None)
                cache[key] = (now + ttl_seconds, val)
                if len(cache) > maxsize:
                    for k in [k for k, (exp, _) in cache.items() if exp <= now]:
                        del cache[k]
                    while len(cache) > maxsize:
                        del cache[next(iter(cache))]
            return val

        wrapper.cache = cache
        return wrapper
    return deco


def parallel_map(fn, items, max_workers: int = 8) -> list:
    """Run blocking Yahoo calls concurrently; results keep input order."""
    items = list(items)
    if len(items) <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as pool:
        return list(pool.map(fn, items))


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

MEGA_NEWS_TICKERS = [t for t, _ in NASDAQ_WATCHLIST] + ["SPY", "QQQ"]
INDIA_NEWS_TICKERS = [t for t, _ in BSE_WATCHLIST] + ["^BSESN", "^NSEI"]

_NEWS_EXTRA_ALIASES = [
    ("apple", "AAPL"), ("iphone", "AAPL"), ("nvidia", "NVDA"),
    ("microsoft", "MSFT"), ("google", "GOOGL"), ("alphabet", "GOOGL"),
    ("amazon", "AMZN"), ("facebook", "META"), ("meta platforms", "META"),
    ("tesla", "TSLA"), ("netflix", "NFLX"), ("broadcom", "AVGO"),
    ("intel", "INTC"), ("qualcomm", "QCOM"),
    ("reliance", "RELIANCE.BO"), ("infosys", "INFY.BO"),
    ("hdfc bank", "HDFCBANK.BO"), ("icici", "ICICIBANK.BO"),
    ("state bank of india", "SBIN.BO"), ("sbi", "SBIN.BO"),
    ("bharti", "BHARTIARTL.BO"), ("airtel", "BHARTIARTL.BO"),
    ("tata motors", "TATAMOTORS.BO"), ("tata consultancy", "TCS.BO"),
    ("hindustan unilever", "HINDUNILVR.BO"), ("larsen", "LT.BO"),
    ("sensex", "^BSESN"), ("nifty", "^NSEI"), ("nasdaq", "^IXIC"),
    ("s&p 500", "^GSPC"), ("s&p500", "^GSPC"),
]


def _news_alias_table():
    """Longer phrases first so 'TATA MOTORS' wins over a generic 'TATA'."""
    rows = []
    for t, n in NASDAQ_WATCHLIST + NASDAQ_INDICES + BSE_WATCHLIST + BSE_INDICES:
        rows.append((t.lower(), t))
        rows.append((n.lower(), t))
        bare = t.lower().replace(".bo", "").replace(".ns", "").lstrip("^")
        if len(bare) >= 2:
            rows.append((bare, t))
    rows.extend(_NEWS_EXTRA_ALIASES)
    first = {}
    for t, n in NASDAQ_WATCHLIST + BSE_WATCHLIST:
        w = n.split()[0].lower()
        if len(w) >= 4:
            first.setdefault(w, set()).add(t)
    for w, tickers in first.items():
        if len(tickers) == 1:
            rows.append((w, next(iter(tickers))))
    # unique by alias, last extra aliases can override catalog
    by_alias = {}
    for alias, ticker in rows:
        by_alias[alias] = ticker
    return sorted(by_alias.items(), key=lambda kv: len(kv[0]), reverse=True)


_NEWS_ALIASES = _news_alias_table()


def tag_tickers(title: str) -> list:
    """Tickers mentioned in a headline (name or symbol)."""
    text = f" {title.lower()} "
    found, seen = [], set()
    for alias, ticker in _NEWS_ALIASES:
        if ticker in seen:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text):
            seen.add(ticker)
            found.append(ticker)
    return found


def _is_india_ticker(t: str) -> bool:
    t = (t or "").upper()
    return t.endswith(".BO") or t.endswith(".NS") or t in {"^BSESN", "^NSEI", "INR=X"}


def _is_mega_ticker(t: str) -> bool:
    return (t or "").upper() in {x.upper() for x in MEGA_NEWS_TICKERS} | {
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "SPY", "QQQ",
    }


def filter_news_items(items, query="", ticker="", scope="all"):
    q = (query or "").strip().lower()
    want = (ticker or "").strip().upper()
    out = []
    for it in items:
        title = it.get("title") or ""
        blob = f"{title} {it.get('provider') or ''}".lower()
        if q and q not in blob:
            continue
        tags = it.get("tickers") or []
        src = (it.get("source") or "").upper()
        primary = (it.get("primary") or "").upper()
        if want and want not in {x.upper() for x in tags} and want != src:
            continue
        if scope == "india":
            universe = tags + [src, primary]
            if not any(_is_india_ticker(x) for x in universe):
                continue
        elif scope == "mega":
            universe = tags + [src, primary]
            if not any(_is_mega_ticker(x) for x in universe):
                continue
        elif scope == "name" and want:
            if want not in {x.upper() for x in tags} and want != src:
                continue
        out.append(it)
    return out


def _decorate_news_item(item: dict, source: str) -> dict:
    tags = tag_tickers(item.get("title") or "")
    primary = tags[0] if tags else source
    return {
        **item,
        "source": source,
        "tickers": tags,
        "primary": primary,
    }


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


US_EXCHANGES = {
    "NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "BTS", "NYSE", "NASDAQ",
    "NYSEARCA", "NYSE ARCA", "AMEX", "BATS", "CBOE BZX", "NYSE AMERICAN",
}
IN_EXCHANGES = {"NSI", "BSE", "NSE", "BOM", "BOMBAY"}


def _catalog(section: str) -> list:
    if section == "nasdaq":
        pairs = NASDAQ_INDICES + NASDAQ_WATCHLIST
    else:
        pairs = BSE_INDICES + BSE_WATCHLIST
    extra = [(w["ticker"], w["name"]) for w in load_watchlists().get(section, [])]
    seen, out = set(), []
    for t, n in list(pairs) + extra:
        if t not in seen:
            seen.add(t)
            out.append((t, n))
    return out


def _rank_symbol_hit(query: str, ticker: str, name: str):
    """0 = ticker prefix (N → NVDA), 1 = name prefix, 2 = substring."""
    q = query.strip().lower()
    t = ticker.lower()
    n = (name or "").lower()
    bare = t.replace(".bo", "").replace(".ns", "").lstrip("^")
    if t.startswith(q) or bare.startswith(q):
        return 0
    if n.startswith(q):
        return 1
    if q in t or q in n or q in bare:
        return 2
    return None


def _local_symbol_search(query: str, section: str, limit: int = 8) -> list:
    q = query.strip().lower()
    if not q:
        return []
    hits = []
    for ticker, name in _catalog(section):
        rank = _rank_symbol_hit(q, ticker, name)
        if rank is None:
            continue
        if len(q) == 1 and rank > 1:
            continue
        hits.append((rank, ticker, {
            "ticker": ticker,
            "name": name,
            "exchange": "NASDAQ" if section == "nasdaq" else "BSE / NSE",
            "type": "EQUITY",
        }))
    hits.sort(key=lambda x: (x[0], x[1]))
    return [h[2] for h in hits[:limit]]


def _filter_search_quotes(quotes: list, section: str) -> list:
    """Keep cash equities/ETFs on the section's home market."""
    out, seen = [], set()
    for q in quotes or []:
        symbol = (q.get("symbol") or "").upper()
        qtype = (q.get("quoteType") or "").upper()
        exch = (q.get("exchange") or "").upper()
        disp = (q.get("exchDisp") or "").upper()
        name = q.get("shortname") or q.get("longname") or symbol
        if not symbol or qtype in {"FUTURE", "OPTION", "CRYPTOCURRENCY", "MUTUALFUND"}:
            continue
        if qtype not in {"EQUITY", "ETF", "INDEX", "ECNQUOTE"}:
            continue
        if section == "nasdaq":
            if "." in symbol or symbol.endswith("=F"):
                continue
            if exch not in US_EXCHANGES and disp not in US_EXCHANGES:
                continue
        else:
            indian = symbol.endswith(".NS") or symbol.endswith(".BO")
            if not indian and exch not in IN_EXCHANGES and disp not in IN_EXCHANGES:
                continue
            if symbol.endswith(".NS"):
                symbol = symbol[:-3] + ".BO"
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append({
            "ticker": symbol,
            "name": str(name).upper()[:40],
            "exchange": q.get("exchDisp") or q.get("exchange") or "",
            "type": qtype,
        })
    return out


YAHOO_SEARCH_TIMEOUT = 3


@ttl_cache(60)
def _yahoo_search_quotes(query: str) -> list:
    """One Yahoo Search per query, shared by both sections."""
    try:
        from yfinance import Search
        result = Search(query, max_results=12, news_count=0,
                        timeout=YAHOO_SEARCH_TIMEOUT, raise_errors=False)
        return list(result.quotes or [])
    except Exception:
        return []


@ttl_cache(60)
def search_symbols(query: str, section: str = "nasdaq", limit: int = 8) -> list:
    """Autocomplete: local catalog plus Yahoo Finance search by name or ticker."""
    q = (query or "").strip()
    if len(q) < 1 or section not in ("nasdaq", "bse"):
        return []
    local = _local_symbol_search(q, section, limit=limit)
    remote = []
    if len(q) >= 2:
        remote = _filter_search_quotes(_yahoo_search_quotes(q.lower()), section)
    merged, seen = [], set()
    for row in local + remote:
        if row["ticker"] in seen:
            continue
        seen.add(row["ticker"])
        merged.append(row)
        if len(merged) >= limit:
            break
    return merged


def search_symbols_all(query: str, limit: int = 12) -> list:
    """NASDAQ + BSE autocomplete. Prefix matches first: N → NVDA [NVIDIA]."""
    q = (query or "").strip()
    if len(q) < 1:
        return []
    seen, ranked = set(), []
    for section in ("nasdaq", "bse"):
        for row in search_symbols(q, section=section, limit=limit):
            t = row["ticker"]
            if t in seen:
                continue
            seen.add(t)
            rank = _rank_symbol_hit(q, t, row.get("name") or "")
            if rank is None:
                continue
            if len(q) == 1 and rank > 1:
                continue
            ranked.append((rank, t, row))
    ranked.sort(key=lambda x: (x[0], x[1]))
    return [r[2] for r in ranked[:limit]]


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
    for it in items[: max(limit * 2, 12)]:
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
        raw = dict(title=title, link=link, provider=provider,
                   when=str(when)[:16].replace("T", " "))
        out.append(_decorate_news_item(raw, ticker.upper()))
        if len(out) >= limit:
            break
    return out


def get_news_feed(scope: str = "all", query: str = "", ticker: str = "",
                  limit: int = 40) -> list:
    """Pull a cross-name headline tape, tag names, then filter like a router."""
    scope = (scope or "all").lower()
    if scope not in ("all", "india", "mega", "name"):
        scope = "all"
    focus = (ticker or "").strip().upper()
    if scope == "mega":
        sources = list(MEGA_NEWS_TICKERS)
    elif scope == "india":
        sources = list(INDIA_NEWS_TICKERS)
    elif scope == "name":
        sources = [focus] if focus else list(MEGA_NEWS_TICKERS[:4])
    else:
        sources = MEGA_NEWS_TICKERS[:8] + INDIA_NEWS_TICKERS[:8]
    if focus and focus not in sources:
        sources = [focus] + sources

    bundled, seen = [], set()
    per = 8 if scope == "name" else 6
    for batch in parallel_map(lambda s: get_news(s, limit=per), sources):
        for item in batch:
            key = (item.get("title") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            bundled.append(item)

    if scope == "name" and focus:
        filtered = filter_news_items(bundled, query=query, ticker=focus, scope="name")
    else:
        filtered = filter_news_items(bundled, query=query, ticker=focus, scope=scope)
    return filtered[:limit]


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


OPTION_UNDERLYING = {
    "^GSPC": "SPY",
    "^DJI": "DIA",
    "^IXIC": "QQQ",
    "^NDX": "QQQ",
    "^RUT": "IWM",
}


def resolve_option_ticker(ticker: str) -> str:
    """Map indices to a liquid ETF options chain; try NSE for .BO names."""
    t = ticker.strip().upper()
    return OPTION_UNDERLYING.get(t, t)


def option_chain_symbol(ticker: str) -> str:
    """Yahoo listed-options symbol. Index futures map to ETFs; BSE names use NSE."""
    t = resolve_option_ticker(ticker)
    if t.endswith(".BO"):
        return t[:-3] + ".NS"
    return t


@ttl_cache(300)
def get_option_expiries(ticker: str) -> tuple:
    symbol = option_chain_symbol(ticker)
    try:
        return tuple(yf.Ticker(symbol).options or ())
    except Exception:
        return ()


@ttl_cache(300)
def get_option_chain(ticker: str, expiry: str) -> dict:
    """Calls/puts as JSON-friendly dicts for one expiry."""
    symbol = option_chain_symbol(ticker)
    try:
        chain = yf.Ticker(symbol).option_chain(expiry)
    except Exception:
        return {"calls": [], "puts": [], "symbol": symbol}

    def pack(df):
        out = []
        if df is None or df.empty:
            return out
        for _, row in df.iterrows():
            yiv = row["impliedVolatility"] if "impliedVolatility" in df.columns else None
            out.append({
                "strike": float(row["strike"]) if pd.notna(row.get("strike")) else None,
                "bid": float(row["bid"]) if pd.notna(row.get("bid")) else 0.0,
                "ask": float(row["ask"]) if pd.notna(row.get("ask")) else 0.0,
                "last": float(row["lastPrice"]) if pd.notna(row.get("lastPrice")) else 0.0,
                "volume": int(row["volume"]) if pd.notna(row.get("volume")) else 0,
                "oi": int(row["openInterest"]) if pd.notna(row.get("openInterest")) else 0,
                "yahoo_iv": float(yiv) if yiv is not None and pd.notna(yiv) else None,
            })
        return out

    return {"calls": pack(chain.calls), "puts": pack(chain.puts), "symbol": symbol}


def get_spot(ticker: str):
    h = get_history(ticker, "5d", "1d")
    if h.empty:
        alt = option_chain_symbol(ticker)
        if alt != ticker.upper():
            h = get_history(alt, "5d", "1d")
    if h.empty:
        return None
    return float(h["Close"].iloc[-1])
