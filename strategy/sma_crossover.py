"""
SMA Crossover strategy — the reference implementation used to prove out
the broker + paper trading pipeline end to end. Deliberately simple.

Entry logic:
- LONG when fast SMA crosses above slow SMA on the latest bar
  (fast[-2] <= slow[-2] and fast[-1] > slow[-1])
- Stop-loss: recent swing low minus a buffer (ATR-free, simple % buffer
  for this first slice)
- Profit target: risk multiplied by a fixed reward multiple

Confidence score is derived only from the crossover strength (how far
fast SMA has pulled ahead of slow SMA, normalized) and recent trend
consistency — no discretionary or AI input.
"""

from __future__ import annotations

from typing import List, Optional

from strategy.base import Direction, PriceBar, Strategy, TradeCandidate


def _sma(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    out = []
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        out.append(sum(window) / period)
    return out


class SmaCrossoverStrategy(Strategy):
    name = "sma_crossover"

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 30,
        stop_buffer_pct: float = 0.02,
        reward_multiple: float = 2.0,
        timeframe: str = "1h",
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.stop_buffer_pct = stop_buffer_pct
        self.reward_multiple = reward_multiple
        self.timeframe = timeframe
        self._stats = {
            "win_rate": None,
            "avg_return": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown": None,
            "expectancy": None,
            "profit_factor": None,
            "trade_count": 0,
        }

    def evaluate(self, symbol: str, bars: List[PriceBar]) -> Optional[TradeCandidate]:
        if len(bars) < self.slow_period + 2:
            return None

        closes = [b.close for b in bars]
        fast = _sma(closes, self.fast_period)
        slow = _sma(closes, self.slow_period)

        # Align the two SMA series to the same trailing window
        offset = len(fast) - len(slow)
        fast_aligned = fast[offset:]

        if len(fast_aligned) < 2 or len(slow) < 2:
            return None

        prev_fast, curr_fast = fast_aligned[-2], fast_aligned[-1]
        prev_slow, curr_slow = slow[-2], slow[-1]

        crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        if not crossed_up:
            return None

        last_close = closes[-1]
        recent_low = min(b.low for b in bars[-self.slow_period :])
        stop_loss = min(recent_low, last_close * (1 - self.stop_buffer_pct))
        risk = last_close - stop_loss
        profit_target = last_close + risk * self.reward_multiple

        # Confidence: normalized separation between fast/slow SMA, capped at 1.0
        separation_pct = (curr_fast - curr_slow) / curr_slow if curr_slow else 0
        confidence = max(0.0, min(1.0, separation_pct * 20))  # empirically scaled

        entry_zone = (last_close * 0.999, last_close * 1.001)

        explanation = (
            f"{self.fast_period}-period SMA crossed above {self.slow_period}-period SMA "
            f"on the latest {self.timeframe} bar. Fast SMA: {curr_fast:.2f}, "
            f"Slow SMA: {curr_slow:.2f}, separation: {separation_pct * 100:.2f}%. "
            f"Stop placed at recent {self.slow_period}-bar low with "
            f"{self.stop_buffer_pct * 100:.1f}% buffer. Target set at "
            f"{self.reward_multiple}x risk."
        )

        return TradeCandidate(
            symbol=symbol,
            market="crypto",
            timeframe=self.timeframe,
            direction=Direction.LONG,
            entry_zone=entry_zone,
            stop_loss=round(stop_loss, 2),
            profit_target=round(profit_target, 2),
            strategy_name=self.name,
            confidence=round(confidence, 3),
            technical_explanation=explanation,
        )

    def historical_stats(self) -> dict:
        return dict(self._stats)

    def update_stats(self, stats: dict) -> None:
        """Called by the paper trading engine after closing trades."""
        self._stats.update(stats)
