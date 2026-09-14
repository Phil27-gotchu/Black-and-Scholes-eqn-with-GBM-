import numpy as np
from scipy.stats import norm
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
from datetime import datetime


st.set_page_config(page_title="DELTA HEDGING // TERMINAL", layout="wide")

# ============================================================
# Quant/Terminal Styling System
# ============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=Inter:wght@300;400;500;600;700&display=swap');

/* Main Canvas & Base Typography */
html, body, [class*="css"], .stApp {
    background-color: #0a0c10 !important;
    font-family: 'Inter', -apple-system, sans-serif !important;
    color: #c9d1d9 !important;
}

/* Headers & Monospace Labels */
h1, h2, h3, h4, h5, h6, .stMarkdown, div[data-testid="stMetricLabel"] {
    font-family: 'IBM Plex Mono', monospace !important;
}

h1 {
    font-size: 1.4rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    color: #f0f6fc !important;
    margin-bottom: 0.2rem !important;
    text-transform: uppercase;
}

h2, h3 {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
    color: #8b949e !important;
    text-transform: uppercase;
    margin-top: 1rem !important;
}

/* Sidebar Terminal Styling */
section[data-testid="stSidebar"] {
    background-color: #12151b !important;
    border-right: 1px solid #232830 !important;
}

section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2 {
    color: #d4a017 !important;
    font-size: 0.8rem !important;
    letter-spacing: 0.1em !important;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid #232830;
    margin-top: 1.2rem !important;
}

/* Input Fields & Dropdowns */
div[data-baseweb="select"] > div, input[type="number"], input[type="text"] {
    background-color: #0a0c10 !important;
    border: 1px solid #232830 !important;
    border-radius: 3px !important;
    color: #f0f6fc !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.85rem !important;
}

div[data-baseweb="select"] > div:hover, input[type="number"]:focus, input[type="text"]:focus {
    border-color: #d4a017 !important;
}

/* Custom Sliders */
div[data-testid="stSlider"] div[role="slider"] {
    background-color: #d4a017 !important;
    border: none !important;
    border-radius: 2px !important;
    width: 12px !important;
    height: 12px !important;
}

div[data-testid="stSlider"] .st-cb, div[data-testid="stSlider"] > div > div > div {
    background: #232830 !important;
}

/* Buttons */
button[kind="primary"] {
    background-color: #d4a017 !important;
    color: #0a0c10 !important;
    border: 1px solid #d4a017 !important;
    border-radius: 2px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-weight: 700 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
    padding: 0.5rem 1rem !important;
    box-shadow: none !important;
    transition: all 0.15s ease !important;
}

button[kind="primary"]:hover {
    background-color: #e5b128 !important;
    border-color: #e5b128 !important;
    color: #0a0c10 !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    border-bottom: 1px solid #232830;
}

.stTabs [data-baseweb="tab"] {
    background-color: #12151b;
    border: 1px solid #232830;
    border-bottom: none;
    border-radius: 2px 2px 0 0;
    padding: 0.4rem 0.8rem;
    color: #8b949e;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
}

.stTabs [aria-selected="true"] {
    background-color: #0a0c10 !important;
    color: #d4a017 !important;
    border-color: #232830 #232830 #0a0c10 #232830 !important;
}

/* Bloomberg-style Live Ticker Strip */
.ticker-strip {
    display: flex;
    gap: 1.5rem;
    background-color: #12151b;
    border: 1px solid #232830;
    border-left: 3px solid #d4a017;
    padding: 0.6rem 1rem;
    margin-bottom: 1.2rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    border-radius: 2px;
}

.ticker-item {
    display: flex;
    flex-direction: column;
}

.ticker-label {
    color: #6e7681;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.ticker-value {
    color: #f0f6fc;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}

/* Custom Metric Card (Quant Styled) */
.metric-card {
    background-color: #12151b;
    border: 1px solid #232830;
    border-radius: 2px;
    padding: 0.75rem 1rem;
}

.metric-card .label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #6e7681;
    text-transform: uppercase;
}

.metric-card .value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.2rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    margin-top: 0.2rem;
}

/* P&L Direction Colors */
.pnl-positive { color: #4ade80 !important; }
.pnl-negative { color: #f87171 !important; }
.pnl-neutral  { color: #f0f6fc !important; }

/* Visual Chart Legend Box */
.chart-guide {
    background-color: #12151b;
    border: 1px solid #232830;
    padding: 0.6rem 0.8rem;
    margin-bottom: 0.8rem;
    font-size: 0.78rem;
    color: #8b949e;
    line-height: 1.4;
    border-radius: 2px;
}

/* Streamlit Alert Overrides */
div[data-testid="stAlert"] {
    background-color: #12151b;
    border: 1px solid #232830;
    border-radius: 2px;
    color: #8b949e;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
}
</style>
""", unsafe_allow_html=True)

# Plotly Theme Settings
PAPER_BG = "#0a0c10"
PLOT_BG = "#12151b"
GRID_COLOR = "#232830"
FONT_FAMILY = "IBM Plex Mono"

def style_fig(fig, height=450, title=None):
    fig.update_layout(
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color="#8b949e", family=FONT_FAMILY, size=11),
        height=height,
        margin=dict(l=50, r=40, t=50 if title else 30, b=40),
        title=dict(text=title.upper() if title else "", font=dict(color="#f0f6fc", size=12)),
        legend=dict(
            bgcolor="rgba(18, 21, 27, 0.8)",
            bordercolor="#232830",
            borderwidth=1,
            font=dict(color="#c9d1d9", size=10)
        ),
        hovermode="x unified",
    )
    fig.update_xaxes(
        gridcolor=GRID_COLOR, 
        zerolinecolor=GRID_COLOR, 
        tickfont=dict(color="#6e7681"),
        showline=True, linecolor=GRID_COLOR
    )
    fig.update_yaxes(
        gridcolor=GRID_COLOR, 
        zerolinecolor=GRID_COLOR, 
        tickfont=dict(color="#6e7681"),
        showline=True, linecolor=GRID_COLOR
    )
    return fig

# ============================================================
# Core Functions
# ============================================================

def bs_price_and_delta(S, K, T, r, sigma, option_type="call"):
    if T <= 0:
        if option_type == "call":
            return max(S - K, 0), 1.0 if S > K else 0.0
        else:
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

def simulate_gbm_path(S0, r, sigma_actual, T_total, n_steps, Z=None):
    dt = T_total / n_steps
    if Z is None:
        Z = np.random.normal(0, 1, n_steps)
    prices = [S0]
    for z in Z:
        S_prev = prices[-1]
        S_next = S_prev * np.exp((r - 0.5 * sigma_actual**2) * dt + sigma_actual * np.sqrt(dt) * z)
        prices.append(S_next)
    return np.array(prices)

def hedge_path(prices, K, r, sigma_hedge, T_total, n_steps, transaction_cost_rate,
                rebalance_every=1, option_type="call", option_premium=None, return_history=False):
    dt = T_total / n_steps
    shares_held = 0.0
    cash = 0.0
    theo_price, _ = bs_price_and_delta(prices[0], K, T_total, r, sigma_hedge, option_type)
    premium_collected = option_premium if option_premium is not None else theo_price
    cash += premium_collected

    history = {"t": [], "S": [], "delta": [], "cash": [], "portfolio_value": [], "rebalanced": []} if return_history else None

    for t in range(n_steps + 1):
        is_rebalance_step = (t % rebalance_every == 0) or (t == n_steps)
        if not is_rebalance_step:
            if return_history:
                history["t"].append(t)
                history["S"].append(prices[t])
                history["delta"].append(shares_held)
                history["cash"].append(cash)
                history["portfolio_value"].append(cash + shares_held * prices[t])
                history["rebalanced"].append(False)
            continue
            
        S_t = prices[t]
        T_remaining = T_total - t * dt
        _, delta_t = bs_price_and_delta(S_t, K, T_remaining, r, sigma_hedge, option_type)
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
            history["rebalanced"].append(True)

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

def run_one_path(S0, K, r, sigma, T_total, n_steps, transaction_cost_rate,
                  rebalance_every=1, option_type="call", option_premium=None,
                  sigma_actual=None):
    sigma_actual = sigma_actual if sigma_actual is not None else sigma
    prices = simulate_gbm_path(S0, r, sigma_actual, T_total, n_steps)
    return hedge_path(prices, K, r, sigma, T_total, n_steps, transaction_cost_rate,
                       rebalance_every, option_type, option_premium)

@st.cache_data(ttl=300)
def get_stock_data(ticker, period="6mo"):
    data = yf.download(ticker, period=period, interval="1d", progress=False)
    if data.empty or len(data) < 2:
        raise ValueError(f"No data returned for '{ticker}'. Check symbol.")
    close_prices = data["Close"].values.flatten()
    current_price = float(close_prices[-1])
    daily_returns = np.diff(np.log(close_prices))
    realized_vol = float(daily_returns.std() * np.sqrt(252))
    return current_price, realized_vol

@st.cache_data(ttl=300)
def get_expiries(ticker):
    t = yf.Ticker(ticker)
    expiries = t.options
    if not expiries:
        raise ValueError(f"No option expiries found for '{ticker}'.")
    return list(expiries)

@st.cache_data(ttl=300)
def get_option_chain(ticker, expiry):
    t = yf.Ticker(ticker)
    chain = t.option_chain(expiry)
    return chain.calls, chain.puts

# ============================================================
# Sidebar: Setup Parameters
# ============================================================



st.sidebar.markdown("## DATA SOURCE")
data_mode = st.sidebar.radio(
    "Setup Method",
    ["Manual inputs", "Real stock (historical volatility)", "Real option chain (live market)"],
    label_visibility="collapsed"
)

option_type = st.sidebar.selectbox("Option Type", ["call", "put"])
r = st.sidebar.slider("Risk-free Rate (r)", 0.0, 0.10, 0.05)

# 1. Define your extensive list of tickers here
POPULAR_TICKERS = [
     "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
    "AVGO", "AMD", "ORCL", "CRM", "ADBE", "CSCO", "INTC",
    "QCOM", "TXN", "MU", "IBM", "PLTR", "PANW",

    # Financials
    "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS",

    # Healthcare
    "JNJ", "LLY", "UNH", "ABBV", "PFE", "MRK",

    # Consumer
    "WMT", "COST", "HD", "LOW", "PG", "KO", "PEP", "MCD",
    "NKE", "SBUX",

    # Industrials & Energy
    "CAT", "GE", "RTX", "XOM", "CVX",

    # ETFs
    "SPY", "QQQ", "IWM"
#high
     "CRWD", "SNOW", "SHOP", "NET", "DDOG",
    "UBER", "ABNB", "MELI", "ANET", "APP",
    "RKLB", "SOFI", "HIMS", "CELH", "COIN"
]

S0 = K = sigma = T_total = option_premium = None
ticker = None
implied_vol = None
realized_vol = None

if data_mode == "Manual inputs":
    S0 = st.sidebar.number_input("Spot Price (S0)", value=100.0)
    K = st.sidebar.number_input("Strike Price (K)", value=100.0)
    sigma = st.sidebar.slider("Volatility (σ)", 0.05, 1.0, 0.20)
    T_total = st.sidebar.slider("Expiry (Years)", 0.02, 1.0, 0.25)

elif data_mode == "Real stock (historical volatility)":
    # 2. Replaced text_input with selectbox
    ticker = st.sidebar.selectbox("Select Ticker", POPULAR_TICKERS, index=POPULAR_TICKERS.index("AAPL"))
    T_total = st.sidebar.slider("Expiry (Years)", 0.02, 1.0, 0.25)
    if ticker:
        try:
            S0, sigma = get_stock_data(ticker)
            realized_vol = sigma
            K = st.sidebar.number_input("Strike Price (K)", value=round(S0, 2))
        except Exception as e:
            st.sidebar.error(str(e))

elif data_mode == "Real option chain (live market)":
    # 3. Replaced text_input with selectbox
    ticker = st.sidebar.selectbox("Select Ticker", POPULAR_TICKERS, index=POPULAR_TICKERS.index("AMZN"))
    if ticker:
        try:
            S0, hist_vol = get_stock_data(ticker)
            realized_vol = hist_vol
            expiries = get_expiries(ticker)
            expiry = st.sidebar.selectbox("Expiry Date", expiries)

            calls, puts = get_option_chain(ticker, expiry)
            table = calls if option_type == "call" else puts
            table = table[table["lastPrice"] > 0].reset_index(drop=True)
            strike_list = table["strike"].tolist()

            default_idx = int(np.argmin([abs(s - S0) for s in strike_list])) if strike_list else 0
            K = st.sidebar.selectbox("Strike Price (K)", strike_list, index=default_idx)

            row = table[table["strike"] == K].iloc[0]
            option_premium = float(row["lastPrice"])
            iv = float(row["impliedVolatility"])
            implied_vol = iv
            sigma = iv

            expiry_date = datetime.strptime(expiry, "%Y-%m-%d")
            days_to_expiry = max((expiry_date - datetime.now()).days, 1)
            T_total = days_to_expiry / 365
        except Exception as e:
            st.sidebar.error(str(e))

st.sidebar.markdown("## HEDGING PARAMETERS")
rebalance_every = st.sidebar.slider("Rebalance Interval (Days)", 1, 21, 1)
transaction_cost_rate = st.sidebar.slider("Cost per Trade Rate", 0.0, 0.01, 0.001, step=0.0005, format="%.4f")
n_simulations = st.sidebar.slider("Monte Carlo Runs", 1000, 20000, 10000, step=1000)
n_steps = st.sidebar.slider("Trading Steps to Expiry", 5, 252, 63)

run_button = st.sidebar.button("Execute Simulation", type="primary")

# ============================================================
# Main Terminal View
# ============================================================

st.markdown("<h1>DELTA HEDGING // ENGINE</h1>", unsafe_allow_html=True)

ready = all(v is not None for v in [S0, K, sigma, T_total])

# Bloomberg-style Ticker Strip
ticker_symbol = ticker if ticker else "CUSTOM"
spot_str = f"${S0:.2f}" if S0 else "---"
strike_str = f"${K:.2f}" if K else "---"
vol_str = f"{sigma:.2%}" if sigma else "---"
days_str = f"{T_total*365:.0f}D" if T_total else "---"
opt_type_str = option_type.upper() if option_type else "CALL"

st.markdown(f"""
<div class="ticker-strip">
    <div class="ticker-item"><span class="ticker-label">Asset</span><span class="ticker-value">{ticker_symbol}</span></div>
    <div class="ticker-item"><span class="ticker-label">Contract</span><span class="ticker-value">{strike_str} {opt_type_str}</span></div>
    <div class="ticker-item"><span class="ticker-label">Spot Price</span><span class="ticker-value">{spot_str}</span></div>
    <div class="ticker-item"><span class="ticker-label">Implied Vol</span><span class="ticker-value">{vol_str}</span></div>
    <div class="ticker-item"><span class="ticker-label">Expiry</span><span class="ticker-value">{days_str}</span></div>
    <div class="ticker-item"><span class="ticker-label">Hedging Freq</span><span class="ticker-value">EVERY {rebalance_every}D</span></div>
</div>
""", unsafe_allow_html=True)

tab_single, tab_dist = st.tabs(["[1] SINGLE PATH ANALYSIS", "[2] MONTE CARLO DISTRIBUTION"])

if run_button and ready:
    seed_Z = np.random.normal(0, 1, n_steps)
    demo_prices = simulate_gbm_path(S0, r, sigma, T_total, n_steps, Z=seed_Z)
    hedged_pnl_demo, unhedged_pnl_demo, hist = hedge_path(
        demo_prices, K, r, sigma, T_total, n_steps, transaction_cost_rate,
        rebalance_every, option_type, option_premium, return_history=True
    )
    st.session_state["demo_hist"] = hist
    st.session_state["demo_pnls"] = (hedged_pnl_demo, unhedged_pnl_demo)

    with st.spinner("RUNNING SIMULATION ENGINE..."):
        hedged_results = []
        unhedged_results = []
        for _ in range(n_simulations):
            h, u = run_one_path(S0, K, r, sigma, T_total, n_steps, transaction_cost_rate,
                                 rebalance_every, option_type, option_premium)
            hedged_results.append(h)
            unhedged_results.append(u)
        st.session_state["hedged_results"] = np.array(hedged_results)
        st.session_state["unhedged_results"] = np.array(unhedged_results)

    st.session_state["setup"] = dict(S0=S0, K=K, sigma=sigma, T_total=T_total, option_type=option_type)

elif run_button and not ready:
    st.warning("SETUP INCOMPLETE: Ensure all data fields are filled in the sidebar.")

has_results = "hedged_results" in st.session_state

with tab_single:
    if not has_results:
        st.info("Configure variables in the sidebar and press EXECUTE SIMULATION.")
    else:
        hist = st.session_state["demo_hist"]
        hedged_pnl_demo, unhedged_pnl_demo = st.session_state["demo_pnls"]

        st.markdown("""
        <div class="chart-guide">
            💡 <b>How to read this path:</b><br/>
            • <b>Chart 1 (Stock Price):</b> Tracks the stock over time. The yellow dashed line is the <b>Strike Price</b> where the option converts to In-The-Money.<br/>
            • <b>Chart 2 (Delta / Hedge Ratio):</b> Shows how many underlying shares you must own to stay market-neutral (0.0 = no shares, 1.0 = 100 shares). Amber dots represent <b>Rebalancing Points</b>.<br/>
            • <b>Chart 3 (Portfolio Value):</b> Your net liquidating value. Flat/stable lines mean your delta hedge successfully canceled market risk!
        </div>
        """, unsafe_allow_html=True)

        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08,
            subplot_titles=(
                "1. UNDERLYING STOCK PRICE (vs Strike Level)", 
                "2. HEDGE POSITION / REQUIRED DELTA SHARES", 
                "3. NET PORTFOLIO VALUE OVER TIME ($)"
            )
        )
        
        # Plot 1: Spot Price
        fig.add_trace(go.Scatter(
            x=hist["t"], y=hist["S"], mode="lines", name="Stock Price",
            line=dict(color="#f0f6fc", width=1.8),
            hovertemplate="Day %{x}<br/>Stock Price: $%{y:.2f}<extra></extra>"
        ), row=1, col=1)
        
        fig.add_hline(
            y=K, line_dash="dash", line_color="#d4a017", row=1, col=1,
            annotation_text=f"STRIKE PRICE (${K:.2f})", annotation_font_color="#d4a017",
            annotation_position="bottom right"
        )

        # Plot 2: Delta Shares & Rebalance Markers
        fig.add_trace(go.Scatter(
            x=hist["t"], y=hist["delta"], mode="lines", name="Delta (Shares Held)",
            line=dict(color="#d4a017", width=1.5), fill="tozeroy",
            fillcolor="rgba(212, 160, 23, 0.08)",
            hovertemplate="Day %{x}<br/>Shares Held: %{y:.3f}<extra></extra>"
        ), row=2, col=1)

        # Highlight Rebalance Execution Events
        rebal_t = [hist["t"][i] for i in range(len(hist["t"])) if hist["rebalanced"][i]]
        rebal_d = [hist["delta"][i] for i in range(len(hist["t"])) if hist["rebalanced"][i]]
        fig.add_trace(go.Scatter(
            x=rebal_t, y=rebal_d, mode="markers", name="Rebalanced Here",
            marker=dict(color="#d4a017", size=5, symbol="circle"),
            hovertemplate="Rebalanced Delta: %{y:.3f}<extra></extra>"
        ), row=2, col=1)

        # Plot 3: Cumulative Portfolio Value
        p_color = "#4ade80" if hist["portfolio_value"][-1] >= 0 else "#f87171"
        fig.add_trace(go.Scatter(
            x=hist["t"], y=hist["portfolio_value"], mode="lines", name="Hedged Portfolio Value",
            line=dict(color=p_color, width=1.8),
            hovertemplate="Day %{x}<br/>Portfolio Net Value: $%{y:.2f}<extra></extra>"
        ), row=3, col=1)
        fig.add_hline(y=0, line_color="#232830", row=3, col=1)

        fig.update_xaxes(title_text="TRADING DAYS TO EXPIRY", row=3, col=1)
        fig.update_yaxes(title_text="Price ($)", row=1, col=1)
        fig.update_yaxes(title_text="Delta (Shares)", row=2, col=1)
        fig.update_yaxes(title_text="Net Value ($)", row=3, col=1)

        fig = style_fig(fig, height=720)
        st.plotly_chart(fig, use_container_width=True)

        h_class = "pnl-positive" if hedged_pnl_demo >= 0 else "pnl-negative"
        u_class = "pnl-positive" if unhedged_pnl_demo >= 0 else "pnl-negative"

        c1, c2 = st.columns(2)
        c1.markdown(f"""
        <div class="metric-card">
            <div class="label">Sample Path Hedged Net P&L</div>
            <div class="value {h_class}">${hedged_pnl_demo:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
        c2.markdown(f"""
        <div class="metric-card">
            <div class="label">Sample Path Unhedged Net P&L</div>
            <div class="value {u_class}">${unhedged_pnl_demo:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

with tab_dist:
    if not has_results:
        st.info("Configure variables in the sidebar and press EXECUTE SIMULATION.")
    else:
        hedged_results = st.session_state["hedged_results"]
        unhedged_results = st.session_state["unhedged_results"]

        st.markdown("""
        <div class="chart-guide">
            💡 <b>How to evaluate risk reduction:</b><br/>
            • <b>Unhedged (Red Curve):</b> Wide, volatile outcome spread. If market moves against you, losses can be massive.<br/>
            • <b>Hedged (Amber Curve):</b> Narrow spike centered around $0 P&L. Demonstrates how delta hedging successfully neutralizes directional risk!
        </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        
        def render_stats_card(title, data):
            mean_v = data.mean()
            std_v = data.std()
            min_v = data.min()
            sharpe = mean_v / std_v if std_v != 0 else 0
            
            m_class = "pnl-positive" if mean_v >= 0 else "pnl-negative"
            min_class = "pnl-positive" if min_v >= 0 else "pnl-negative"
            
            return f"""
            <div class="metric-card" style="margin-bottom: 1rem;">
                <div class="label">{title}</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; margin-top: 0.5rem;">
                    <div><span class="label">Expected P&L (Mean)</span><br/><span class="value {m_class}">${mean_v:,.2f}</span></div>
                    <div><span class="label">Risk (Std Dev)</span><br/><span class="value">${std_v:,.2f}</span></div>
                    <div><span class="label">Worst Case Drawdown</span><br/><span class="value {min_class}">${min_v:,.2f}</span></div>
                    <div><span class="label">Sharpe Ratio</span><br/><span class="value">{sharpe:.3f}</span></div>
                </div>
            </div>
            """

        c1.markdown(render_stats_card("HEDGED STRATEGY METRICS", hedged_results), unsafe_allow_html=True)
        c2.markdown(render_stats_card("UNHEDGED STRATEGY METRICS", unhedged_results), unsafe_allow_html=True)

        fig2 = go.Figure()
        
        fig2.add_trace(go.Histogram(
            x=unhedged_results, nbinsx=80, name="Unhedged Strategy",
            marker_color="#f87171", opacity=0.4,
            hovertemplate="Unhedged Outcome Range: $%{x:.2f}<br/>Count: %{y}<extra></extra>"
        ))
        fig2.add_trace(go.Histogram(
            x=hedged_results, nbinsx=80, name="Delta Hedged Strategy",
            marker_color="#d4a017", opacity=0.8,
            hovertemplate="Hedged Outcome Range: $%{x:.2f}<br/>Count: %{y}<extra></extra>"
        ))
        
        # Zero Baseline Loss/Profit Divider
        fig2.add_vline(
            x=0, line_color="#8b949e", line_width=1.5,
            annotation_text="ZERO BREAKEVEN LINE ($0)", annotation_font_color="#8b949e",
            annotation_position="top left"
        )
        
        fig2.add_vline(x=hedged_results.mean(), line_dash="dash", line_color="#d4a017")
        fig2.add_vline(x=unhedged_results.mean(), line_dash="dash", line_color="#f87171")
        
        fig2.update_layout(barmode="overlay", xaxis_title="FINAL PROFIT / LOSS ($)", yaxis_title="SIMULATION FREQUENCY")
        fig2 = style_fig(fig2, height=480, title="PROFIT/LOSS DISTRIBUTION OVER 10,000 MONTE CARLO PATHS")
        st.plotly_chart(fig2, use_container_width=True)