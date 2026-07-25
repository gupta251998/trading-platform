"""Mean Reversion Strategy"""
import numpy as np
from strategy.base import StrategyBase, TradeCandidate, Direction

class MeanReversionStrategy(StrategyBase):
    """Buy dips (oversold), sell rallies (overbought)"""
    
    def __init__(self, short_period=10, long_period=50):
        super().__init__()
        self.short_period = short_period
        self.long_period = long_period
        self.name = "mean_reversion"
    
    def generate_signal(self, symbol, candles):
        if len(candles) < self.long_period:
            return None
        
        closes = np.array([c['close'] for c in candles])
        short_ma = np.mean(closes[-self.short_period:])
        long_ma = np.mean(closes[-self.long_period:])
        current = closes[-1]
        volatility = np.std(closes[-20:]) / long_ma
        
        if volatility > 0.01:
            if current < short_ma * 0.98 and short_ma < long_ma:
                return TradeCandidate(
                    symbol=symbol,
                    direction=Direction.LONG,
                    entry_price=current,
                    stop_loss=current * 0.97,
                    profit_target=short_ma,
                    confidence=0.65,
                    strategy_name=self.name,
                    risk_reward_ratio=1.5
                )
            
            if current > short_ma * 1.02 and short_ma > long_ma:
                return TradeCandidate(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    entry_price=current,
                    stop_loss=current * 1.03,
                    profit_target=short_ma,
                    confidence=0.65,
                    strategy_name=self.name,
                    risk_reward_ratio=1.5
                )
        return None
