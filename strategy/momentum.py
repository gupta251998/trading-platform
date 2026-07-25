"""Momentum Strategy"""
import numpy as np
from strategy.base import StrategyBase, TradeCandidate, Direction

class MomentumStrategy(StrategyBase):
    """Follow strong momentum moves"""
    
    def __init__(self, period=14):
        super().__init__()
        self.period = period
        self.name = "momentum"
    
    def generate_signal(self, symbol, candles):
        if len(candles) < self.period + 1:
            return None
        
        closes = np.array([c['close'] for c in candles])
        volumes = np.array([c['volume'] for c in candles])
        
        momentum = closes[-1] - closes[-self.period]
        momentum_pct = (momentum / closes[-self.period]) * 100
        
        avg_volume = np.mean(volumes[-self.period:])
        current_volume = volumes[-1]
        
        if momentum_pct > 2 and current_volume > avg_volume * 1.2:
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.LONG,
                entry_price=closes[-1],
                stop_loss=closes[-1] * 0.96,
                profit_target=closes[-1] * 1.06,
                confidence=0.75,
                strategy_name=self.name,
                risk_reward_ratio=1.5
            )
        
        if momentum_pct < -2 and current_volume > avg_volume * 1.2:
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.SHORT,
                entry_price=closes[-1],
                stop_loss=closes[-1] * 1.04,
                profit_target=closes[-1] * 0.94,
                confidence=0.75,
                strategy_name=self.name,
                risk_reward_ratio=1.5
            )
        return None
