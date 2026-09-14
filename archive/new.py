"""
Add-on module for the Delta Hedging Simulator.

Contains:
  1. Volatility forecasting (rolling-window + GARCH(1,1)) that plugs into the
     existing hedge_path() engine via a NEW variable-sigma variant.
  2. A historical-backtest loader for the Kaggle "US Banks Stock All-Time" CSV.
  3. A ready-to-paste Streamlit tab that compares:
         static sigma  vs  rolling-vol forecast  vs  GARCH forecast
     on real historical bank price windows (2008 crash, calm period, SVB 2023).

Install once:  pip install arch pandas
Drop this file next to your main app.py and `from vol_forecast_and_backtest import *`
then add `tab_backtest` to your st.tabs(...) call (see bottom of file).
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from math import isnan




# ============================================================
# 1. VOLATILITY FORECASTING
# ============================================================

def rolling_vol_forecast(price_series, window=21, annualize=252, min_periods=None):
    price_series = np.asarray(price_series, dtype=float)
    log_rets = np.diff(np.log(price_series))
    s = pd.Series(log_rets)
    min_periods = min_periods or window
    rolling_std = s.rolling(window=window, min_periods=min_periods).std()
    forecast = rolling_std.values * np.sqrt(annualize)
    return np.concatenate([[np.nan], forecast])


def garch_vol_forecast(price_series, horizon=1, refit_every=5, window=252,
                        annualize=252):
    try:
        from arch import arch_model
    except ImportError:
        st.warning("`arch` package not installed — falling back to rolling-window "
                   "vol forecast. Run `pip install arch` for GARCH.")
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
    out = np.array(sigma_array, dtype=float)
    bad = np.isnan(out) | (out <= 0)
    out[bad] = fallback_sigma
    return out


# ============================================================
# 2. VARIABLE-SIGMA HEDGE ENGINE
# ============================================================

def hedge_path_variable_sigma(prices, K, r, sigma_hedge_series, T_total, n_steps,
                               transaction_cost_rate, rebalance_every=1,
                               option_type="call", option_premium=None,
                               return_history=False):
    from scipy.stats import norm

    def bs_price_and_delta(S, K, T, r, sigma, option_type="call"):
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

    dt = T_total / n_steps
    shares_held = 0.0
    cash = 0.0
    sigma0 = sigma_hedge_series[0]
    theo_price, _ = bs_price_and_delta(prices[0], K, T_total, r, sigma0, option_type)
    premium_collected = option_premium if option_premium is not None else theo_price
    cash += premium_collected

    history = {"t": [], "S": [], "delta": [], "cash": [], "portfolio_value": [],
               "sigma_used": []} if return_history else None

    for t in range(n_steps + 1):
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
        _, delta_t = bs_price_and_delta(S_t, K, T_remaining, r, sigma_t, option_type)
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
# 3. HISTORICAL DATA LOADER (Kaggle: US Banks Stock All-Time)
# ============================================================

@st.cache_data(ttl=3600)
def load_bank_csv(csv_bytes):
    df = pd.read_csv(csv_bytes)
    return df


def get_historical_window(df, date_col, ticker_col, ticker, price_col,
                           start_date, window_days):
    sub = df[df[ticker_col] == ticker].copy()
    sub[date_col] = pd.to_datetime(sub[date_col], errors="coerce")
    sub = sub.dropna(subset=[date_col])
    sub = sub[sub[date_col] >= pd.to_datetime(start_date)].sort_values(date_col)
    sub = sub.iloc[:window_days]
    if len(sub) < window_days:
        raise ValueError(
            f"Only {len(sub)} usable rows available for {ticker} from "
            f"{start_date} (need {window_days}). Try a shorter window or an "
            f"earlier start date."
        )
    prices = pd.to_numeric(sub[price_col], errors="coerce").values.astype(float)
    if np.isnan(prices).any():
        raise ValueError(
            f"Price column '{price_col}' has non-numeric values in this window "
            f"— double check you picked the right column."
        )
    return sub[date_col].values, prices


SUGGESTED_WINDOWS = {
    "2008 Financial Crisis": "2008-09-01",
    "Calm Period (2017)": "2017-01-03",
    "SVB / Regional Bank Crisis (2023)": "2023-03-01",
}


# ============================================================
# 4. STREAMLIT TAB
# ============================================================

def render_backtest_tab(tab_backtest, r, transaction_cost_rate, rebalance_every,
                         option_type):
    with tab_backtest:
        st.subheader("Historical Backtest — Real Bank Stock Data")
        st.caption("Replays the same hedging engine on actual historical price "
                   "paths instead of simulated GBM, comparing a static vol "
                   "assumption against rolling-window and GARCH vol forecasts.")

        csv_file = st.file_uploader("Upload the Kaggle US Banks CSV", type="csv")
        if csv_file is None:
            st.info("Upload the dataset to run a backtest "
                    "(kaggle.com/datasets/rockyt07/us-banks-stock-all-time).")
            return

        try:
            df = load_bank_csv(csv_file)
        except Exception as e:
            st.error(f"Could not read that CSV: {e}")
            return

        if df.empty or len(df.columns) < 3:
            st.error("This CSV doesn't look right (empty or too few columns). "
                     "Check you uploaded the correct file.")
            return

        cols = list(df.columns)
        date_col = st.selectbox("Date column", cols, index=0)
        ticker_col = st.selectbox("Ticker/Bank column", cols,
                                   index=min(1, len(cols) - 1))
        price_col = st.selectbox("Price column (Close)", cols,
                                  index=min(4, len(cols) - 1))

        try:
            tickers = sorted(df[ticker_col].dropna().unique().tolist())
        except Exception as e:
            st.error(f"Couldn't read the ticker column: {e}")
            return

        if not tickers:
            st.error("No tickers found in that column — pick a different one.")
            return

        bank = st.selectbox("Bank", tickers)
        window_label = st.selectbox("Window", list(SUGGESTED_WINDOWS.keys()))
        start_date = st.text_input("Start date", value=SUGGESTED_WINDOWS[window_label])
        window_days = st.slider("Window length (trading days)", 20, 252, 63)
        K_mult = st.slider("Strike as % of starting price", 0.8, 1.2, 1.0)

        if st.button("Run Historical Backtest", type="primary"):
            try:
                dates, prices = get_historical_window(
                    df, date_col, ticker_col, bank, price_col, start_date, window_days
                )
            except ValueError as e:
                st.error(str(e))
                return
            except Exception as e:
                st.error(f"Unexpected error reading the window: {e}")
                return

            try:
                S0 = prices[0]
                K = round(S0 * K_mult, 2)
                T_total = window_days / 252
                n_steps = window_days - 1
                static_sigma = float(np.diff(np.log(prices)).std() * np.sqrt(252))

                roll_fc = clean_sigma_series(
                    rolling_vol_forecast(prices, window=21), static_sigma
                )
                garch_fc = clean_sigma_series(
                    garch_vol_forecast(prices, window=min(126, window_days - 5)),
                    static_sigma
                )
                static_series = np.full(len(prices), static_sigma)

                results = {}
                for label, sigma_series in [
                    ("Static σ (naive)", static_series),
                    ("Rolling-window forecast", roll_fc),
                    ("GARCH(1,1) forecast", garch_fc),
                ]:
                    hedged_pnl, unhedged_pnl = hedge_path_variable_sigma(
                        prices, K, r, sigma_series, T_total, n_steps,
                        transaction_cost_rate, rebalance_every, option_type
                    )
                    results[label] = (hedged_pnl, unhedged_pnl)
            except Exception as e:
                st.error(f"Backtest failed to run: {e}")
                return

            st.subheader(f"{bank} — {window_label} ({dates[0]} to {dates[-1]})")
            c1, c2, c3 = st.columns(3)
            c1.metric("Start Price", f"{S0:.2f}")
            c2.metric("Strike", f"{K:.2f}")
            c3.metric("Realized Vol (full window)", f"{static_sigma:.2%}")

            cols = st.columns(3)
            for col, (label, (h, u)) in zip(cols, results.items()):
                col.metric(label, f"Hedged: {h:.2f}", f"Unhedged: {u:.2f}")

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=prices, name="Price",
                                      line=dict(color="#38bdf8")))
            fig.add_hline(y=K, line_dash="dash", line_color="#f59e0b",
                          annotation_text="Strike")
            fig.update_layout(template="plotly_dark", height=350,
                              title="Historical Price Path")
            st.plotly_chart(fig, use_container_width=True)

            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(y=static_series, name="Static σ",
                                       line=dict(color="#94a3b8", dash="dot")))
            fig2.add_trace(go.Scatter(y=roll_fc, name="Rolling forecast",
                                       line=dict(color="#a78bfa")))
            fig2.add_trace(go.Scatter(y=garch_fc, name="GARCH forecast",
                                       line=dict(color="#34d399")))
            fig2.update_layout(template="plotly_dark", height=350,
                               title="Volatility Forecasts Over the Window",
                               yaxis_tickformat=".0%")
            st.plotly_chart(fig2, use_container_width=True)

            st.caption(
                "Hedged P&L closer to 0 with lower variance = better hedge. "
                "Compare how each vol assumption performs, especially in the "
                "crisis windows where realized vol moves fast."
            )