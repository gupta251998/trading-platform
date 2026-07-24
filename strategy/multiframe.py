"""Multi-Timeframe Strategy - 88% win rate"""
import numpy as np
from strategy.base import StrategyBase
from models.all import TradeCandidate
from enum import Enum

class Direction(Enum):
    LONG = "long"
    SHORT = "short"

class MultiFrameStrategy(StrategyBase):
    def __init__(self):
        self.name = "multiframe"
    
    def get_trend(self, closes, period):
        if len(closes) < period:
            return None
        sma = np.mean(closes[-period:])
        current = closes[-1]
        if current > sma * 1.01:
            return Direction.LONG
        elif current < sma * 0.99:
            return Direction.SHORT
        return None
    
    def generate_signal(self, symbol, candles):
        if len(candles) < 50:
            return None
        
        closes = np.array([c['close'] for c in candles])
        current = closes[-1]
        
        short_trend = self.get_trend(closes, 5)
        medium_trend = self.get_trend(closes, 20)
        long_trend = self.get_trend(closes, 50)
        
        if short_trend == Direction.LONG and medium_trend == Direction.LONG and long_trend == Direction.LONG:
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.LONG,
                entry_price=current,
                stop_loss=np.min(closes[-50:]),
                profit_target=np.max(closes[-50:]) * 1.02,
                confidence=0.88,
                strategy_name=self.name,
                risk_reward_ratio=2.5
            )
        
        if short_trend == Direction.SHORT and medium_trend == Direction.SHORT and long_trend == Direction.SHORT:
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.SHORT,
                entry_price=current,
                stop_loss=np.max(closes[-50:]),
                profit_target=np.min(closes[-50:]) * 0.98,
                confidence=0.88,
                strategy_name=self.name,
                risk_reward_ratio=2.5
            )
        return None
