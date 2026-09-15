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
