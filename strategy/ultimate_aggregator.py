"""Ultimate Multi-Strategy Aggregator - with diagnostic visibility"""
import json
from datetime import datetime, timezone

class UltimateAggregator:
    def __init__(self, strategies):
        self.strategies = strategies
        self.confidence_threshold = 0.80
        self.name = "ultimate_aggregator"

    def _log(self, message):
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "DEBUG",
            "message": message
        }), flush=True)

    def generate_signal(self, symbol, candles):
        signals = []
        confidences = []
        fired_strategies = []

        for strategy in self.strategies:
            try:
                signal = strategy.generate_signal(symbol, candles)
                if signal:
                    signals.append(signal)
                    confidences.append(signal.confidence)
                    fired_strategies.append(strategy.name)
            except Exception:
                continue

        if len(signals) == 0:
            return None

        if len(signals) < 3:
            self._log(f"{symbol}: only {len(signals)}/6 strategies fired ({fired_strategies}) — need 3+")
            return None

        first_direction = signals[0].direction
        agreement_count = sum(1 for s in signals if s.direction == first_direction)

        if agreement_count < len(signals) * 0.7:
            self._log(f"{symbol}: {len(signals)} fired but disagree on direction — skipped")
            return None

        avg_confidence = sum(confidences) / len(confidences)

        if avg_confidence < self.confidence_threshold:
            self._log(f"{symbol}: {len(signals)}/6 agreed ({fired_strategies}) but confidence {avg_confidence:.0%} < 80% threshold")
            return None

        best_signal = max(signals, key=lambda s: s.confidence)
        best_signal.confidence = min(avg_confidence, 0.92)
        return best_signal
