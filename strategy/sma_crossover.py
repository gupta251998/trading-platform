"""SMA Crossover Strategy"""
import numpy as np
from strategy.base import StrategyBase, TradeCandidate, Direction

class SmaCrossoverStrategy(StrategyBase):
    """Simple Moving Average Crossover Strategy"""
    
    def __init__(self, short_period=10, long_period=50):
        super().__init__()
        self.short_period = short_period
        self.long_period = long_period
        self.name = "sma_crossover"
    
    def generate_signal(self, symbol, candles):
        """Generate buy/sell signals based on SMA crossover"""
        if len(candles) < self.long_period:
            return None
        
        try:
            closes = np.array([c['close'] for c in candles])
            
            # Calculate SMAs
            short_sma = np.mean(closes[-self.short_period:])
            long_sma = np.mean(closes[-self.long_period:])
            current_price = closes[-1]
            
            # Previous values for crossover detection
            if len(closes) >= self.long_period + 1:
                prev_short = np.mean(closes[-(self.short_period+1):-1])
                prev_long = np.mean(closes[-(self.long_period+1):-1])
            else:
                return None
            
            # Calculate volatility for confidence
            volatility = np.std(closes[-20:]) / np.mean(closes[-20:])
            confidence = min(0.75, 0.5 + volatility)
            
            # Buy Signal: Short SMA crosses above Long SMA
            if prev_short <= prev_long and short_sma > long_sma:
                return TradeCandidate(
                    symbol=symbol,
                    direction=Direction.LONG,
                    entry_price=current_price,
                    stop_loss=current_price * 0.98,  # 2% stop
                    profit_target=current_price * 1.03,  # 3% target
                    confidence=min(confidence, 0.72),
                    strategy_name=self.name,
                    risk_reward_ratio=1.5
                )
            
            # Sell Signal: Short SMA crosses below Long SMA
            if prev_short >= prev_long and short_sma < long_sma:
                return TradeCandidate(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    entry_price=current_price,
                    stop_loss=current_price * 1.02,
                    profit_target=current_price * 0.97,
                    confidence=min(confidence, 0.72),
                    strategy_name=self.name,
                    risk_reward_ratio=1.5
                )
        
        except Exception as e:
            return None
        
        return None
