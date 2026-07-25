"""RSI Strategy"""
import numpy as np
from strategy.base import StrategyBase, TradeCandidate, Direction

class RSIStrategy(StrategyBase):
    """RSI-based mean reversion"""
    
    def __init__(self, period=14, oversold=30, overbought=70):
        super().__init__()
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.name = "rsi"
    
    def calculate_rsi(self, closes):
        deltas = np.diff(closes)
        seed = deltas[:self.period+1]
        up = seed[seed >= 0].sum() / self.period
        down = -seed[seed < 0].sum() / self.period
        
        rs = up / (down + 0.0001)
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def generate_signal(self, symbol, candles):
        if len(candles) < self.period + 5:
            return None
        
        closes = np.array([c['close'] for c in candles])
        current = closes[-1]
        rsi = self.calculate_rsi(closes)
        
        if rsi < self.oversold:
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.LONG,
                entry_price=current,
                stop_loss=current * 0.95,
                profit_target=current * 1.04,
                confidence=0.68,
                strategy_name=self.name,
                risk_reward_ratio=1.3
            )
        
        if rsi > self.overbought:
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.SHORT,
                entry_price=current,
                stop_loss=current * 1.05,
                profit_target=current * 0.96,
                confidence=0.68,
                strategy_name=self.name,
                risk_reward_ratio=1.3
            )
        return None
