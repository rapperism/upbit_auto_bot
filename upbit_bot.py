import os
import time
import pyupbit
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# .env 파일에서 API Key 로드
load_dotenv()
access_key = os.getenv("UPBIT_ACCESS_KEY")
secret_key = os.getenv("UPBIT_SECRET_KEY")

# 업비트 객체 생성
upbit = pyupbit.Upbit(access_key, secret_key)

def get_target_price(ticker, k):
    """변동성 돌파 전략으로 매수 목표가 조회"""
    df = pyupbit.get_ohlcv(ticker, interval="day", count=2)
    target_price = df.iloc[0]['close'] + (df.iloc[0]['high'] - df.iloc[0]['low']) * k
    return target_price

def get_start_time(ticker):
    """시작 시간 조회"""
    df = pyupbit.get_ohlcv(ticker, interval="day", count=1)
    start_time = df.index[0]
    return start_time

def get_ma5(ticker):
    """5일 이동 평균선 조회"""
    df = pyupbit.get_ohlcv(ticker, interval="day", count=5)
    ma5 = df['close'].rolling(window=5).mean().iloc[-1]
    return ma5

def get_balance(ticker):
    """잔고 조회"""
    balances = upbit.get_balances()
    for b in balances:
        if b['currency'] == ticker:
            if b['balance'] is not None:
                return float(b['balance'])
            else:
                return 0
    return 0

def get_current_price(ticker):
    """현재가 조회"""
    return pyupbit.get_orderbook(ticker=ticker)["orderbook_units"][0]["ask_price"]

print("Upbit Bot Initialized.")

def run_trading_bot(ticker="KRW-BTC", k=0.5):
    """자동매매 실행 루프"""
    print(f"Trading bot started for {ticker} with k={k}")
    
    while True:
        try:
            now = datetime.now()
            start_time = get_start_time(ticker)
            end_time = start_time + pd.Timedelta(days=1)

            # 09:00:00 ~ 다음날 08:59:50 (장 운영 시간)
            if start_time < now < end_time - pd.Timedelta(seconds=10):
                target_price = get_target_price(ticker, k)
                ma5 = get_ma5(ticker)
                current_price = get_current_price(ticker)
                
                # 매수 조건: 현재가 > 목표가 AND 현재가 > 5일 이동평균선
                if target_price < current_price and ma5 < current_price:
                    krw = get_balance("KRW")
                    if krw > 5000: # 최소 주문 금액 5,000원
                        print(f"Buying {ticker} at {current_price}")
                        upbit.buy_market_order(ticker, krw * 0.9995) # 수수료 고려
            
            else:
                # 장 마감 시 전량 매도
                coin_balance = get_balance(ticker.split("-")[1])
                if coin_balance > 0.00008: # 최소 매도 수량 (BTC 기준 예시)
                    print(f"Selling {ticker} at {get_current_price(ticker)}")
                    upbit.sell_market_order(ticker, coin_balance)
            
            time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    # 실제 실행 시에는 API Key가 설정되어 있어야 합니다.
    run_trading_bot("KRW-BTC")
    # pass
