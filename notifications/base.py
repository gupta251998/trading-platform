"""
Notifier interface — same pattern as BrokerInterface: the engine talks to
this abstraction, never to a specific channel's SDK. Telegram is the
first implementation; Discord/Slack/Email from the original spec plug in
the same way later without touching the engine.

Notifiers must never raise into the engine. A failed notification (bad
token, Telegram down, rate limited) is a notifier problem, not a trading
problem — the paper trading loop must keep running either way. Each
implementation is responsible for catching its own errors; the engine
calls these best-effort and does not check return values.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from paper_trading.portfolio import ClosedTrade
from strategy.base import TradeCandidate


class Notifier(ABC):
    name: str = "base"

    @abstractmethod
    def notify_candidate_opened(
        self, candidate: TradeCandidate, quantity: float, fill_price: float
    ) -> None:
        """Called when the engine opens a simulated paper position."""

    @abstractmethod
    def notify_position_closed(self, trade: ClosedTrade) -> None:
        """Called when the engine closes a simulated paper position."""

    @abstractmethod
    def notify_symbol_failing(self, symbol: str, consecutive_failures: int, error: Optional[str]) -> None:
        """Called when a symbol has failed several consecutive cycles."""
