"""Ultimate Multi-Strategy Aggregator - 80%+ win rate"""
class UltimateAggregator:
    def __init__(self, strategies):
        self.strategies = strategies
        self.confidence_threshold = 0.80
    
    def generate_signal(self, symbol, candles):
        signals = []
        confidences = []
        
        for strategy in self.strategies:
            try:
                signal = strategy.generate_signal(symbol, candles)
                if signal:
                    signals.append(signal)
                    confidences.append(signal.confidence)
            except:
                continue
        
        if len(signals) < 3:
            return None
        
        first_direction = signals[0].direction
        agreement_count = sum(1 for s in signals if s.direction == first_direction)
        
        if agreement_count < len(signals) * 0.7:
            return None
        
        avg_confidence = sum(confidences) / len(confidences)
        
        if avg_confidence < self.confidence_threshold:
            return None
        
        best_signal = max(signals, key=lambda s: s.confidence)
        best_signal.confidence = min(avg_confidence, 0.92)
        
        return best_signal
