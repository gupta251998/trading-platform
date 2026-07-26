"""Single-Strategy Mode - diagnostic: uses ONE strategy only, no voting required"""
import json
from datetime import datetime, timezone

class UltimateAggregator:
    def __init__(self, strategies):
        # In single-strategy mode, only the first strategy in the list is used
        self.strategies = strategies
        self.active_strategy = strategies[0] if strategies else None
        self.name = "single_strategy_diagnostic"

    def _log(self, message):
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "DEBUG",
            "message": message
        }), flush=True)

    def generate_signal(self, symbol, candles):
        if not self.active_strategy:
            return None

        try:
            signal = self.active_strategy.generate_signal(symbol, candles)
        except Exception as e:
            self._log(f"{symbol}: {self.active_strategy.name} errored: {e}")
            return None

        if signal:
            self._log(f"{symbol}: {self.active_strategy.name} FIRED - direction={signal.direction.value}, confidence={signal.confidence:.0%}")
            return signal
        else:
            self._log(f"{symbol}: {self.active_strategy.name} - no signal this cycle")
            return None
