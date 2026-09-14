import yfinance as yf
import numpy as np

ticker = "AAPL"
data = yf.download(ticker, period="6mo", interval="1d")

close_prices = data["Close"].values.flatten()
current_price = close_prices[-1]

daily_returns = np.diff(np.log(close_prices))
realized_vol = daily_returns.std() * np.sqrt(252)  # annualized volatility

print(f"Ticker: {ticker}")
print(f"Current price: {current_price:.2f}")
print(f"Number of trading days pulled: {len(close_prices)}")
print(f"Realized annualized volatility: {realized_vol:.4f}")