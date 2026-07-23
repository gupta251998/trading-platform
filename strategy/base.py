"""
Strategy layer.

A Strategy consumes price history and emits TradeCandidate objects with a
confidence score derived only from the strategy's own predefined metrics
(never from an LLM). Claude's role is to *explain* a candidate after the
fact — never to generate or score it. That separation is intentional and
should not be collapsed later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from broker.types import OrderSide


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class PriceBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TradeCandidate:
    symbol: str
    market: str
    timeframe: str
    direction: Direction
    entry_zone: tuple  # (low, high)
    stop_loss: float
    profit_target: float
    strategy_name: str
    confidence: float  # 0-1, from strategy's own metrics only
    technical_explanation: str
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def risk_reward_ratio(self) -> float:
        entry_mid = sum(self.entry_zone) / 2
        risk = abs(entry_mid - self.stop_loss)
        reward = abs(self.profit_target - entry_mid)
        return round(reward / risk, 2) if risk > 0 else 0.0

    @property
    def order_side(self) -> OrderSide:
        return OrderSide.BUY if self.direction == Direction.LONG else OrderSide.SELL


class Strategy(ABC):
    """Base class every predefined strategy implements."""

    name: str = "base_strategy"

    @abstractmethod
    def evaluate(self, symbol: str, bars: List[PriceBar]) -> Optional[TradeCandidate]:
        """
        Evaluate the latest bars and return a TradeCandidate if the
        strategy's entry conditions are met, else None.
        """

    @abstractmethod
    def historical_stats(self) -> dict:
        """
        Return this strategy's own tracked historical performance
        (win_rate, avg_return, sharpe, etc.) — populated by the paper
        trading engine over time, read here for display alongside new
        candidates.
        """
