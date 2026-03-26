import logging
import os
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

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
    """Get volatility breakout target price (same formula as backtest).
    Target = today's open + (yesterday's high - yesterday's low) * k.
    get_ohlcv returns ascending order: iloc[0]=yesterday, iloc[1]=today.
    """
    df = get_ohlcv_or_none(ticker, interval="day", count=2)
    if df is None or len(df) < 2:
        return None

    yesterday = df.iloc[0]
    today = df.iloc[1]
    day_range = (yesterday["high"] - yesterday["low"]) * k
    return today["open"] + day_range


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


# Minimum return to sell after fees (0.05% buy + 0.05% sell ≈ 0.1%)
MIN_RETURN_TO_SELL = 0.001

# Stop-loss: 평균 매수가 대비 이 비율만큼 하락 시 즉시 매도 (수수료 최소 수익 조건보다 우선)
STOP_LOSS_PCT = 0.03


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


def get_avg_buy_price(currency):
    """Get average buy price for the given currency (from Upbit balance). Returns None if not available."""
    balances = upbit.get_balances()
    if not balances:
        return None

    for item in balances:
        if item.get("currency") == currency:
            price = item.get("avg_buy_price")
            if price is None or price == "":
                return None
            try:
                return float(price)
            except (TypeError, ValueError):
                return None
    return None


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


# 로그: 파일(일 단위 로테이션, 30일 보관) + 콘솔
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "upbit_bot.log")
LOG_BACKUP_DAYS = 30
_logger = None


def setup_logging():
    """파일(일 단위 로테이션, 30일 초과 분 삭제) + 콘솔 출력 설정."""
    global _logger
    if _logger is not None:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    _logger = logging.getLogger("upbit_bot")
    _logger.setLevel(logging.INFO)
    _logger.handlers.clear()
    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=LOG_BACKUP_DAYS,
        encoding="utf-8",
    )
    fh.suffix = "%Y-%m-%d"
    fh.setFormatter(fmt)
    _logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    _logger.addHandler(sh)


def log(msg):
    """콘솔 + 로그 파일에 시간 접두어와 함께 출력."""
    if _logger is None:
        setup_logging()
    _logger.info(msg)


setup_logging()
log("Upbit Bot Initialized.")


def run_trading_bot(ticker="KRW-BTC", k=0.5):
    """Main trading loop."""
    log(f"Trading bot started for {ticker} with k={k}")
    last_buy_log_time = None
    BUY_LOG_INTERVAL_SEC = 60  # 매수 조건 로그는 60초마다 한 번만

    while True:
        try:
            now = datetime.now()
            start_time = get_start_time(ticker)
            if start_time is None:
                log(f"Warning: failed to get start time for {ticker}")
                time.sleep(1)
                continue

            # 손절: 보유 중이고 평단이 있으면, 매도 구간과 무관하게 임계 하락 시 즉시 매도
            base_currency = ticker.split("-")[1]
            coin_balance = get_balance(base_currency)
            if coin_balance > 0.00008:
                sl_price = get_current_price(ticker)
                avg_buy_sl = get_avg_buy_price(base_currency)
                if (
                    avg_buy_sl is not None
                    and avg_buy_sl > 0
                    and sl_price is not None
                    and sl_price <= avg_buy_sl * (1 - STOP_LOSS_PCT)
                ):
                    log(
                        f"Stop-loss sell {ticker} at {sl_price:,.0f} "
                        f"(avg_buy={avg_buy_sl:,.0f}, threshold -{STOP_LOSS_PCT*100:.0f}%)"
                    )
                    upbit.sell_market_order(ticker, coin_balance)
                    time.sleep(1)
                    continue

            end_time = start_time + pd.Timedelta(days=1)

            # Trading window: 09:00:00 to the next day 08:59:50
            if start_time < now < end_time - pd.Timedelta(seconds=10):
                target_price = get_target_price(ticker, k)
                ma5 = get_ma5(ticker)
                current_price = get_current_price(ticker)

                if target_price is None or ma5 is None or current_price is None:
                    log(f"Warning: market data unavailable for {ticker}")
                    time.sleep(1)
                    continue

                # 매수 조건: 목표가 돌파(target < 현재가) + 현재가가 5일선 위(ma5 < 현재가)
                should_buy = target_price < current_price and ma5 < current_price
                if should_buy:
                    krw = get_balance("KRW")
                    if krw > 5000:
                        log(f"Buying {ticker} at {current_price:,.0f}")
                        upbit.buy_market_order(ticker, krw * 0.9995)
                    else:
                        if last_buy_log_time is None or (now - last_buy_log_time).total_seconds() >= BUY_LOG_INTERVAL_SEC:
                            log(f"[Buy condition OK but no KRW] target={target_price:,.0f} ma5={ma5:,.0f} current={current_price:,.0f} krw={krw:,.0f}")
                            last_buy_log_time = now
                else:
                    # 왜 매수 안 하는지 주기적으로 로그 (매초 말고 60초마다)
                    if last_buy_log_time is None or (now - last_buy_log_time).total_seconds() >= BUY_LOG_INTERVAL_SEC:
                        reason = []
                        if current_price <= target_price:
                            reason.append(f"current({current_price:,.0f}) <= target({target_price:,.0f})")
                        if current_price <= ma5:
                            reason.append(f"current({current_price:,.0f}) <= ma5({ma5:,.0f})")
                        log(f"[No buy] {ticker} — {'; '.join(reason)}")
                        last_buy_log_time = now

            else:
                # 매도 구간(09:00 전 등): 다음 날 매수 로그를 위해 초기화
                last_buy_log_time = None
                coin_balance = get_balance(base_currency)
                if coin_balance > 0.00008:
                    current_price = get_current_price(ticker)
                    if current_price is None:
                        log(f"Warning: failed to get current price for {ticker}")
                        time.sleep(1)
                        continue

                    avg_buy = get_avg_buy_price(base_currency)
                    if avg_buy is not None and avg_buy > 0:
                        min_sell_price = avg_buy * (1 + MIN_RETURN_TO_SELL)
                        if current_price < min_sell_price:
                            log(
                                f"Skipping sell {ticker}: {current_price:,.0f} < min {min_sell_price:,.0f} "
                                f"(avg_buy={avg_buy:,.0f}, need +{MIN_RETURN_TO_SELL*100:.2f}%)"
                            )
                            time.sleep(1)
                            continue

                    log(f"Selling {ticker} at {current_price:,.0f}")
                    upbit.sell_market_order(ticker, coin_balance)

            time.sleep(1)
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    run_trading_bot("KRW-BTC")
