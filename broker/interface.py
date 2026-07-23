"""
Broker Interface — the single contract the rest of the platform depends on.

The signal engine, paper trading engine, and dashboard only ever talk to
this interface. Swapping brokers (Coinbase -> Binance -> Alpaca) is a
config change, never a code change, as long as the adapter implements
this ABC.

Design notes:
- All methods are synchronous for this first slice. If/when the platform
  moves to a fully async FastAPI service, wrap these in a thread executor
  or introduce an AsyncBrokerInterface counterpart — don't silently make
  half the methods async.
- `paper_mode` is a first-class concept on every adapter: read operations
  (quotes, balances, positions) always hit the real broker so paper
  trading uses real market data; `place_order` is short-circuited by the
  paper trading engine and should never reach here when paper_mode=True.
  The flag exists on the adapter so adapters can also refuse to place
  live orders defensively even if miswired.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from broker.types import (
    Balance,
    ConnectionHealth,
    Order,
    OrderRequest,
    Position,
    Quote,
)


class BrokerInterface(ABC):
    """Abstract base class every broker adapter must implement."""

    name: str = "base"

    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode

    # ---- Auth / health -------------------------------------------------

    @abstractmethod
    def authenticate(self) -> bool:
        """Verify credentials are valid. Raises BrokerAuthError on failure."""

    @abstractmethod
    def check_health(self) -> ConnectionHealth:
        """Lightweight connectivity + latency check."""

    # ---- Account ---------------------------------------------------------

    @abstractmethod
    def get_balances(self) -> List[Balance]:
        """Return all asset balances on the account."""

    @abstractmethod
    def get_buying_power(self, quote_asset: str = "USD") -> float:
        """Return available buying power denominated in quote_asset."""

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Return all open positions."""

    # ---- Market data -------------------------------------------------

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """Return the current bid/ask/last for a symbol."""

    # ---- Orders ------------------------------------------------------

    @abstractmethod
    def place_order(self, request: OrderRequest) -> Order:
        """
        Submit an order to the broker.

        Live-trading safety: adapters MUST NOT be called with place_order
        by anything other than the explicit, human-approved execution
        path. The paper trading engine simulates fills itself and should
        not call this method at all.
        """

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an open order. Returns True if cancellation succeeded."""

    @abstractmethod
    def modify_order(
        self,
        broker_order_id: str,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        quantity: Optional[float] = None,
    ) -> Order:
        """Modify an open order's price and/or quantity."""

    @abstractmethod
    def get_order(self, broker_order_id: str) -> Order:
        """Fetch the current state of a single order."""

    @abstractmethod
    def get_order_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Order]:
        """Fetch historical orders, optionally filtered by symbol."""
