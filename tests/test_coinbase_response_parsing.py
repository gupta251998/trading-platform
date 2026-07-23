"""
Regression tests for CoinbaseAdvancedBroker's response parsing.

These build real SDK response objects (coinbase.rest.types.*) rather than
plain dicts, because the SDK mixes typed-object and raw-dict fields
inconsistently — a bug (get_quote crashing with "'PriceBook' object has
no attribute 'get'") slipped through earlier because MockBroker only
exercises BrokerInterface, never CoinbaseAdvancedBroker's own parsing
logic. No real network calls are made — only the SDK's response
constructors, which is what actually determines object shape.
"""

from unittest.mock import MagicMock

import pytest
from coinbase.rest.types.accounts_types import ListAccountsResponse
from coinbase.rest.types.orders_types import CreateOrderResponse, GetOrderResponse
from coinbase.rest.types.product_types import GetBestBidAskResponse, GetProductCandlesResponse

from broker.coinbase_advanced import CoinbaseAdvancedBroker
from broker.types import BrokerConnectionError, OrderRejectedError, OrderRequest, OrderSide, OrderType


def make_broker():
    broker = CoinbaseAdvancedBroker.__new__(CoinbaseAdvancedBroker)
    broker.paper_mode = True
    broker.default_quote_asset = "USD"
    broker._client = MagicMock()
    return broker


class TestGetQuote:
    def test_parses_real_pricebook_response(self):
        broker = make_broker()
        broker._client.get_best_bid_ask.return_value = GetBestBidAskResponse({
            "pricebooks": [{
                "product_id": "BTC-USD",
                "bids": [{"price": "65000.50", "size": "0.5"}],
                "asks": [{"price": "65001.25", "size": "0.3"}],
                "time": {},
            }]
        })
        quote = broker.get_quote("BTC-USD")
        assert quote.bid == 65000.50
        assert quote.ask == 65001.25
        assert quote.last == pytest.approx(65000.875)

    def test_raises_cleanly_on_empty_pricebooks(self):
        broker = make_broker()
        broker._client.get_best_bid_ask.return_value = GetBestBidAskResponse({"pricebooks": []})
        with pytest.raises(BrokerConnectionError):
            broker.get_quote("BTC-USD")


class TestGetBalances:
    def test_parses_real_accounts_response(self):
        broker = make_broker()
        broker._client.get_accounts.return_value = ListAccountsResponse({
            "accounts": [
                {
                    "uuid": "abc", "currency": "USD",
                    "available_balance": {"value": "1000.50", "currency": "USD"},
                    "hold": {"value": "0", "currency": "USD"},
                },
                {
                    "uuid": "def", "currency": "BTC",
                    "available_balance": {"value": "0.25", "currency": "BTC"},
                    "hold": {"value": "0.01", "currency": "BTC"},
                },
                {
                    "uuid": "ghi", "currency": "ETH",
                    "available_balance": {"value": "0", "currency": "ETH"},
                    "hold": {"value": "0", "currency": "ETH"},
                },
            ]
        })
        balances = broker.get_balances()
        by_asset = {b.asset: b for b in balances}
        assert by_asset["USD"].free == 1000.50
        assert by_asset["BTC"].free == 0.25
        assert by_asset["BTC"].locked == 0.01
        assert "ETH" not in by_asset  # zero balance, filtered out


class TestGetOrder:
    def test_parses_market_order_response(self):
        broker = make_broker()
        broker._client.get_order.return_value = GetOrderResponse({
            "order": {
                "order_id": "order-123",
                "product_id": "BTC-USD",
                "side": "BUY",
                "status": "FILLED",
                "order_type": "MARKET",
                "client_order_id": "client-abc",
                "filled_size": "0.1",
                "average_filled_price": "65000.0",
                "order_configuration": {
                    "market_market_ioc": {"base_size": "0.1"}
                },
            }
        })
        order = broker.get_order("order-123")
        assert order.broker_order_id == "order-123"
        assert order.symbol == "BTC-USD"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 0.1
        assert order.filled_quantity == 0.1
        assert order.avg_fill_price == 65000.0

    def test_parses_limit_order_response(self):
        broker = make_broker()
        broker._client.get_order.return_value = GetOrderResponse({
            "order": {
                "order_id": "order-456",
                "product_id": "ETH-USD",
                "side": "SELL",
                "status": "OPEN",
                "order_type": "LIMIT",
                "order_configuration": {
                    "limit_limit_gtc": {"base_size": "2.0", "limit_price": "3000.0"}
                },
            }
        })
        order = broker.get_order("order-456")
        assert order.side == OrderSide.SELL
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == 2.0


class TestPlaceOrder:
    def test_refuses_in_paper_mode(self):
        broker = make_broker()
        broker.paper_mode = True
        req = OrderRequest(symbol="BTC-USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.1)
        with pytest.raises(Exception):
            broker.place_order(req)
        broker._client.market_order_buy.assert_not_called()

    def test_parses_success_response_and_fetches_order(self):
        broker = make_broker()
        broker.paper_mode = False
        broker._client.market_order_buy.return_value = CreateOrderResponse({
            "success": True,
            "success_response": {"order_id": "order-789", "product_id": "BTC-USD", "side": "BUY"},
        })
        broker._client.get_order.return_value = GetOrderResponse({
            "order": {
                "order_id": "order-789", "product_id": "BTC-USD", "side": "BUY",
                "status": "FILLED", "order_type": "MARKET",
                "order_configuration": {"market_market_ioc": {"base_size": "0.1"}},
            }
        })
        req = OrderRequest(symbol="BTC-USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.1)
        order = broker.place_order(req)
        assert order.broker_order_id == "order-789"

    def test_raises_on_rejected_order(self):
        broker = make_broker()
        broker.paper_mode = False
        broker._client.market_order_buy.return_value = CreateOrderResponse({
            "success": False,
            "error_response": {"error": "INSUFFICIENT_FUND", "message": "not enough balance"},
        })
        req = OrderRequest(symbol="BTC-USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        with pytest.raises(OrderRejectedError):
            broker.place_order(req)


class TestGetCandles:
    def test_parses_real_candles_response(self):
        broker = make_broker()
        broker._client.get_public_candles.return_value = GetProductCandlesResponse({
            "candles": [
                {"start": "1700000000", "low": "64000", "high": "65000",
                 "open": "64500", "close": "64800", "volume": "10.5"},
                {"start": "1700003600", "low": "64800", "high": "65500",
                 "open": "64800", "close": "65200", "volume": "12.1"},
            ]
        })
        candles = broker.get_candles("BTC-USD", granularity="ONE_HOUR", limit=2)
        assert len(candles) == 2
        assert candles[0]["close"] == 64800.0
        assert candles[0]["start"] < candles[1]["start"]  # sorted oldest first
