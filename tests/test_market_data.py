"""Helpers in market_data.py that do not need Yahoo Finance."""

import json

import market_data as md


def test_fmt_big():
    assert md.fmt_big(1.23e12) == "1.23T"
    assert md.fmt_big(2.5e9) == "2.50B"
    assert md.fmt_big(4.2e6) == "4.20M"
    assert md.fmt_big(800) == "800.00"
    assert md.fmt_big(None) is None
    assert md.fmt_big("nope") is None


def test_watchlist_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "watchlists.json"
    monkeypatch.setattr(md, "WATCHLIST_FILE", path)
    data = md.load_watchlists()
    assert "nasdaq" in data and "bse" in data
    assert any(w["ticker"] == "AAPL" for w in data["nasdaq"])

    data["nasdaq"].append({"ticker": "SHOP", "name": "SHOPIFY"})
    md._save_watchlists(data)
    reloaded = json.loads(path.read_text())
    assert any(w["ticker"] == "SHOP" for w in reloaded["nasdaq"])

    result = md.remove_watchlist_ticker("nasdaq", "SHOP")
    assert result["ok"] is True
    assert all(w["ticker"] != "SHOP" for w in md.load_watchlists()["nasdaq"])


def test_remove_missing_ticker(tmp_path, monkeypatch):
    monkeypatch.setattr(md, "WATCHLIST_FILE", tmp_path / "watchlists.json")
    result = md.remove_watchlist_ticker("nasdaq", "NOTHERE")
    assert result["ok"] is False


def test_tape_tickers_follow_watchlist(tmp_path, monkeypatch):
    monkeypatch.setattr(md, "WATCHLIST_FILE", tmp_path / "watchlists.json")
    tape = md.tape_tickers()
    assert "^IXIC" in tape
    assert "^BSESN" in tape
    assert "AAPL" in tape


def test_option_symbol_mapping():
    assert md.resolve_option_ticker("^GSPC") == "SPY"
    assert md.option_chain_symbol("RELIANCE.BO") == "RELIANCE.NS"
    assert md.option_chain_symbol("AAPL") == "AAPL"


def test_filter_search_keeps_us_equity_drops_futures():
    quotes = [
        {"symbol": "AAPL", "shortname": "Apple Inc.", "quoteType": "EQUITY",
         "exchDisp": "NASDAQ", "exchange": "NMS"},
        {"symbol": "SAAPL=F", "shortname": "Apple futures", "quoteType": "FUTURE",
         "exchDisp": "Chicago Mercantile Exchange", "exchange": "CME"},
        {"symbol": "AAPL.TO", "shortname": "APPLE CDR", "quoteType": "EQUITY",
         "exchDisp": "Toronto", "exchange": "TOR"},
    ]
    tickers = [r["ticker"] for r in md._filter_search_quotes(quotes, "nasdaq")]
    assert tickers == ["AAPL"]


def test_filter_search_maps_nse_to_bo():
    quotes = [
        {"symbol": "RELIANCE.NS", "shortname": "Reliance Industries",
         "quoteType": "EQUITY", "exchDisp": "NSE", "exchange": "NSI"},
    ]
    rows = md._filter_search_quotes(quotes, "bse")
    assert rows[0]["ticker"] == "RELIANCE.BO"


def test_local_symbol_search_by_name():
    hits = md._local_symbol_search("apple", "nasdaq")
    assert any(h["ticker"] == "AAPL" for h in hits)
    hits_in = md._local_symbol_search("infosys", "bse")
    assert any(h["ticker"] == "INFY.BO" for h in hits_in)


def test_local_symbol_search_prefix_ranks_ticker():
    hits = md._local_symbol_search("n", "nasdaq")
    tickers = [h["ticker"] for h in hits]
    assert tickers[0] in {"NFLX", "NVDA"}
    assert "NVDA" in tickers
    assert "NFLX" in tickers
    assert "AMZN" not in tickers


def test_ttl_cache_evicts_beyond_maxsize():
    calls = []

    @md.ttl_cache(60, maxsize=3)
    def sq(x):
        calls.append(x)
        return x * x

    for x in range(10):
        sq(x)
    assert len(sq.cache) == 3
    sq(9)
    assert calls.count(9) == 1
    sq(0)
    assert calls.count(0) == 2


def test_ttl_cache_expires(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(md.time, "time", lambda: clock[0])
    calls = []

    @md.ttl_cache(10)
    def f(x):
        calls.append(x)
        return x

    f(1)
    f(1)
    clock[0] += 11
    f(1)
    assert calls == [1, 1]


def test_symbol_search_hits_yahoo_once_for_both_markets(monkeypatch):
    import yfinance

    seen = []

    class FakeSearch:
        def __init__(self, query, **kw):
            seen.append((query, kw.get("timeout")))
            self.quotes = [{"symbol": "ZQXA", "shortname": "ZQX ALPHA",
                            "quoteType": "EQUITY", "exchange": "NMS"}]

    monkeypatch.setattr(yfinance, "Search", FakeSearch)
    hits = md.search_symbols_all("zqx")
    assert [q for q, _ in seen] == ["zqx"]
    assert seen[0][1] == md.YAHOO_SEARCH_TIMEOUT
    assert any(h["ticker"] == "ZQXA" for h in hits)


def test_parallel_map_keeps_order():
    import time as _t

    def slow(x):
        _t.sleep(0.02 * (5 - x))
        return x * 10

    assert md.parallel_map(slow, range(5)) == [0, 10, 20, 30, 40]


def test_search_symbols_all_covers_both_markets():
    hits = md.search_symbols_all("n")
    tickers = [h["ticker"] for h in hits]
    assert "NVDA" in tickers
    assert any(h["name"] == "NVIDIA" for h in hits if h["ticker"] == "NVDA")


def test_tag_tickers_by_name_and_symbol():
    assert "AAPL" in md.tag_tickers("Apple unveils cheaper iPhone in India")
    assert "NVDA" in md.tag_tickers("NVIDIA guidance lifts chip stocks")
    assert "INFY.BO" in md.tag_tickers("Infosys raises full-year outlook")
    assert "RELIANCE.BO" in md.tag_tickers("Reliance Industries to add refining capacity")
    assert "AAPL" in md.tag_tickers("AAPL option volume spikes")


def test_filter_news_keyword_and_scope():
    items = [
        {"title": "Apple beats estimates", "provider": "Reuters", "tickers": ["AAPL"],
         "source": "AAPL", "primary": "AAPL"},
        {"title": "RBI holds rates, Sensex steady", "provider": "ET", "tickers": ["^BSESN"],
         "source": "^BSESN", "primary": "^BSESN"},
        {"title": "Infosys wins deal", "provider": "Mint", "tickers": ["INFY.BO"],
         "source": "INFY.BO", "primary": "INFY.BO"},
    ]
    fed = md.filter_news_items(items, query="apple")
    assert len(fed) == 1 and fed[0]["primary"] == "AAPL"
    india = md.filter_news_items(items, scope="india")
    assert {x["primary"] for x in india} == {"^BSESN", "INFY.BO"}
    mega = md.filter_news_items(items, scope="mega")
    assert [x["primary"] for x in mega] == ["AAPL"]
    nvda = md.filter_news_items(items, ticker="NVDA")
    assert nvda == []
    apple = md.filter_news_items(items, ticker="AAPL")
    assert len(apple) == 1
