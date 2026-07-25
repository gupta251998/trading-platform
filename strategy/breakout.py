"""Breakout Strategy"""
import numpy as np
from strategy.base import StrategyBase, TradeCandidate, Direction

class BreakoutStrategy(StrategyBase):
    """Break above resistance or below support"""
    
    def __init__(self, period=20, breakout_pct=0.02):
        super().__init__()
        self.period = period
        self.breakout_pct = breakout_pct
        self.name = "breakout"
    
    def generate_signal(self, symbol, candles):
        if len(candles) < self.period:
            return None
        
        closes = np.array([c['close'] for c in candles])
        highs = np.array([c['high'] for c in candles])
        lows = np.array([c['low'] for c in candles])
        
        resistance = np.max(highs[-self.period:])
        support = np.min(lows[-self.period:])
        current = closes[-1]
        
        if current > resistance * (1 + self.breakout_pct):
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.LONG,
                entry_price=current,
                stop_loss=support,
                profit_target=current * 1.05,
                confidence=0.70,
                strategy_name=self.name,
                risk_reward_ratio=2.0
            )
        
        if current < support * (1 - self.breakout_pct):
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.SHORT,
                entry_price=current,
                stop_loss=resistance,
                profit_target=current * 0.95,
                confidence=0.70,
                strategy_name=self.name,
                risk_reward_ratio=2.0
            )
        return None
