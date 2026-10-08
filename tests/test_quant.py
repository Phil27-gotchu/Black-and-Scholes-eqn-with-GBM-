"""Financial invariants for the pricing, simulation, and hedge engines.

These are the checks that caught the missing cash-interest bug in the
delta-hedge engine. They need no network and must stay green in CI.
"""

import numpy as np
import pytest

import quant

S, K, T, R, SIG = 100.0, 100.0, 0.25, 0.04, 0.25


@pytest.fixture(scope="module")
def call():
    return quant.bs_price_delta_greeks(S, K, T, R, SIG, "call")


@pytest.fixture(scope="module")
def put():
    return quant.bs_price_delta_greeks(S, K, T, R, SIG, "put")


# ------------------------------------------------------------
# Black-Scholes
# ------------------------------------------------------------

def test_put_call_parity(call, put):
    residual = call["price"] - put["price"] - (S - K * np.exp(-R * T))
    assert abs(residual) < 1e-10


def test_call_delta_in_unit_interval(call):
    assert 0 < call["delta"] < 1


def test_put_delta_in_minus_one_zero(put):
    assert -1 < put["delta"] < 0


def test_delta_parity(call, put):
    assert abs(call["delta"] - put["delta"] - 1) < 1e-10


def test_gamma_equal_call_put(call, put):
    assert abs(call["gamma"] - put["gamma"]) < 1e-12


def test_vega_equal_call_put(call, put):
    assert abs(call["vega"] - put["vega"]) < 1e-12


def test_atm_call_theta_negative(call):
    assert call["theta"] < 0


def test_deep_itm_call_delta_near_one():
    g = quant.bs_price_delta_greeks(200, 100, T, R, SIG, "call")
    assert g["delta"] > 0.999


def test_deep_otm_call_delta_near_zero():
    g = quant.bs_price_delta_greeks(40, 100, T, R, SIG, "call")
    assert g["delta"] < 0.001


def test_expiry_call_equals_intrinsic():
    g = quant.bs_price_delta_greeks(110, 100, 0, R, SIG, "call")
    assert g["price"] == 10
    assert g["delta"] == 1.0


def test_analytic_delta_matches_finite_difference(call):
    h = 1e-4
    up = quant.bs_price_delta_greeks(S + h, K, T, R, SIG, "call")["price"]
    dn = quant.bs_price_delta_greeks(S - h, K, T, R, SIG, "call")["price"]
    numeric = (up - dn) / (2 * h)
    assert abs(numeric - call["delta"]) < 1e-6


# ------------------------------------------------------------
# Implied vol (Newton-Raphson)
# ------------------------------------------------------------

def test_implied_vol_roundtrip_atm_call(call):
    iv = quant.implied_vol(call["price"], S, K, T, R, "call", sigma0=0.1)
    assert abs(iv - SIG) < 1e-6


def test_implied_vol_roundtrip_atm_put(put):
    iv = quant.implied_vol(put["price"], S, K, T, R, "put", sigma0=0.4)
    assert abs(iv - SIG) < 1e-6


def test_implied_vol_roundtrip_otm_call():
    sig = 0.35
    g = quant.bs_price_delta_greeks(100, 110, T, R, sig, "call")
    iv = quant.implied_vol(g["price"], 100, 110, T, R, "call", sigma0=0.2)
    assert abs(iv - sig) < 1e-5


def test_implied_vol_below_intrinsic_is_nan():
    assert np.isnan(quant.implied_vol(1.0, 110, 100, T, R, "call"))


def test_implied_vol_expired_is_nan():
    assert np.isnan(quant.implied_vol(5.0, 100, 100, 0.0, R, "call"))


def test_option_mid_prefers_bid_ask():
    assert quant.option_mid(1.0, 1.2, 9.0) == pytest.approx(1.1)
    assert quant.option_mid(0, 0, 2.5) == pytest.approx(2.5)
    assert quant.option_mid(0, 0, 0) is None


# ------------------------------------------------------------
# GBM
# ------------------------------------------------------------

def test_gbm_shape_start_positive_reproducible():
    paths = quant.simulate_gbm_paths(100, 0.08, 0.25, 63, 63, 5000, seed=7)
    assert paths.shape == (5000, 64)
    assert np.allclose(paths[:, 0], 100)
    assert (paths > 0).all()
    again = quant.simulate_gbm_paths(100, 0.08, 0.25, 63, 63, 10, seed=7)
    assert np.allclose(again, paths[:10])


def test_gbm_mean_matches_drift():
    paths = quant.simulate_gbm_paths(100, 0.08, 0.25, 63, 63, 5000, seed=7)
    tq = 63 / 252
    expected = 100 * np.exp(0.08 * tq)
    assert abs(paths[:, -1].mean() - expected) < 1.0


# ------------------------------------------------------------
# Monte Carlo vs closed form
# ------------------------------------------------------------

def test_mc_call_within_three_se_of_bs(call):
    mc, se, *_ = quant.monte_carlo_price(100, 100, 0.04, 0.25, 63, 80_000, "call", seed=3)
    assert abs(mc - call["price"]) < 3 * se


def test_mc_put_within_three_se_of_bs(put):
    mc, se, *_ = quant.monte_carlo_price(100, 100, 0.04, 0.25, 63, 80_000, "put", seed=3)
    assert abs(mc - put["price"]) < 3 * se


def test_mc_terminal_sampling_is_lognormal():
    _, _, finals, payoffs = quant.monte_carlo_price(100, 100, 0.04, 0.25, 63, 200_000, "call", seed=5)
    assert finals.shape == payoffs.shape == (200_000,)
    assert abs(finals.mean() - 100 * np.exp(0.04 * 63 / 252)) < 0.2


# ------------------------------------------------------------
# Volatility forecasting
# ------------------------------------------------------------

def _synthetic_prices(n=500, daily_vol=0.02, seed=1):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, daily_vol, n)))


def test_rolling_vol_warmup_and_level():
    prices = _synthetic_prices()
    rv = quant.rolling_vol_forecast(prices, window=21)
    true_vol = 0.02 * np.sqrt(252)
    valid = rv[~np.isnan(rv)]
    assert np.isnan(rv[:21]).all()
    assert abs(valid.mean() - true_vol) < 0.05


def test_garch_produces_sane_forecasts():
    prices = _synthetic_prices()
    gv = quant.garch_vol_forecast(prices, refit_every=20, window=252)
    valid = gv[~np.isnan(gv)]
    assert len(valid) > 100
    assert (valid > 0.05).all()
    assert (valid < 2.0).all()


def test_clean_sigma_replaces_nan_and_nonpositive():
    prices = _synthetic_prices()
    rv = quant.rolling_vol_forecast(prices, window=21)
    cleaned = quant.clean_sigma_series(rv, 0.3)
    assert not np.isnan(cleaned).any()
    assert (cleaned[:21] == 0.3).all()
    assert (quant.clean_sigma_series(np.array([-1.0, 0.0, np.nan]), 0.2) == 0.2).all()


def test_rolling_vol_no_lookahead():
    """Window ending at t must ignore prices after t."""
    prices = _synthetic_prices(80)
    full = quant.rolling_vol_forecast(prices, window=21)
    truncated = quant.rolling_vol_forecast(prices[:50], window=21)
    assert np.allclose(full[:50], truncated, equal_nan=True)


# ------------------------------------------------------------
# Hedge engine — the interest-accrual invariant
# ------------------------------------------------------------

def test_hedged_pnl_near_zero_under_true_vol():
    """Short a call, delta-hedge at the true GBM vol, zero costs.

    With cash interest, mean hedged P&L must be statistically zero.
    Without interest this sat ~0.55 — twenty-five SEs from zero.
    """
    paths = quant.simulate_gbm_paths(100, 0.04, 0.2, 63, 252, 120, seed=11)
    sig = np.full(253, 0.2)
    hedged, unhedged = [], []
    for i in range(120):
        hp, up = quant.hedge_path_variable_sigma(
            paths[i], 100, 0.04, sig, 0.25, 252, 0.0, 1, "call"
        )
        hedged.append(hp)
        unhedged.append(up)
    mean, std = np.mean(hedged), np.std(hedged)
    se = std / np.sqrt(120)
    assert abs(mean) < 3 * se + 0.05, f"hedged mean={mean:.4f} se={se:.4f}"
    assert std < 0.25 * np.std(unhedged)


def test_transaction_costs_reduce_pnl():
    path = quant.simulate_gbm_paths(100, 0.04, 0.2, 63, 252, 1, seed=11)[0]
    sig = np.full(253, 0.2)
    with_cost, _ = quant.hedge_path_variable_sigma(
        path, 100, 0.04, sig, 0.25, 252, 0.005, 1, "call"
    )
    free, _ = quant.hedge_path_variable_sigma(
        path, 100, 0.04, sig, 0.25, 252, 0.0, 1, "call"
    )
    assert with_cost < free


def test_hedge_history_lengths():
    path = quant.simulate_gbm_paths(100, 0.04, 0.2, 63, 252, 1, seed=11)[0]
    sig = np.full(253, 0.2)
    _, _, hist = quant.hedge_path_variable_sigma(
        path, 100, 0.04, sig, 0.25, 252, 0.001, 1, "call", return_history=True
    )
    assert len(hist["t"]) == len(hist["portfolio_value"]) == 253
    assert "payout" in hist and "premium_collected" in hist


def test_cash_accrues_interest_between_steps():
    """cash_t = cash_{t-1} * e^{r dt} minus the cost of the delta trade."""
    n_steps = 10
    prices = np.full(n_steps + 1, 100.0)
    sig = np.full(n_steps + 1, 0.2)
    r = 0.04
    _, _, hist = quant.hedge_path_variable_sigma(
        prices, 100, r, sig, n_steps / 252, n_steps, 0.0, 1, "call",
        return_history=True,
    )
    dt = (n_steps / 252) / n_steps
    grown = hist["cash"][0] * np.exp(r * dt)
    trade = (hist["delta"][1] - hist["delta"][0]) * prices[1]
    expected = grown - trade
    assert abs(hist["cash"][1] - expected) < 1e-8
