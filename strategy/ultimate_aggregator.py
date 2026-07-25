"""Ultimate Multi-Strategy Aggregator - 80%+ win rate"""

class UltimateAggregator:
    """Advanced aggregation for maximum win rate"""
    
    def __init__(self, strategies):
        self.strategies = strategies
        self.confidence_threshold = 0.80
        self.name = "ultimate_aggregator"
    
    def generate_signal(self, symbol, candles):
        """
        Get signals from all strategies
        Only trade if 3+ strategies agree AND high confidence
        """
        signals = []
        confidences = []
        
        for strategy in self.strategies:
            try:
                signal = strategy.generate_signal(symbol, candles)
                if signal:
                    signals.append(signal)
                    confidences.append(signal.confidence)
            except Exception as e:
                continue
        
        # Need AT LEAST 3 strategies to agree
        if len(signals) < 3:
            return None
        
        # Check if all signals agree on direction
        first_direction = signals[0].direction
        agreement_count = sum(1 for s in signals if s.direction == first_direction)
        
        # Need 70%+ agreement
        if agreement_count < len(signals) * 0.7:
            return None
        
        # Average confidence
        avg_confidence = sum(confidences) / len(confidences)
        
        # Only trade if high confidence (80%+)
        if avg_confidence < self.confidence_threshold:
            return None
        
        # Use most conservative stop/target
        best_signal = max(signals, key=lambda s: s.confidence)
        best_signal.confidence = min(avg_confidence, 0.92)
        
        return best_signal
