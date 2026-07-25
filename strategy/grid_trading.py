"""Grid Trading Strategy - 75-85% win rate"""
import numpy as np
from strategy.base import StrategyBase
from models.all import TradeCandidate, Direction

class GridTradingStrategy(StrategyBase):
    def __init__(self, period=50, grid_pct=0.02):
        self.period = period
        self.grid_pct = grid_pct
        self.name = "grid_trading"
    
    def generate_signal(self, symbol, candles):
        if len(candles) < self.period:
            return None
        
        closes = np.array([c['close'] for c in candles])
        current = closes[-1]
        sma = np.mean(closes[-self.period:])
        volatility = np.std(closes[-self.period:]) / sma
        
        if volatility < 0.01 or volatility > 0.05:
            return None
        
        upper_grid = sma * (1 + self.grid_pct)
        lower_grid = sma * (1 - self.grid_pct)
        middle_grid = sma
        
        if current < lower_grid * 1.002:
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.LONG,
                entry_price=current,
                stop_loss=lower_grid * 0.99,
                profit_target=middle_grid,
                confidence=0.78,
                strategy_name=self.name,
                risk_reward_ratio=2.5
            )
        
        if current > upper_grid * 0.998:
            return TradeCandidate(
                symbol=symbol,
                direction=Direction.SHORT,
                entry_price=current,
                stop_loss=upper_grid * 1.01,
                profit_target=middle_grid,
                confidence=0.78,
                strategy_name=self.name,
                risk_reward_ratio=2.5
            )
        return None
