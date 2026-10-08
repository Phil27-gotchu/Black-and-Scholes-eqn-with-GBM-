"""
quant.py — pricing / simulation / hedging engines.

Pure numerics: no Streamlit imports here so everything is unit-testable.
"""

import numpy as np
import pandas as pd
from scipy.stats import norm


# ============================================================
# VOLATILITY FORECASTING
# ============================================================

def rolling_vol_forecast(price_series, window=21, annualize=252, min_periods=None):
    """
    Rolling realized-vol forecast. At each index t, uses ONLY prices up to t
    (no look-ahead). Returns an array aligned with price_series (NaN for the
    first `window` points, since there isn't enough history yet).
    """
    price_series = np.asarray(price_series, dtype=float)
    log_rets = np.diff(np.log(price_series))
    s = pd.Series(log_rets)
    min_periods = min_periods or window
    rolling_std = s.rolling(window=window, min_periods=min_periods).std()
    forecast = rolling_std.values * np.sqrt(annualize)
    return np.concatenate([[np.nan], forecast])


def garch_vol_forecast(price_series, horizon=1, refit_every=5, window=252,
                       annualize=252):
    """
    Rolling GARCH(1,1) one-step-ahead vol forecast, refit periodically (refit
    every `refit_every` steps to keep runtime reasonable) using a trailing
    `window`-day history. No look-ahead: fit only ever uses data up to t.

    Falls back to rolling_vol_forecast if `arch` isn't installed.
    """
    try:
        from arch import arch_model
    except ImportError:
        return rolling_vol_forecast(price_series, window=21, annualize=annualize)

    price_series = np.asarray(price_series, dtype=float)
    log_rets = np.diff(np.log(price_series)) * 100
    n = len(log_rets)
    forecasts = np.full(n + 1, np.nan)

    last_fit_sigma = None
    for t in range(window, n):
        if (t - window) % refit_every == 0 or last_fit_sigma is None:
            hist = log_rets[max(0, t - window):t]
            try:
                model = arch_model(hist, vol="Garch", p=1, q=1, dist="normal")
                fit = model.fit(disp="off")
                fcast = fit.forecast(horizon=horizon, reindex=False)
                sigma_next = np.sqrt(fcast.variance.values[-1, 0]) / 100 * np.sqrt(annualize)
                last_fit_sigma = sigma_next
            except Exception:
                last_fit_sigma = rolling_vol_forecast(
                    price_series[:t + 2], window=21, annualize=annualize
                )[-1]
        forecasts[t + 1] = last_fit_sigma

    return forecasts


def clean_sigma_series(sigma_array, fallback_sigma):
    """Replace NaN/invalid vol forecasts (e.g. warm-up period) with a fallback
    so the hedge engine never receives an unusable sigma."""
    out = np.array(sigma_array, dtype=float)
    bad = np.isnan(out) | (out <= 0)
    out[bad] = fallback_sigma
    return out


# ============================================================
# BLACK-SCHOLES
# ============================================================

def bs_price_delta_greeks(S, K, T, r, sigma, option_type="call"):
    if T <= 0 or sigma <= 0:
        price = max(S - K, 0) if option_type == "call" else max(K - S, 0)
        delta = (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
        return dict(price=price, delta=delta, gamma=0.0, vega=0.0, theta=0.0, rho=0.0)

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    pdf_d1 = norm.pdf(d1)

    if option_type == "call":
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = (-S * pdf_d1 * sigma / (2 * np.sqrt(T))
                 - r * K * np.exp(-r * T) * norm.cdf(d2)) / 252
        rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1
        theta = (-S * pdf_d1 * sigma / (2 * np.sqrt(T))
                 + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 252
        rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100

    gamma = pdf_d1 / (S * sigma * np.sqrt(T))
    vega = S * pdf_d1 * np.sqrt(T) / 100

    return dict(price=price, delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)


def implied_vol(market_price, S, K, T, r, option_type="call",
                sigma0=0.25, tol=1e-8, max_iter=50):
    """
    Newton-Raphson inversion of Black-Scholes: find σ such that
    BS(S, K, T, r, σ) = market_price.

    Vega in bs_price_delta_greeks is per 1% vol, so dPrice/dσ = vega * 100.
    Returns NaN if the quote is unusable (expired, below intrinsic, flat vega).
    """
    try:
        market_price = float(market_price)
    except (TypeError, ValueError):
        return float("nan")
    if T <= 0 or market_price <= 0 or S <= 0 or K <= 0:
        return float("nan")

    df = np.exp(-r * T)
    floor = max(S - K * df, 0.0) if option_type == "call" else max(K * df - S, 0.0)
    if market_price < floor - 1e-8:
        return float("nan")

    sigma = float(sigma0)
    for _ in range(max_iter):
        sigma = min(max(sigma, 1e-4), 5.0)
        g = bs_price_delta_greeks(S, K, T, r, sigma, option_type)
        diff = g["price"] - market_price
        if abs(diff) < tol:
            return float(sigma)
        vega_unit = g["vega"] * 100.0
        if abs(vega_unit) < 1e-12:
            return float("nan")
        sigma -= diff / vega_unit
    return float(sigma) if abs(diff) < 1e-4 else float("nan")


def option_mid(bid, ask, last):
    """Mid quote, falling back to last trade."""
    try:
        bid, ask, last = float(bid or 0), float(ask or 0), float(last or 0)
    except (TypeError, ValueError):
        return None
    if bid > 0 and ask > 0 and ask >= bid:
        return 0.5 * (bid + ask)
    if last > 0:
        return last
    if bid > 0:
        return bid
    return None


# ============================================================
# VARIABLE-SIGMA HEDGE ENGINE
# ============================================================

def _bs_price_and_delta(S, K, T, r, sigma, option_type="call"):
    if T <= 0:
        if option_type == "call":
            return max(S - K, 0), 1.0 if S > K else 0.0
        return max(K - S, 0), -1.0 if S < K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == "call":
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1
    return price, delta


def hedge_path_variable_sigma(prices, K, r, sigma_hedge_series, T_total, n_steps,
                              transaction_cost_rate, rebalance_every=1,
                              option_type="call", option_premium=None,
                              return_history=False):
    """
    Delta-hedge a short option along a realized price path, using
    sigma_hedge_series[t] as the hedge vol at step t.
    """
    dt = T_total / n_steps
    shares_held = 0.0
    cash = 0.0
    sigma0 = sigma_hedge_series[0]
    theo_price, _ = _bs_price_and_delta(prices[0], K, T_total, r, sigma0, option_type)
    premium_collected = option_premium if option_premium is not None else theo_price
    cash += premium_collected

    history = {"t": [], "S": [], "delta": [], "cash": [], "portfolio_value": [],
               "sigma_used": []} if return_history else None

    for t in range(n_steps + 1):
        if t > 0:
            cash *= np.exp(r * dt)  # cash account accrues/pays interest
        sigma_t = sigma_hedge_series[min(t, len(sigma_hedge_series) - 1)]
        if t % rebalance_every != 0 and t != n_steps:
            if return_history:
                history["t"].append(t)
                history["S"].append(prices[t])
                history["delta"].append(shares_held)
                history["cash"].append(cash)
                history["portfolio_value"].append(cash + shares_held * prices[t])
                history["sigma_used"].append(sigma_t)
            continue
        S_t = prices[t]
        T_remaining = T_total - t * dt
        _, delta_t = _bs_price_and_delta(S_t, K, T_remaining, r, sigma_t, option_type)
        shares_to_trade = delta_t - shares_held
        trade_cost = shares_to_trade * S_t
        fee = abs(trade_cost) * transaction_cost_rate
        cash -= trade_cost
        cash -= fee
        shares_held = delta_t

        if return_history:
            history["t"].append(t)
            history["S"].append(S_t)
            history["delta"].append(shares_held)
            history["cash"].append(cash)
            history["portfolio_value"].append(cash + shares_held * S_t)
            history["sigma_used"].append(sigma_t)

    final_price = prices[-1]
    payout = max(final_price - K, 0) if option_type == "call" else max(K - final_price, 0)
    cash -= payout
    cash += shares_held * final_price
    hedged_pnl = cash
    unhedged_pnl = premium_collected - payout

    if return_history:
        history["payout"] = payout
        history["premium_collected"] = premium_collected
        return hedged_pnl, unhedged_pnl, history
    return hedged_pnl, unhedged_pnl


# ============================================================
# GBM SIMULATION & MONTE CARLO PRICING
# ============================================================

def simulate_gbm_paths(S0, mu, sigma, T_days, n_steps, n_paths, seed=None):
    """Simulate n_paths of Geometric Brownian Motion over n_steps."""
    rng = np.random.default_rng(seed)
    dt = (T_days / 252) / n_steps
    Z = rng.standard_normal((n_paths, n_steps))
    log_increments = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z
    log_paths = np.cumsum(log_increments, axis=1)
    log_paths = np.concatenate([np.zeros((n_paths, 1)), log_paths], axis=1)
    paths = S0 * np.exp(log_paths)
    return paths


def monte_carlo_price(S0, K, r, sigma, T_days, n_paths,
                      option_type="call", seed=None):
    """Risk-neutral Monte Carlo pricing of a European option.

    The payoff depends only on S_T, and under GBM S_T has an exact lognormal
    law, so terminal prices are sampled in one step: O(n_paths) time and memory.
    """
    rng = np.random.default_rng(seed)
    T = T_days / 252
    Z = rng.standard_normal(n_paths)
    final_prices = S0 * np.exp((r - 0.5 * sigma**2) * T + sigma * np.sqrt(T) * Z)
    if option_type == "call":
        payoffs = np.maximum(final_prices - K, 0)
    else:
        payoffs = np.maximum(K - final_prices, 0)
    discounted = payoffs * np.exp(-r * T)
    price = discounted.mean()
    stderr = discounted.std(ddof=1) / np.sqrt(n_paths)
    return price, stderr, final_prices, payoffs
