"""Multi-Symbol Trading Scheduler — works with real or mock brokers"""
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

    def _log(self, message, level="INFO"):
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message
        }))

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
                self._log(f"🎯 SIGNAL: {symbol} {signal.direction.value.upper()} @ ${signal.entry_price:.6f} (Confidence: {signal.confidence:.0%})")
                self.execute_trade(signal)

        except Exception as e:
            self._log(f"Error in process_symbol({symbol}): {e}", "ERROR")

    def execute_trade(self, signal):
        try:
            # Only support LONG entries for spot (no shorting on Coinbase spot)
            if signal.direction.value != "long":
                self._log(f"Skipping SHORT signal on {signal.symbol} — spot account can't short", "INFO")
                return

            position_size_usd = self.portfolio.calculate_position_size(signal.entry_price)

            if hasattr(self.broker, "place_market_order") and not getattr(self.broker, "paper_mode", True):
                result = self.broker.place_market_order(
                    symbol=signal.symbol,
                    side="BUY",
                    quote_size=round(position_size_usd, 2)
                )
                if result:
                    self._log(f"✅ TRADE EXECUTED (LIVE): {signal.symbol} BUY ${position_size_usd:.2f}")
                else:
                    self._log(f"❌ Trade failed for {signal.symbol}", "ERROR")
                    return
            else:
                self._log(f"✅ TRADE EXECUTED (PAPER): {signal.symbol} BUY ${position_size_usd:.2f}")

            self.portfolio.add_position(
                symbol=signal.symbol,
                direction="long",
                quantity=position_size_usd / signal.entry_price,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                profit_target=signal.profit_target,
                strategy=signal.strategy_name
            )

        except Exception as e:
            self._log(f"Error executing trade: {e}", "ERROR")
