#!/usr/bin/env python3
import os
import sys
import threading
import time
from datetime import datetime
import json

sys.path.insert(0, os.path.dirname(__file__))

def log_json(message, level="INFO"):
    timestamp = datetime.utcnow().isoformat() + "+00:00"
    log_entry = {"timestamp": timestamp, "level": level, "message": message}
    print(json.dumps(log_entry))

def run_scheduler():
    """Run the trading scheduler in background"""
    log_json("Starting scheduler thread...")
    try:
        from scheduler.multi_symbol_scheduler import MultiSymbolScheduler
        from strategy.sma_crossover import SmaCrossoverStrategy
        from paper_trading.portfolio import PaperPortfolio
        from broker.mock_broker import MockBroker
        from config import load_config
        
        config = load_config()
        log_json(f"Execution mode: {config.execution.mode}")
        log_json(f"Symbols: {config.scheduler.symbols}")
        
        broker = MockBroker(paper_mode=True)
        strategy = SmaCrossoverStrategy()
        portfolio = PaperPortfolio(starting_cash=config.scheduler.starting_cash)
        
        scheduler = MultiSymbolScheduler(
            broker=broker,
            strategy=strategy,
            portfolio=portfolio,
            symbols=config.scheduler.symbols,
        )
        
        log_json("Scheduler running in background...")
        
        import time
        while True:
            try:
                scheduler.run_full_cycle()
                time.sleep(300)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log_json(f"Cycle error: {e}", "ERROR")
                time.sleep(300)
                
    except Exception as e:
        log_json(f"Scheduler fatal error: {e}", "ERROR")
        import traceback
        traceback.print_exc()

def run_dashboard():
    """Run the Uvicorn web server"""
    log_json("Starting dashboard server...")
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"
    
    uvicorn.run(
        "dashboard.app:app",
        host=host,
        port=port,
        log_level="info"
    )

def main():
    log_json("=" * 80)
    log_json("TRADING PLATFORM STARTING (Web + Scheduler)")
    log_json("=" * 80)
    
    # Start scheduler in background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Sleep a bit to let scheduler initialize
    time.sleep(2)
    
    # Run dashboard in main thread (blocks)
    run_dashboard()

if __name__ == "__main__":
    main()
