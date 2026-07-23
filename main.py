"""
Demo runner: pulls real OHLCV candles from Coinbase Advanced (public
endpoint — no auth needed for candles/quotes), runs the SMA crossover
strategy against them, and simulates the trade through the paper trading
engine. This is the smoke test for the whole vertical slice end to end.

Usage:
    cp .env.example .env        # fill in COINBASE_API_KEY / COINBASE_API_SECRET
    pip install -r requirements.txt
    python main.py

Notes:
- get_quote / get_candles work with valid API keys (Coinbase requires
  auth even for "public" market data via this SDK's authenticated
  client). Balances/positions additionally require trade permissions.
- This script NEVER calls place_order. It is paper trading only.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from broker.coinbase_advanced import CoinbaseAdvancedBroker
from paper_trading.engine import PaperTradingEngine, PositionSizeConfig
from paper_trading.portfolio import PaperPortfolio
from strategy.base import PriceBar
from strategy.sma_crossover import SmaCrossoverStrategy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("main")


def main() -> None:
    load_dotenv()

    api_key = os.getenv("COINBASE_API_KEY")
    api_secret = os.getenv("COINBASE_API_SECRET")
    if not api_key or not api_secret:
        logger.error(
            "COINBASE_API_KEY / COINBASE_API_SECRET not set. "
            "Copy .env.example to .env and fill in your CDP API key."
        )
        sys.exit(1)

    live_flag = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
    if live_flag:
        logger.warning(
            "LIVE_TRADING_ENABLED=true is set, but this demo runner only ever "
            "constructs the broker in paper_mode=True — there is no live "
            "execution path wired up in this slice."
        )

    symbol = os.getenv("SYMBOL", "BTC-USD")
    granularity = os.getenv("GRANULARITY", "ONE_HOUR")
    candle_limit = int(os.getenv("CANDLE_LIMIT", "200"))
    starting_cash = float(os.getenv("STARTING_CASH", "10000"))

    broker = CoinbaseAdvancedBroker(api_key=api_key, api_secret=api_secret, paper_mode=True)

    health = broker.check_health()
    logger.info("Broker health: connected=%s latency=%sms", health.connected, health.latency_ms)
    if not health.connected:
        logger.error("Cannot reach Coinbase: %s", health.message)
        sys.exit(1)

    logger.info("Fetching %d %s candles for %s...", candle_limit, granularity, symbol)
    raw_candles = broker.get_candles(symbol, granularity=granularity, limit=candle_limit)
    bars = [
        PriceBar(
            timestamp=datetime.fromtimestamp(c["start"], tz=timezone.utc),
            open=c["open"], high=c["high"],
            low=c["low"], close=c["close"], volume=c["volume"],
        )
        for c in raw_candles
    ]
    logger.info("Got %d bars, latest close: %.2f", len(bars), bars[-1].close if bars else 0)

    strategy = SmaCrossoverStrategy(fast_period=10, slow_period=30)
    portfolio = PaperPortfolio(starting_cash=starting_cash)
    engine = PaperTradingEngine(
        broker=broker,
        strategy=strategy,
        portfolio=portfolio,
        sizing=PositionSizeConfig(risk_per_trade_pct=1.0, max_position_pct=20.0),
    )

    candidate = engine.on_bars(symbol, bars)
    if candidate:
        logger.info("Trade candidate generated:")
        logger.info("  Symbol: %s | Direction: %s | Confidence: %.2f",
                     candidate.symbol, candidate.direction.value, candidate.confidence)
        logger.info("  Entry zone: %.2f - %.2f", *candidate.entry_zone)
        logger.info("  Stop-loss: %.2f | Target: %.2f | R:R %.2f",
                     candidate.stop_loss, candidate.profit_target, candidate.risk_reward_ratio)
        logger.info("  Explanation: %s", candidate.technical_explanation)
    else:
        logger.info("No trade candidate on this bar (no crossover, or position already open).")

    report = engine.performance_report([symbol])
    logger.info("Paper portfolio report: %s", report)


if __name__ == "__main__":
    main()
