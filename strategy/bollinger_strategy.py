"""Bollinger Bands Strategy"""
import numpy as np
from strategy.base import StrategyBase, TradeCandidate, Direction

class BollingerStrategy(StrategyBase):
    """Trade Bollinger Bands breakouts"""
    
    def __init__(self, period=20, std_dev=2):
        super().__init__()
        self.period = period
        self.std_dev = std_dev
        self.name = "bollinger"
    
    def generate_signal(self, symbol, candles):
        if len(candles) < self.period:
            return None
        
        closes = np.array([c['close'] for c in candles])
        
        sma = np.mean(closes[-self.period:])
        std = np.std(closes[-self.period:])
        upper_band = sma + (self.std_dev * std)
        lower_band = sma - (self.std_dev * std)
        current = closes[-1]
        
        if current < lower_band * 1.01:
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.LONG,
                entry_price=current,
                stop_loss=lower_band,
                profit_target=sma,
                confidence=0.72,
                strategy_name=self.name,
                risk_reward_ratio=1.4
            )
        
        if current > upper_band * 0.99:
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.SHORT,
                entry_price=current,
                stop_loss=upper_band,
                profit_target=sma,
                confidence=0.72,
                strategy_name=self.name,
                risk_reward_ratio=1.4
            )
        return None
