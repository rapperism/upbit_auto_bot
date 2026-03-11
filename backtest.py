import pyupbit
import numpy as np

def backtest(ticker="KRW-BTC", k=0.5, count=30):
    """과거 데이터를 기반으로 변동성 돌파 전략 수익률 계산"""
    # OHLCV(Open, High, Low, Close, Volume) 데이터 가져오기
    df = pyupbit.get_ohlcv(ticker, interval="day", count=count)
    
    # 변동폭 계산 (고가 - 저가)
    df['range'] = (df['high'] - df['low']) * k
    
    # 매수 목표가 (시가 + 변동폭)
    df['target'] = df['open'] + df['range'].shift(1)
    
    # 수익률 계산 (매수가 대비 종가)
    # 매수 조건: 고가가 목표가보다 높아야 함
    df['ror'] = np.where(df['high'] > df['target'],
                         df['close'] / df['target'],
                         1)
    
    # 누적 수익률 (HPR)
    df['hpr'] = df['ror'].cumprod()
    
    # 낙폭 (Drawdown) 계산
    df['dd'] = (df['hpr'].cummax() - df['hpr']) / df['hpr'].cummax() * 100
    
    print(f"--- Backtest Result for {ticker} (k={k}, days={count}) ---")
    print(f"Cumulative Return (HPR): {df['hpr'].iloc[-1]:.4f}")
    print(f"Max Drawdown (MDD): {df['dd'].max():.2f}%")
    
    return df

if __name__ == "__main__":
    # 비트코인 최근 30일 백테스트 실행
    backtest("KRW-BTC", k=0.5, count=30)
