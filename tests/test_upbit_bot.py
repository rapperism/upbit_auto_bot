# tests/test_upbit_bot.py
"""단위 테스트: 목표가 계산·매도 조건 로직 검증 (API 호출 없음)."""
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock

import pandas as pd

# 프로젝트 루트를 path에 추가
import os
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
os.chdir(_root)

# pyupbit/upbit 의존성 모킹 후 upbit_bot 임포트
with patch.dict("sys.modules", {"pyupbit": MagicMock(), "dotenv": MagicMock()}):
    with patch("upbit_bot.upbit", MagicMock()):
        import upbit_bot as bot


def test_get_target_price_formula():
    """목표가 = 당일 시가 + (전일 고가 - 전일 저가) * k (백테스트와 동일)."""
    # get_ohlcv 오름차순: iloc[0]=어제, iloc[1]=오늘
    df = pd.DataFrame(
        {
            "open": [100, 102],
            "high": [110, 115],
            "low": [95, 100],
            "close": [108, 112],
        },
        index=pd.DatetimeIndex(["2025-03-13 09:00:00", "2025-03-14 09:00:00"]),
    )
    with patch.object(bot, "get_ohlcv_or_none", return_value=df):
        target = bot.get_target_price("KRW-BTC", k=0.5)
    # 어제 range = (110-95)*0.5 = 7.5, 오늘 시가 = 102 → 102 + 7.5 = 109.5
    assert target == 109.5


def test_get_target_price_uses_yesterday_and_today():
    """2일치가 없으면 None 반환 (기존 잘못된 1일만 쓰는 경우 방지)."""
    df_one = pd.DataFrame(
        {"open": [100], "high": [110], "low": [90], "close": [105]},
        index=pd.DatetimeIndex(["2025-03-14 09:00:00"]),
    )
    with patch.object(bot, "get_ohlcv_or_none", return_value=df_one):
        target = bot.get_target_price("KRW-BTC", k=0.5)
    assert target is None


def test_min_return_to_sell_constant():
    """수수료 감안 최소 수익률 상수 존재 및 0.1% 이상."""
    assert hasattr(bot, "MIN_RETURN_TO_SELL")
    assert bot.MIN_RETURN_TO_SELL >= 0.001


def test_stop_loss_constant():
    """손절 비율 상수 존재 (기본 -3%)."""
    assert hasattr(bot, "STOP_LOSS_PCT")
    assert bot.STOP_LOSS_PCT == 0.03


def test_get_avg_buy_price_returns_float_or_none():
    """get_avg_buy_price는 float 또는 None 반환."""
    with patch.object(bot.upbit, "get_balances", return_value=[]):
        assert bot.get_avg_buy_price("BTC") is None

    with patch.object(
        bot.upbit,
        "get_balances",
        return_value=[{"currency": "BTC", "balance": "0.001", "avg_buy_price": "95000000"}],
    ):
        assert bot.get_avg_buy_price("BTC") == 95000000.0

    with patch.object(
        bot.upbit,
        "get_balances",
        return_value=[{"currency": "BTC", "balance": "0", "avg_buy_price": ""}],
    ):
        assert bot.get_avg_buy_price("BTC") is None
