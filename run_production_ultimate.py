#!/usr/bin/env python3
import os
import sys
import threading
import time
from datetime import datetime, timezone
import json

sys.path.insert(0, os.path.dirname(__file__))


def load_env_file():
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
    print(json.dumps({"timestamp": timestamp, "level": level, "message": message}), flush=True)


def reconcile_existing_holdings(broker, portfolio, symbols, log_json):
    """On startup, check real Coinbase balances and register any holdings
    not already tracked in the in-memory portfolio, so check_exits() can manage them."""
    try:
        for symbol in symbols:
            base_currency = symbol.split("-")[0]
            if symbol in portfolio.positions:
                continue
            if not hasattr(broker, "get_holding_value_usd"):
                continue
            qty = broker.get_holding_value_usd(base_currency)
            if qty and qty > 0.0001:
                try:
                    candles = broker.get_candles(symbol, granularity="ONE_HOUR", limit=30)
                    if not candles:
                        log_json(f"Could not reconcile {symbol}: no recent candle data", "ERROR")
                        continue
                    current_price = candles[-1]["close"]
                    stop_loss = current_price * 0.98
                    profit_target = current_price * 1.02
                    portfolio.register_existing_holding(
                        symbol=symbol,
                        quantity=qty,
                        fill_price=current_price,
                        strategy_name="reconciled_existing",
                        stop_loss=stop_loss,
                        profit_target=profit_target,
                    )
                    log_json(f"RECONCILED existing holding: {symbol} qty={qty:.6f} @ approx ${current_price:.6f}, stop=${stop_loss:.6f}, target=${profit_target:.6f}")
                except Exception as e:
                    log_json(f"Failed to reconcile {symbol}: {e}", "ERROR")
    except Exception as e:
        log_json(f"Reconciliation error: {e}", "ERROR")


def run_scheduler():
    log_json("Starting trading system...")
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

        broker = CoinbaseLiveBroker()
        usdt_balance = broker.get_usdt_balance()
        log_json(f"Live Coinbase USDT balance: {usdt_balance}")

        starting_cash = usdt_balance if usdt_balance > 0 else config.scheduler.starting_cash
        portfolio = PaperPortfolio(starting_cash=starting_cash)

        import shared_state
        shared_state.set_portfolio(portfolio)
        shared_state.set_broker(broker)

        strategies = [
            GridTradingStrategy(),
            ScalpingStrategy(),
            LiquidHeatmapStrategy(),
            MultiFrameStrategy(),
            SmaCrossoverStrategy(),
            MeanReversionStrategy(),
        ]

        log_json("=" * 80)
        log_json(f"{len(strategies)} strategies loaded: Grid, Scalping, LiquidHeatmap, MultiFrame, SMA, MeanReversion")
        log_json(f"Aggregator threshold: 2/6 agreement, 65% confidence")
        log_json(f"Fixed trade size: ${os.getenv('FIXED_TRADE_SIZE_USD', '2.00')}")
        log_json(f"Max concurrent positions: {os.getenv('MAX_CONCURRENT_POSITIONS', '3')}")
        log_json("=" * 80)

        strategy = UltimateAggregator(strategies)

        reconcile_existing_holdings(broker, portfolio, config.scheduler.symbols, log_json)

        scheduler = MultiSymbolScheduler(
            broker=broker,
            strategy=strategy,
            portfolio=portfolio,
            symbols=config.scheduler.symbols,
        )

        log_json("System running with REAL Coinbase broker...")

        cycle = 0
        while True:
            try:
                cycle += 1
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
    log_json("TRADING PLATFORM - LAUNCHING (LIVE BROKER)")
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    time.sleep(2)
    run_dashboard()


if __name__ == "__main__":
    main()
