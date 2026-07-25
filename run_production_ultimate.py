#!/usr/bin/env python3
import os
import sys
import threading
import time
from datetime import datetime, timezone
import json

sys.path.insert(0, os.path.dirname(__file__))


def load_env_file():
    """Manually load .env if python-dotenv env vars aren't already set (local dev)"""
    from pathlib import Path
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env_file()


def log_json(message, level="INFO"):
    timestamp = datetime.now(timezone.utc).isoformat()
    print(json.dumps({"timestamp": timestamp, "level": level, "message": message}))


def run_scheduler():
    log_json("🚀 Starting ULTIMATE trading system...")
    try:
        from scheduler.multi_symbol_scheduler import MultiSymbolScheduler
        from strategy.grid_trading import GridTradingStrategy
        from strategy.scalping import ScalpingStrategy
        from strategy.liquid_heatmap import LiquidHeatmapStrategy
        from strategy.multiframe import MultiFrameStrategy
        from strategy.sma_crossover import SmaCrossoverStrategy
        from strategy.mean_reversion import MeanReversionStrategy
        from strategy.ultimate_aggregator import UltimateAggregator
        from paper_trading.portfolio import PaperPortfolio
        from broker.coinbase_live import CoinbaseLiveBroker
        from config import load_config

        config = load_config()
        execution_mode = os.getenv("EXECUTION_MODE", "paper")
        live_enabled = os.getenv("LIVE_TRADING_ENABLED", "false")

        log_json(f"Execution mode: {execution_mode}")
        log_json(f"Live trading enabled: {live_enabled}")
        log_json(f"Trading with: {len(config.scheduler.symbols)} coins")

        # ✅ REAL BROKER — connects to your actual Coinbase account
        broker = CoinbaseLiveBroker()
        usdt_balance = broker.get_usdt_balance()
        log_json(f"💰 Live Coinbase USDT balance: {usdt_balance}")

        starting_cash = usdt_balance if usdt_balance > 0 else config.scheduler.starting_cash
        portfolio = PaperPortfolio(starting_cash=starting_cash)

        strategies = [
            GridTradingStrategy(),
            ScalpingStrategy(),
            LiquidHeatmapStrategy(),
            MultiFrameStrategy(),
            SmaCrossoverStrategy(),
            MeanReversionStrategy(),
        ]

        log_json("=" * 80)
        log_json("🔥 ULTIMATE TRADING SYSTEM LOADED")
        log_json(f"✅ {len(strategies)} Strategies")
        log_json(f"Execution Mode: {execution_mode.upper()}")
        log_json(f"Live Trading: {live_enabled.upper()}")
        log_json("=" * 80)

        strategy = UltimateAggregator(strategies)

        scheduler = MultiSymbolScheduler(
            broker=broker,
            strategy=strategy,
            portfolio=portfolio,
            symbols=config.scheduler.symbols,
        )

        log_json("✅ ULTIMATE system running with REAL Coinbase broker...")

        cycle = 0
        while True:
            try:
                cycle += 1
                log_json(f"Starting cycle {cycle}...")
                scheduler.run_full_cycle()
                log_json(f"Cycle {cycle} completed")
                time.sleep(300)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log_json(f"Cycle error: {e}", "ERROR")
                time.sleep(300)

    except Exception as e:
        log_json(f"Fatal error: {e}", "ERROR")
        import traceback
        traceback.print_exc()


def run_dashboard():
    log_json("Starting dashboard...")
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("dashboard.app:app", host="0.0.0.0", port=port, log_level="info")


def main():
    log_json("🚀 ULTIMATE TRADING PLATFORM - LAUNCHING (LIVE BROKER)")
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    time.sleep(2)
    run_dashboard()


if __name__ == "__main__":
    main()
