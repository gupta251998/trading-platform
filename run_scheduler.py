"""
Continuous multi-symbol paper trading runner.

Usage:
    cp .env.example .env       # fill in COINBASE_API_KEY / COINBASE_API_SECRET
    pip install -r requirements.txt
    python run_scheduler.py

Stop with Ctrl+C (SIGINT) or SIGTERM — both trigger a graceful shutdown
that logs a final portfolio report before exiting. This process NEVER
places live orders (see scheduler/multi_symbol_scheduler.py and
paper_trading/engine.py docstrings for the safety guarantees).
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from broker.coinbase_advanced import CoinbaseAdvancedBroker
from notifications.telegram_notifier import TelegramNotifier
from paper_trading.engine import PositionSizeConfig
from scheduler.multi_symbol_scheduler import MultiSymbolScheduler
from strategy.sma_crossover import SmaCrossoverStrategy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_scheduler")


def parse_symbols(raw: str) -> list:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def _start_dashboard(runner: MultiSymbolScheduler) -> None:
    """
    Run the FastAPI dashboard in a background daemon thread inside this
    same process, reading directly from `runner`'s in-memory state. This
    is why it's a thread, not a separate process: a separate process
    would have no access to the live scheduler object without a DB or
    IPC layer neither of which exist yet (see README persistence TODO).
    """
    import uvicorn
    from dashboard.app import create_app

    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("DASHBOARD_PORT", "8000"))

    app = create_app(runner)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    logger.info("Dashboard running at http://%s:%d", host, port)


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

    symbols = parse_symbols(os.getenv("SYMBOLS", os.getenv("SYMBOL", "BTC-USD,ETH-USD")))
    granularity = os.getenv("GRANULARITY", "ONE_HOUR")
    candle_limit = int(os.getenv("CANDLE_LIMIT", "200"))
    starting_cash = float(os.getenv("STARTING_CASH", "10000"))
    poll_interval_seconds = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

    broker = CoinbaseAdvancedBroker(api_key=api_key, api_secret=api_secret, paper_mode=True)

    health = broker.check_health()
    if not health.connected:
        logger.error("Cannot reach Coinbase: %s", health.message)
        sys.exit(1)
    logger.info("Broker connected (latency %sms). Symbols: %s. Poll every %ds.",
                health.latency_ms, symbols, poll_interval_seconds)

    strategy = SmaCrossoverStrategy(fast_period=10, slow_period=30)

    notifiers = []
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if telegram_token and telegram_chat_id:
        notifiers.append(TelegramNotifier(bot_token=telegram_token, chat_id=telegram_chat_id))
        logger.info("Telegram notifications enabled.")
    else:
        logger.info("Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset) — skipping.")

    runner = MultiSymbolScheduler(
        broker=broker,
        strategy=strategy,
        symbols=symbols,
        granularity=granularity,
        candle_limit=candle_limit,
        starting_cash=starting_cash,
        sizing=PositionSizeConfig(risk_per_trade_pct=1.0, max_position_pct=20.0),
        notifiers=notifiers,
    )
    runner.poll_interval_seconds = poll_interval_seconds  # surfaced in dashboard /api/summary

    if os.getenv("DASHBOARD_ENABLED", "true").lower() == "true":
        _start_dashboard(runner)

    # max_instances=1 means if a cycle somehow takes longer than the poll
    # interval, APScheduler skips the overlapping run instead of stacking
    # concurrent cycles against the same shared portfolio.
    scheduler = BlockingScheduler(executors={"default": ThreadPoolExecutor(1)})
    scheduler.add_job(
        runner.run_full_cycle,
        trigger="interval",
        seconds=poll_interval_seconds,
        max_instances=1,
        coalesce=True,
        next_run_time=None,  # set explicitly below so the first run fires immediately
        id="paper_trading_cycle",
    )
    # Fire the first cycle right away rather than waiting a full interval.
    import datetime as _dt
    scheduler.modify_job("paper_trading_cycle", next_run_time=_dt.datetime.now())

    def _graceful_shutdown(signum, frame):
        logger.info("Received signal %s — shutting down after current cycle...", signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    try:
        scheduler.start()
    finally:
        logger.info("Final portfolio report: %s", runner.final_report())
        logger.info("Scheduler stopped after %d cycles.", runner.tick_count)


if __name__ == "__main__":
    main()
