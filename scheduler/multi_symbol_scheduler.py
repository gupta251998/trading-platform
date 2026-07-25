"""Multi-Symbol Trading Scheduler"""
import logging
from typing import List, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class MultiSymbolScheduler:
    """Schedules trading across multiple symbols"""
    
    def __init__(self, broker, strategy, portfolio, symbols, granularity="ONE_HOUR", candle_limit=100):
        self.broker = broker
        self.strategy = strategy
        self.portfolio = portfolio
        self.symbols = symbols
        self.granularity = granularity
        self.candle_limit = candle_limit
        self.cycle_count = 0
    
    def run_full_cycle(self):
        """Run one complete trading cycle across all symbols"""
        self.cycle_count += 1
        
        print(json.dumps({
            "timestamp": datetime.utcnow().isoformat() + "+00:00",
            "level": "INFO",
            "message": f"=== Cycle {self.cycle_count} starting ({len(self.symbols)} symbols) ==="
        }))
        
        for symbol in self.symbols:
            try:
                self.process_symbol(symbol)
            except Exception as e:
                print(json.dumps({
                    "timestamp": datetime.utcnow().isoformat() + "+00:00",
                    "level": "ERROR",
                    "message": f"Error processing {symbol}: {e}"
                }))
    
    def process_symbol(self, symbol):
        """Process a single symbol"""
        try:
            # Get candles from broker
            candles = self.broker.get_candles(
                symbol=symbol,
                granularity=self.granularity,
                limit=self.candle_limit
            )
            
            if not candles or len(candles) < 5:
                return
            
            # Generate signal from strategy
            signal = self.strategy.generate_signal(symbol, candles)
            
            if signal:
                print(json.dumps({
                    "timestamp": datetime.utcnow().isoformat() + "+00:00",
                    "level": "INFO",
                    "message": f"🎯 SIGNAL: {symbol} {signal.direction.value.upper()} @ ${signal.entry_price:.6f} (Confidence: {signal.confidence:.0%})"
                }))
                
                # Execute trade
                self.execute_trade(signal)
        
        except Exception as e:
            print(json.dumps({
                "timestamp": datetime.utcnow().isoformat() + "+00:00",
                "level": "ERROR",
                "message": f"Error in process_symbol({symbol}): {str(e)}"
            }))
    
    def execute_trade(self, signal):
        """Execute a trade based on signal"""
        try:
            if signal.direction.value == "long":
                position_size = self.portfolio.calculate_position_size(signal.entry_price)
                self.portfolio.add_position(
                    symbol=signal.symbol,
                    direction="long",
                    quantity=position_size,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    profit_target=signal.profit_target,
                    strategy=signal.strategy_name
                )
            else:
                position_size = self.portfolio.calculate_position_size(signal.entry_price)
                self.portfolio.add_position(
                    symbol=signal.symbol,
                    direction="short",
                    quantity=position_size,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    profit_target=signal.profit_target,
                    strategy=signal.strategy_name
                )
            
            print(json.dumps({
                "timestamp": datetime.utcnow().isoformat() + "+00:00",
                "level": "INFO",
                "message": f"✅ TRADE EXECUTED: {signal.symbol} {signal.direction.value.upper()}"
            }))
        
        except Exception as e:
            print(json.dumps({
                "timestamp": datetime.utcnow().isoformat() + "+00:00",
                "level": "ERROR",
                "message": f"Error executing trade: {str(e)}"
            }))
