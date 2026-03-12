import os
import time
from datetime import datetime

import pandas as pd
import pyupbit
from dotenv import load_dotenv

# Load API keys from .env
load_dotenv()
access_key = os.getenv("UPBIT_ACCESS_KEY")
secret_key = os.getenv("UPBIT_SECRET_KEY")

# Create Upbit client
upbit = pyupbit.Upbit(access_key, secret_key)


def get_ohlcv_or_none(ticker, interval="day", count=1):
    """Return OHLCV dataframe or None when the API returns no usable data."""
    df = pyupbit.get_ohlcv(ticker, interval=interval, count=count)
    if df is None or df.empty:
        return None
    return df


def get_target_price(ticker, k):
    """Get volatility breakout target price."""
    df = get_ohlcv_or_none(ticker, interval="day", count=2)
    if df is None or len(df) < 1:
        return None

    candle = df.iloc[0]
    return candle["close"] + (candle["high"] - candle["low"]) * k


def get_start_time(ticker):
    """Get market start time."""
    df = get_ohlcv_or_none(ticker, interval="day", count=1)
    if df is None or len(df.index) < 1:
        return None
    return df.index[0]


def get_ma5(ticker):
    """Get 5-day moving average."""
    df = get_ohlcv_or_none(ticker, interval="day", count=5)
    if df is None or "close" not in df or len(df) < 5:
        return None

    ma5 = df["close"].rolling(window=5).mean().iloc[-1]
    if pd.isna(ma5):
        return None
    return ma5


def get_balance(ticker):
    """Get balance for the given currency."""
    balances = upbit.get_balances()
    if not balances:
        return 0

    for item in balances:
        currency = item.get("currency")
        balance = item.get("balance")

        if currency == ticker:
            if balance is None:
                return 0
            return float(balance)

    return 0


def get_current_price(ticker):
    """Get current ask price."""
    orderbook = pyupbit.get_orderbook(ticker=ticker)
    if not orderbook:
        return None

    if isinstance(orderbook, list):
        orderbook = orderbook[0] if orderbook else None

    if not orderbook:
        return None

    orderbook_units = orderbook.get("orderbook_units")
    if not orderbook_units:
        return None

    first_unit = orderbook_units[0]
    if not first_unit:
        return None

    return first_unit.get("ask_price")


print("Upbit Bot Initialized.")


def run_trading_bot(ticker="KRW-BTC", k=0.5):
    """Main trading loop."""
    print(f"Trading bot started for {ticker} with k={k}")

    while True:
        try:
            now = datetime.now()
            start_time = get_start_time(ticker)
            if start_time is None:
                print(f"Warning: failed to get start time for {ticker}")
                time.sleep(1)
                continue

            end_time = start_time + pd.Timedelta(days=1)

            # Trading window: 09:00:00 to the next day 08:59:50
            if start_time < now < end_time - pd.Timedelta(seconds=10):
                target_price = get_target_price(ticker, k)
                ma5 = get_ma5(ticker)
                current_price = get_current_price(ticker)

                if target_price is None or ma5 is None or current_price is None:
                    print(f"Warning: market data unavailable for {ticker}")
                    time.sleep(1)
                    continue

                if target_price < current_price and ma5 < current_price:
                    krw = get_balance("KRW")
                    if krw > 5000:
                        print(f"Buying {ticker} at {current_price}")
                        upbit.buy_market_order(ticker, krw * 0.9995)

            else:
                base_currency = ticker.split("-")[1]
                coin_balance = get_balance(base_currency)
                if coin_balance > 0.00008:
                    current_price = get_current_price(ticker)
                    if current_price is None:
                        print(f"Warning: failed to get current price for {ticker}")
                        time.sleep(1)
                        continue

                    print(f"Selling {ticker} at {current_price}")
                    upbit.sell_market_order(ticker, coin_balance)

            time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    run_trading_bot("KRW-BTC")
