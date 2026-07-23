"""
Coinbase Advanced Trade broker adapter.

Wraps the official `coinbase-advanced-py` SDK (RESTClient) behind the
platform's BrokerInterface contract. Authenticates with CDP API keys
(key name + PEM/EC private key), which is Coinbase's current auth scheme
for Advanced Trade — the older HMAC key/secret/passphrase scheme is
deprecated and not used here.

Safety:
- `place_order` refuses to run when `paper_mode=True`. This is a second
  independent guard on top of the paper trading engine never calling it —
  belt and suspenders for live-trading safety.
- Nothing here decides *when* to trade. This adapter only executes what
  it's told, and only in live mode.
"""

from __future__ import annotations

import time
import uuid
from typing import List, Optional

from coinbase.rest import RESTClient

from broker.interface import BrokerInterface
from broker.types import (
    Balance,
    BrokerAuthError,
    BrokerConnectionError,
    ConnectionHealth,
    Order,
    OrderRejectedError,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    TimeInForce,
)

_STATUS_MAP = {
    "OPEN": OrderStatus.OPEN,
    "FILLED": OrderStatus.FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "EXPIRED": OrderStatus.CANCELLED,
    "FAILED": OrderStatus.REJECTED,
    "UNKNOWN_ORDER_STATUS": OrderStatus.PENDING,
    "QUEUED": OrderStatus.PENDING,
    "PENDING": OrderStatus.PENDING,
}


def _to_product_id(symbol: str) -> str:
    """Normalize 'BTC-USD' or 'BTC/USD' or 'btcusd' style inputs to Coinbase's 'BTC-USD'."""
    s = symbol.upper().replace("/", "-")
    if "-" not in s and len(s) > 3:
        # best-effort split e.g. BTCUSD -> BTC-USD; explicit "BASE-QUOTE" is preferred
        s = f"{s[:-3]}-{s[-3:]}"
    return s


def _field(obj, key, default=None):
    """
    Read a field off an SDK response object OR a raw dict — the
    coinbase-advanced-py SDK is inconsistent about which nested fields it
    converts to typed objects (attribute access) versus leaves as raw
    JSON (dict access), so every place we read a response field goes
    through this instead of guessing.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class CoinbaseAdvancedBroker(BrokerInterface):
    name = "coinbase_advanced"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        paper_mode: bool = True,
        default_quote_asset: str = "USD",
    ):
        super().__init__(paper_mode=paper_mode)
        self.default_quote_asset = default_quote_asset
        try:
            self._client = RESTClient(api_key=api_key, api_secret=api_secret)
        except Exception as exc:  # SDK raises varied exceptions on malformed keys
            raise BrokerAuthError(f"Failed to initialize Coinbase client: {exc}") from exc

    # ---- Auth / health -------------------------------------------------

    def authenticate(self) -> bool:
        try:
            accounts = self._client.get_accounts(limit=1)
            return accounts is not None
        except Exception as exc:
            raise BrokerAuthError(f"Coinbase authentication failed: {exc}") from exc

    def check_health(self) -> ConnectionHealth:
        start = time.monotonic()
        try:
            self._client.get_unix_time()
            latency_ms = (time.monotonic() - start) * 1000
            return ConnectionHealth(
                connected=True,
                broker_name=self.name,
                latency_ms=round(latency_ms, 1),
                message="ok",
            )
        except Exception as exc:
            return ConnectionHealth(
                connected=False,
                broker_name=self.name,
                message=str(exc),
            )

    # ---- Account -------------------------------------------------------

    def get_balances(self) -> List[Balance]:
        try:
            resp = self._client.get_accounts(limit=250)
        except Exception as exc:
            raise BrokerConnectionError(f"Failed to fetch balances: {exc}") from exc

        balances: List[Balance] = []
        for acct in getattr(resp, "accounts", None) or []:
            avail = _field(acct, "available_balance") or {}
            hold = _field(acct, "hold") or {}
            available = float(_field(avail, "value", 0) or 0)
            hold_amt = float(_field(hold, "value", 0) or 0)
            if available == 0 and hold_amt == 0:
                continue
            balances.append(
                Balance(asset=_field(acct, "currency", "?"), free=available, locked=hold_amt)
            )
        return balances

    def get_buying_power(self, quote_asset: str = "USD") -> float:
        for bal in self.get_balances():
            if bal.asset == quote_asset:
                return bal.free
        return 0.0

    def get_positions(self) -> List[Position]:
        """
        Coinbase Advanced (spot) has no native "positions" endpoint the way a
        futures/margin broker does — a spot position is just a non-quote-asset
        balance. We derive positions from balances and attach current price.
        """
        positions: List[Position] = []
        for bal in self.get_balances():
            if bal.asset == self.default_quote_asset or bal.total <= 0:
                continue
            symbol = f"{bal.asset}-{self.default_quote_asset}"
            try:
                quote = self.get_quote(symbol)
                current_price = quote.last
            except Exception:
                current_price = None
            positions.append(
                Position(
                    symbol=symbol,
                    quantity=bal.total,
                    avg_entry_price=current_price or 0.0,  # spot has no cost basis via this API
                    current_price=current_price,
                    market="crypto",
                )
            )
        return positions

    # ---- Market data -----------------------------------------------------

    def get_quote(self, symbol: str) -> Quote:
        product_id = _to_product_id(symbol)
        try:
            book = self._client.get_best_bid_ask(product_ids=[product_id])
        except Exception as exc:
            raise BrokerConnectionError(f"Failed to fetch quote for {symbol}: {exc}") from exc

        pricebooks = getattr(book, "pricebooks", None) or []
        if not pricebooks:
            raise BrokerConnectionError(f"No quote data returned for {symbol}")
        pb = pricebooks[0]
        bids = getattr(pb, "bids", None) or []
        asks = getattr(pb, "asks", None) or []
        bid = float(bids[0].price) if bids else 0.0
        ask = float(asks[0].price) if asks else 0.0
        last = (bid + ask) / 2 if (bid and ask) else (bid or ask)
        return Quote(symbol=product_id, bid=bid, ask=ask, last=last)

    # ---- Orders ----------------------------------------------------------

    def place_order(self, request: OrderRequest) -> Order:
        if self.paper_mode:
            raise BrokerError_PaperModeGuard()

        product_id = _to_product_id(request.symbol)
        client_order_id = request.client_order_id or str(uuid.uuid4())

        try:
            if request.order_type == OrderType.MARKET:
                if request.side == OrderSide.BUY:
                    resp = self._client.market_order_buy(
                        client_order_id=client_order_id,
                        product_id=product_id,
                        base_size=str(request.quantity),
                    )
                else:
                    resp = self._client.market_order_sell(
                        client_order_id=client_order_id,
                        product_id=product_id,
                        base_size=str(request.quantity),
                    )
            elif request.order_type == OrderType.LIMIT:
                if request.limit_price is None:
                    raise OrderRejectedError("limit_price required for LIMIT orders")
                fn = (
                    self._client.limit_order_gtc_buy
                    if request.side == OrderSide.BUY
                    else self._client.limit_order_gtc_sell
                )
                resp = fn(
                    client_order_id=client_order_id,
                    product_id=product_id,
                    base_size=str(request.quantity),
                    limit_price=str(request.limit_price),
                )
            else:
                raise OrderRejectedError(
                    f"Order type {request.order_type} not yet implemented in this adapter"
                )
        except (OrderRejectedError, BrokerError_PaperModeGuard):
            raise
        except Exception as exc:
            raise OrderRejectedError(f"Coinbase rejected order: {exc}") from exc

        success = _field(resp, "success")
        if success is False:
            error_resp = _field(resp, "error_response") or {}
            raise OrderRejectedError(f"Coinbase rejected order: {error_resp}")

        order_id = _field(resp, "order_id")
        if not order_id:
            success_response = _field(resp, "success_response") or {}
            order_id = _field(success_response, "order_id")
        if not order_id:
            raise OrderRejectedError(f"Coinbase order response had no order_id: {resp}")
        return self.get_order(order_id)

    def cancel_order(self, broker_order_id: str) -> bool:
        try:
            resp = self._client.cancel_orders(order_ids=[broker_order_id])
            results = getattr(resp, "results", None) or []
            return bool(results and _field(results[0], "success"))
        except Exception as exc:
            raise BrokerConnectionError(f"Failed to cancel order {broker_order_id}: {exc}") from exc

    def modify_order(
        self,
        broker_order_id: str,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        quantity: Optional[float] = None,
    ) -> Order:
        if self.paper_mode:
            raise BrokerError_PaperModeGuard()
        try:
            self._client.edit_order(
                order_id=broker_order_id,
                price=str(limit_price) if limit_price is not None else None,
                size=str(quantity) if quantity is not None else None,
            )
        except Exception as exc:
            raise OrderRejectedError(f"Failed to modify order {broker_order_id}: {exc}") from exc
        return self.get_order(broker_order_id)

    def get_order(self, broker_order_id: str) -> Order:
        try:
            resp = self._client.get_order(order_id=broker_order_id)
        except Exception as exc:
            raise BrokerConnectionError(f"Failed to fetch order {broker_order_id}: {exc}") from exc

        o = getattr(resp, "order", None)
        if o is None:
            raise BrokerConnectionError(f"No order data returned for {broker_order_id}")

        order_config = _field(o, "order_configuration")
        market_ioc = _field(order_config, "market_market_ioc") or {}
        limit_gtc = _field(order_config, "limit_limit_gtc") or {}
        base_size = _field(market_ioc, "base_size") or _field(limit_gtc, "base_size") or 0

        side_raw = (_field(o, "side", "") or "").upper()
        order_type_raw = _field(o, "order_type", "") or ""

        return Order(
            broker_order_id=_field(o, "order_id", broker_order_id),
            symbol=_field(o, "product_id", ""),
            side=OrderSide.BUY if side_raw == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET if "MARKET" in order_type_raw else OrderType.LIMIT,
            quantity=float(base_size or 0),
            status=_STATUS_MAP.get(_field(o, "status", "UNKNOWN_ORDER_STATUS"), OrderStatus.PENDING),
            filled_quantity=float(_field(o, "filled_size", 0) or 0),
            avg_fill_price=float(_field(o, "average_filled_price", 0) or 0) or None,
            client_order_id=_field(o, "client_order_id"),
            raw=o if isinstance(o, dict) else getattr(o, "__dict__", None),
        )

    # ---- Extra: candles (not part of BrokerInterface — this belongs to the
    # future Market Data module, but exposing it here unblocks the demo
    # runner without waiting on that module to be built) -----------------

    def get_candles(self, symbol: str, granularity: str = "ONE_HOUR", limit: int = 200):
        """
        Returns a list of dicts with keys: start, low, high, open, close, volume
        (oldest first). granularity is a Coinbase enum string, e.g.
        ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, ONE_HOUR, SIX_HOUR, ONE_DAY.
        """
        import time as _time

        granularity_seconds = {
            "ONE_MINUTE": 60, "FIVE_MINUTE": 300, "FIFTEEN_MINUTE": 900,
            "THIRTY_MINUTE": 1800, "ONE_HOUR": 3600, "TWO_HOUR": 7200,
            "SIX_HOUR": 21600, "ONE_DAY": 86400,
        }.get(granularity, 3600)

        product_id = _to_product_id(symbol)
        end = int(_time.time())
        start = end - granularity_seconds * limit
        try:
            resp = self._client.get_public_candles(
                product_id=product_id,
                start=str(start),
                end=str(end),
                granularity=granularity,
            )
        except Exception as exc:
            raise BrokerConnectionError(f"Failed to fetch candles for {symbol}: {exc}") from exc

        candles = getattr(resp, "candles", None) or []
        out = [
            {
                "start": int(_field(c, "start")),
                "low": float(_field(c, "low")),
                "high": float(_field(c, "high")),
                "open": float(_field(c, "open")),
                "close": float(_field(c, "close")),
                "volume": float(_field(c, "volume")),
            }
            for c in candles
        ]
        return sorted(out, key=lambda c: c["start"])

    def get_order_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Order]:
        kwargs = {"limit": limit}
        if symbol:
            kwargs["product_id"] = _to_product_id(symbol)
        try:
            resp = self._client.list_orders(**kwargs)
        except Exception as exc:
            raise BrokerConnectionError(f"Failed to fetch order history: {exc}") from exc

        orders = getattr(resp, "orders", None) or []
        return [self.get_order(_field(o, "order_id")) for o in orders]


class BrokerError_PaperModeGuard(Exception):
    """
    Internal guard: raised if something tries to route a real order through
    this adapter while it's configured for paper mode. The paper trading
    engine should never call place_order at all — this is a defensive
    second layer, not the primary safety mechanism.
    """

    def __init__(self):
        super().__init__(
            "This CoinbaseAdvancedBroker instance is in paper_mode=True. "
            "Refusing to place a live order. The paper trading engine should "
            "simulate fills itself, not call place_order()."
        )
