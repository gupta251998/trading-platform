"""Real Coinbase Advanced Trade broker using official SDK"""
import os
import json
from datetime import datetime, timezone, timedelta
from coinbase.rest import RESTClient


def _to_dict(obj):
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return obj


class CoinbaseLiveBroker:
    def __init__(self):
        api_key = (os.getenv("COINBASE_API_KEY") or "").strip()
        api_secret = (os.getenv("COINBASE_API_SECRET") or "").strip()
        if not api_key or not api_secret:
            raise ValueError("COINBASE_API_KEY / COINBASE_API_SECRET not set")
        self.client = RESTClient(api_key=api_key, api_secret=api_secret)
        self.paper_mode = False

    def get_accounts(self):
        resp = _to_dict(self.client.get_accounts())
        return resp.get("accounts", [])

    def get_usdt_balance(self):
        for acc in self.get_accounts():
            acc = _to_dict(acc)
            if acc.get("currency") in ("USDT", "USD"):
                bal = _to_dict(acc.get("available_balance", {}))
                return float(bal.get("value", 0))
        return 0.0

    def get_candles(self, symbol, granularity="ONE_HOUR", limit=100):
        granularity_seconds = {
            "ONE_MINUTE": 60, "FIVE_MINUTE": 300, "FIFTEEN_MINUTE": 900,
            "ONE_HOUR": 3600, "SIX_HOUR": 21600, "ONE_DAY": 86400
        }.get(granularity, 3600)

        end = datetime.now(timezone.utc)
        start = end - timedelta(seconds=granularity_seconds * limit)

        try:
            resp = _to_dict(self.client.get_candles(
                product_id=symbol,
                start=str(int(start.timestamp())),
                end=str(int(end.timestamp())),
                granularity=granularity
            ))
            raw_candles = resp.get("candles", [])
        except Exception as e:
            print(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "ERROR",
                "message": f"get_candles failed for {symbol}: {e}"
            }), flush=True)
            return []

        candles = []
        for c in raw_candles:
            c = _to_dict(c)
            candles.append({
                "open": float(c.get("open", 0)),
                "high": float(c.get("high", 0)),
                "low": float(c.get("low", 0)),
                "close": float(c.get("close", 0)),
                "volume": float(c.get("volume", 0)),
            })
        candles.reverse()
        return candles

    def get_product_min_size(self, symbol):
        """Fetch minimum quote size Coinbase requires for this product"""
        try:
            product = _to_dict(self.client.get_product(product_id=symbol))
            quote_min = product.get("quote_min_size")
            return float(quote_min) if quote_min else 1.0
        except Exception:
            return 1.0

    def place_market_order(self, symbol, side, quote_size=None, base_size=None):
        """Place a real market order. Explicitly checks Coinbase's 'success' field —
        does NOT assume success just because a response object was returned."""
        order_config = {}
        if side.upper() == "BUY":
            order_config = {"market_market_ioc": {"quote_size": str(quote_size)}}
        else:
            order_config = {"market_market_ioc": {"base_size": str(base_size)}}

        client_order_id = f"bot_{int(datetime.now(timezone.utc).timestamp() * 1000)}"

        try:
            resp = _to_dict(self.client.create_order(
                client_order_id=client_order_id,
                product_id=symbol,
                side=side.upper(),
                order_configuration=order_config
            ))

            success = resp.get("success", False)

            if not success:
                error_info = resp.get("error_response", {})
                reason = error_info.get("preview_failure_reason") or error_info.get("error") or "unknown"
                print(json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "ERROR",
                    "message": f"Order REJECTED by Coinbase for {symbol}: {reason}"
                }), flush=True)
                return None

            order_id = resp.get("order_id") or resp.get("success_response", {}).get("order_id", "unknown")
            print(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "INFO",
                "message": f"Order CONFIRMED by Coinbase for {symbol}: order_id={order_id}"
            }), flush=True)
            return resp

        except Exception as e:
            print(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "ERROR",
                "message": f"place_market_order exception for {symbol}: {e}"
            }), flush=True)
            return None
