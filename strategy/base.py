"""Base Strategy Class"""
from models.all import TradeCandidate, Direction

class StrategyBase:
    """Base class for all trading strategies"""
    
    def __init__(self):
        self.name = "base_strategy"
    
    def generate_signal(self, symbol, candles):
        """Generate trading signal - override in subclass"""
        return None

# Export for backward compatibility
__all__ = ['StrategyBase', 'TradeCandidate', 'Direction']
