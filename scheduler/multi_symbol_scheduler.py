"""Multi-Symbol Trading Scheduler — works with real or mock brokers"""
import os
from datetime import datetime, timezone
import json


class MultiSymbolScheduler:
    def __init__(self, broker, strategy, portfolio, symbols, granularity="ONE_HOUR", candle_limit=100):
        self.broker = broker
        self.strategy = strategy
        self.portfolio = portfolio
        self.symbols = symbols
        self.granularity = granularity
        self.candle_limit = candle_limit
        self.cycle_count = 0
        self.max_position_pct = float(os.getenv("MAX_POSITION_SIZE_PCT", "0.5")) / 100

    def _log(self, message, level="INFO"):
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message
        }), flush=True)

    def run_full_cycle(self):
        self.cycle_count += 1
        self._log(f"=== Cycle {self.cycle_count} starting ({len(self.symbols)} symbols) ===")

        for symbol in self.symbols:
            try:
                self.process_symbol(symbol)
            except Exception as e:
                self._log(f"Error processing {symbol}: {e}", "ERROR")

    def process_symbol(self, symbol):
        try:
            candles = self.broker.get_candles(symbol, granularity=self.granularity, limit=self.candle_limit)

            if not candles or len(candles) < 5:
                self._log(f"{symbol}: not enough candle data ({len(candles) if candles else 0})", "DEBUG")
                return

            signal = self.strategy.generate_signal(symbol, candles)

            if signal:
                self._log(f"SIGNAL: {symbol} {signal.direction.value.upper()} @ ${signal.entry_price:.6f} (Confidence: {signal.confidence:.0%})")
                self.execute_trade(signal)

        except Exception as e:
            self._log(f"Error in process_symbol({symbol}): {e}", "ERROR")

    def execute_trade(self, signal):
        try:
            if signal.direction.value != "long":
                self._log(f"Skipping SHORT signal on {signal.symbol} - spot account cannot short", "INFO")
                return

            available_cash = self.portfolio.cash
            position_size_usd = available_cash * self.max_position_pct

            if position_size_usd < 1.0:
                self._log(f"Position size ${position_size_usd:.4f} too small to trade on {signal.symbol}", "INFO")
                return

            quantity = position_size_usd / signal.entry_price

            is_live = hasattr(self.broker, "place_market_order") and not getattr(self.broker, "paper_mode", True)

            if is_live:
                result = self.broker.place_market_order(
                    symbol=signal.symbol,
                    side="BUY",
                    quote_size=round(position_size_usd, 2)
                )
                if not result:
                    self._log(f"LIVE order failed for {signal.symbol}", "ERROR")
                    return
                self._log(f"TRADE EXECUTED (LIVE): {signal.symbol} BUY ${position_size_usd:.4f}")
            else:
                self._log(f"TRADE EXECUTED (PAPER): {signal.symbol} BUY ${position_size_usd:.4f}")

            self.portfolio.open_position(
                symbol=signal.symbol,
                quantity=quantity,
                fill_price=signal.entry_price,
                strategy_name=signal.strategy_name,
                stop_loss=signal.stop_loss,
                profit_target=signal.profit_target,
            )
            self._log(f"Portfolio position opened: {signal.symbol} qty={quantity:.6f} @ ${signal.entry_price:.6f}")

        except ValueError as e:
            self._log(f"Trade rejected (insufficient funds): {e}", "ERROR")
        except Exception as e:
            self._log(f"Error executing trade: {e}", "ERROR")
