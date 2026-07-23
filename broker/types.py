"""
Shared data types for the Broker Interface layer.

Every broker adapter (Coinbase Advanced, Alpaca, OANDA, etc.) speaks these
types. The rest of the platform (signal engine, paper trading engine,
dashboard) never touches a broker-specific SDK object directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TimeInForce(str, Enum):
    GTC = "gtc"  # good till cancelled
    IOC = "ioc"  # immediate or cancel
    FOK = "fok"  # fill or kill
    DAY = "day"


@dataclass
class Balance:
    asset: str
    free: float
    locked: float = 0.0

    @property
    def total(self) -> float:
        return self.free + self.locked


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: Optional[float] = None
    market: str = "crypto"

    @property
    def market_value(self) -> Optional[float]:
        if self.current_price is None:
            return None
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> Optional[float]:
        if self.current_price is None:
            return None
        return (self.current_price - self.avg_entry_price) * self.quantity


@dataclass
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    client_order_id: Optional[str] = None


@dataclass
class Order:
    broker_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    status: OrderStatus
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    filled_quantity: float = 0.0
    avg_fill_price: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    client_order_id: Optional[str] = None
    raw: Optional[dict] = None  # original broker payload, for debugging/audit


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fee: float
    fee_asset: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


@dataclass
class ConnectionHealth:
    connected: bool
    broker_name: str
    latency_ms: Optional[float] = None
    message: str = ""
    checked_at: datetime = field(default_factory=datetime.utcnow)


class BrokerError(Exception):
    """Base class for all broker adapter errors."""


class BrokerAuthError(BrokerError):
    """Raised when authentication with the broker fails."""


class BrokerConnectionError(BrokerError):
    """Raised when the broker cannot be reached."""


class OrderRejectedError(BrokerError):
    """Raised when the broker rejects an order."""
