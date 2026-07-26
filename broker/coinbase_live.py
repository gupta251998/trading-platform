"""Real Coinbase Advanced Trade broker using official SDK"""
import os
import json
from datetime import datetime, timedelta
from coinbase.rest import RESTClient


def _to_dict(obj):
    """Safely convert SDK response objects to plain dicts"""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return obj


class CoinbaseLiveBroker:
    """Wraps Coinbase Advanced Trade SDK for live account + order operations"""

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
        """Fetch historical candles for a product (e.g. BTC-USDT)"""
        granularity_seconds = {
            "ONE_MINUTE": 60, "FIVE_MINUTE": 300, "FIFTEEN_MINUTE": 900,
            "ONE_HOUR": 3600, "SIX_HOUR": 21600, "ONE_DAY": 86400
        }.get(granularity, 3600)

        end = datetime.utcnow()
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
                "timestamp": datetime.utcnow().isoformat() + "+00:00",
                "level": "ERROR",
                "message": f"get_candles failed for {symbol}: {e}"
            }))
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
        candles.reverse()  # API returns newest first; strategies expect oldest first
        return candles

    def place_market_order(self, symbol, side, quote_size=None, base_size=None):
        """Place a real market order. side = 'BUY' or 'SELL'"""
        order_config = {}
        if side.upper() == "BUY":
            order_config = {"market_market_ioc": {"quote_size": str(quote_size)}}
        else:
            order_config = {"market_market_ioc": {"base_size": str(base_size)}}

        client_order_id = f"bot_{int(datetime.utcnow().timestamp() * 1000)}"

        try:
            resp = _to_dict(self.client.create_order(
                client_order_id=client_order_id,
                product_id=symbol,
                side=side.upper(),
                order_configuration=order_config
            ))
            return resp
        except Exception as e:
            print(json.dumps({
                "timestamp": datetime.utcnow().isoformat() + "+00:00",
                "level": "ERROR",
                "message": f"place_market_order failed for {symbol}: {e}"
            }))
            return None
