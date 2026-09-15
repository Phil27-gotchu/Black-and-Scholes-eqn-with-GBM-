"""API tests that do not call Yahoo Finance.

Live-data endpoints (markets, tape, history, profile, news, vol, backtest)
are exercised against mocks so CI stays deterministic and offline.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app as terminal
import quant


@pytest.fixture
def client():
    return TestClient(terminal.app)


def _ohlc(n=80, start="2023-03-01", s0=100.0, seed=0):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0, 0.015, n)
    close = s0 * np.exp(np.cumsum(rets))
    idx = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame({
        "Open": close, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Volume": np.full(n, 1_000_000.0),
    }, index=idx)


# ------------------------------------------------------------
# frontend + validation
# ------------------------------------------------------------

def test_index_serves_terminal(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "TERMINAL" in r.text
    assert "B&amp;S" in r.text


def test_docs_available(client):
    assert client.get("/docs").status_code == 200


def test_history_bad_range(client):
    r = client.get("/api/history", params={"ticker": "AAPL", "range": "BOGUS"})
    assert r.status_code == 400


def test_ov_bad_type(client):
    r = client.get("/api/ov", params={
        "S": 100, "K": 100, "T_days": 63, "r": 0.04, "sigma": 0.25,
        "opt_type": "banana",
    })
    assert r.status_code == 400


def test_watchlist_bad_section(client):
    r = client.post("/api/watchlist/add", params={"section": "lse", "ticker": "AAPL"})
    assert r.status_code == 400
    r = client.post("/api/watchlist/remove", params={"section": "lse", "ticker": "AAPL"})
    assert r.status_code == 400


# ------------------------------------------------------------
# Black-Scholes / GBM / Monte Carlo endpoints
# ------------------------------------------------------------

def test_ov_call_matches_engine(client):
    r = client.get("/api/ov", params={
        "S": 100, "K": 100, "T_days": 63, "r": 0.04, "sigma": 0.25,
        "opt_type": "call",
    })
    assert r.status_code == 200
    body = r.json()
    engine = quant.bs_price_delta_greeks(100, 100, 63 / 252, 0.04, 0.25, "call")
    assert abs(body["greeks"]["price"] - engine["price"]) < 1e-5
    assert abs(body["greeks"]["delta"] - engine["delta"]) < 1e-5
    assert len(body["spots"]) == 120
    assert len(body["curves"]["price"]) == 120


def test_ov_put_call_parity(client):
    params = {"S": 100, "K": 100, "T_days": 63, "r": 0.04, "sigma": 0.25}
    call = client.get("/api/ov", params={**params, "opt_type": "call"}).json()
    put = client.get("/api/ov", params={**params, "opt_type": "put"}).json()
    residual = (call["greeks"]["price"] - put["greeks"]["price"]
                - (100 - 100 * np.exp(-0.04 * 63 / 252)))
    assert abs(residual) < 1e-4


def test_gbm_clamps_paths_and_is_seeded(client):
    r = client.get("/api/gbm", params={
        "S0": 100, "mu": 0.08, "sigma": 0.25, "T_days": 21,
        "n_paths": 500, "seed": 1,
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["paths"]) == 200
    assert body["stats"]["min_final"] > 0
    again = client.get("/api/gbm", params={
        "S0": 100, "mu": 0.08, "sigma": 0.25, "T_days": 21,
        "n_paths": 500, "seed": 1,
    }).json()
    assert body["paths"][0] == again["paths"][0]


def test_mc_converges_to_black_scholes(client):
    r = client.get("/api/mc", params={
        "S0": 100, "K": 100, "r": 0.04, "sigma": 0.25, "T_days": 63,
        "n_steps": 63, "n_paths": 40000, "opt_type": "call", "seed": 2,
    })
    assert r.status_code == 200
    body = r.json()
    assert abs(body["diff"]) < 3 * body["ci95"] / 1.96 + 0.08


# ------------------------------------------------------------
# mocked live-data endpoints
# ------------------------------------------------------------

def test_history_404_when_empty(client, monkeypatch):
    monkeypatch.setattr(terminal.md, "get_history", lambda *a, **k: pd.DataFrame())
    r = client.get("/api/history", params={"ticker": "FAKE", "range": "1Y"})
    assert r.status_code == 404


def test_history_ok_with_synthetic_bars(client, monkeypatch):
    monkeypatch.setattr(terminal.md, "get_history", lambda *a, **k: _ohlc())
    r = client.get("/api/history", params={"ticker": "AAPL", "range": "6M"})
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert len(body["c"]) == 80


def test_profile_404_when_empty(client, monkeypatch):
    monkeypatch.setattr(terminal.md, "get_profile", lambda *a, **k: {})
    r = client.get("/api/profile", params={"ticker": "NOPE"})
    assert r.status_code == 404


def test_profile_ok(client, monkeypatch):
    monkeypatch.setattr(terminal.md, "get_profile", lambda *a, **k: {
        "longName": "Apple Inc.", "regularMarketPrice": 180.0,
        "marketCap": 2.8e12, "trailingPE": 28.0,
    })
    r = client.get("/api/profile", params={"ticker": "aapl"})
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["name"] == "Apple Inc."
    assert body["last"] == 180.0


def test_vol_404_short_history(client, monkeypatch):
    monkeypatch.setattr(terminal.md, "get_history", lambda *a, **k: _ohlc(n=20))
    r = client.get("/api/vol", params={"ticker": "AAPL", "garch": False})
    assert r.status_code == 404


def test_vol_ok_without_garch(client, monkeypatch):
    monkeypatch.setattr(terminal.md, "get_history", lambda *a, **k: _ohlc(n=200))
    r = client.get("/api/vol", params={"ticker": "AAPL", "garch": False})
    assert r.status_code == 200
    body = r.json()
    assert body["garch"] is None
    assert 0.01 < body["metrics"]["realized_21d"] < 3


def test_backtest_404_empty(client, monkeypatch):
    monkeypatch.setattr(terminal.md, "get_history", lambda *a, **k: pd.DataFrame())
    r = client.get("/api/backtest", params={"ticker": "NOPE", "start": "2023-03-01"})
    assert r.status_code == 404


def test_backtest_400_future_window(client, monkeypatch):
    monkeypatch.setattr(terminal.md, "get_history", lambda *a, **k: _ohlc(n=40))
    r = client.get("/api/backtest", params={
        "ticker": "JPM", "start": "2023-03-01", "window_days": 63,
    })
    assert r.status_code == 400


def test_backtest_synthetic_path(client, monkeypatch):
    monkeypatch.setattr(terminal.md, "get_history", lambda *a, **k: _ohlc(n=120))
    r = client.get("/api/backtest", params={
        "ticker": "jpm", "start": "2023-03-01", "window_days": 63,
        "opt_type": "call",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "JPM"
    assert set(body["strategies"]) == {"static", "rolling", "garch"}
    assert len(body["dates"]) == len(body["prices"]) == 63


def test_markets_uses_quotes_mock(client, monkeypatch):
    def fake_quotes(tickers):
        return [{"ticker": t, "name": t, "last": 1.0, "chg": 0.0, "chg_pct": 0.0}
                for t in tickers]

    monkeypatch.setattr(terminal.md, "get_quotes", fake_quotes)
    monkeypatch.setattr(terminal.md, "watchlist_tickers",
                        lambda section: ["AAPL"] if section == "nasdaq" else ["RELIANCE.BO"])
    r = client.get("/api/markets")
    assert r.status_code == 200
    body = r.json()
    assert body["nasdaq"]["benchmark"] == "^IXIC"
    assert body["bse"]["benchmark"] == "^BSESN"
    assert body["nasdaq"]["status"]["label"] in ("OPEN", "CLOSED")
    assert body["nasdaq"]["watchlist"][0]["ticker"] == "AAPL"
