"""
Mock broker adapter — deterministic, no network calls. Used by the test
suite and for local development before Coinbase API keys are configured.

Feed it a price series via `set_price` and it behaves like a real
adapter for everything the paper trading engine touches.
"""

from __future__ import annotations

from typing import List, Optional

from broker.interface import BrokerInterface
from broker.types import (
    Balance,
    ConnectionHealth,
    Order,
    OrderRequest,
    OrderStatus,
    Position,
    Quote,
)


class MockBroker(BrokerInterface):
    name = "mock"

    def __init__(self, paper_mode: bool = True, starting_prices: Optional[dict] = None):
        super().__init__(paper_mode=paper_mode)
        self._prices = dict(starting_prices or {})
        self._orders: dict = {}

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    def authenticate(self) -> bool:
        return True

    def check_health(self) -> ConnectionHealth:
        return ConnectionHealth(connected=True, broker_name=self.name, latency_ms=1.0, message="ok")

    def get_balances(self) -> List[Balance]:
        return [Balance(asset="USD", free=10_000.0)]

    def get_buying_power(self, quote_asset: str = "USD") -> float:
        return 10_000.0

    def get_positions(self) -> List[Position]:
        return []

    def get_quote(self, symbol: str) -> Quote:
        price = self._prices.get(symbol, 100.0)
        return Quote(symbol=symbol, bid=price * 0.999, ask=price * 1.001, last=price)

    def place_order(self, request: OrderRequest) -> Order:
        raise RuntimeError("MockBroker.place_order should never be called by the paper trading engine")

    def cancel_order(self, broker_order_id: str) -> bool:
        return True

    def modify_order(self, broker_order_id, limit_price=None, stop_price=None, quantity=None) -> Order:
        raise NotImplementedError

    def get_order(self, broker_order_id: str) -> Order:
        raise NotImplementedError

    def get_order_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Order]:
        return []


    def get_candles(self, symbol: str, granularity: str = "ONE_HOUR", limit: int = 100) -> list:
        """Return mock OHLCV candles."""
        import time
        now = int(time.time())
        candles = []
        base_price = 50000.0 if 'BTC' in symbol else (3000.0 if 'ETH' in symbol else 150.0)
        
        for i in range(limit, 0, -1):
            timestamp = now - (i * 3600)
            candles.append({
                "start": timestamp,
                "open": base_price + (i * 10),
                "high": base_price + (i * 15),
                "low": base_price + (i * 5),
                "close": base_price + (i * 12),
                "volume": 1000.0
            })
        
        return candles

