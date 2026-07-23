#!/usr/bin/env python3
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from scheduler.multi_symbol_scheduler import MultiSymbolScheduler
from strategy.sma_crossover import SmaCrossoverStrategy
from paper_trading.portfolio import PaperPortfolio
from broker.mock_broker import MockBroker
from config import load_config

def log_json(message, level="INFO"):
    timestamp = datetime.utcnow().isoformat() + "+00:00"
    log_entry = {
        "timestamp": timestamp,
        "level": level,
        "message": message
    }
    print(json.dumps(log_entry))

def main():
    log_json("=" * 80)
    log_json("TRADING PLATFORM STARTING UP")
    log_json("=" * 80)
    
    config = load_config()
    
    log_json(f"Execution mode: {config.execution.mode}")
    log_json(f"Symbols: {config.scheduler.symbols}")
    log_json(f"Starting cash: ${config.scheduler.starting_cash}")
    
    broker = MockBroker(paper_mode=True)
    strategy = SmaCrossoverStrategy()
    portfolio = PaperPortfolio(starting_cash=config.scheduler.starting_cash)
    
    scheduler = MultiSymbolScheduler(
        broker=broker,
        strategy=strategy,
        
        symbols=config.scheduler.symbols,
        granularity=config.scheduler.granularity,
        candle_limit=config.scheduler.candle_limit,
    )
    
    log_json("Scheduler starting. Press Ctrl+C to stop.")
    log_json("Dashboard: http://127.0.0.1:8000")
    
    try:
        import time
        while True:
            try:
                scheduler.run_full_cycle()
                time.sleep(300)  # Wait 5 minutes
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log_json(f"Cycle error: {e}", "ERROR")
                time.sleep(300)
    except KeyboardInterrupt:
        log_json("Scheduler stopped.")

if __name__ == "__main__":
    main()
