"""Multi-Symbol Trading Scheduler — real broker, verified order success, risk guards, full open+close automation"""
import os
from datetime import datetime, timezone
import json

from notifications.telegram_notify import send_telegram


class MultiSymbolScheduler:
    def __init__(self, broker, strategy, portfolio, symbols, granularity="ONE_HOUR", candle_limit=100):
        self.broker = broker
        self.strategy = strategy
        self.portfolio = portfolio
        self.symbols = symbols
        self.granularity = granularity
        self.candle_limit = candle_limit
        self.cycle_count = 0

        self.fixed_trade_size_usd = float(os.getenv("FIXED_TRADE_SIZE_USD", "2.00"))
        self.max_concurrent_positions = int(os.getenv("MAX_CONCURRENT_POSITIONS", "3"))
        self.daily_loss_limit = float(os.getenv("DAILY_LOSS_LIMIT", "2.00"))
        self.trading_halted_today = False

    def _log(self, message, level="INFO"):
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message
        }), flush=True)

    def run_full_cycle(self):
        self.cycle_count += 1
        self._log(f"=== Cycle {self.cycle_count} starting ({len(self.symbols)} symbols) ===")

        self.check_exits()

        daily_pnl = self.portfolio.daily_pnl() if hasattr(self.portfolio, "daily_pnl") else 0
        if daily_pnl <= -abs(self.daily_loss_limit):
            if not self.trading_halted_today:
                self._log(f"DAILY LOSS LIMIT HIT: realized P&L today is ${daily_pnl:.4f}, limit is -${self.daily_loss_limit:.2f}. Halting new trades until UTC midnight.", "ERROR")
                send_telegram(f"DAILY LOSS LIMIT HIT\nRealized P&L today: ${daily_pnl:.4f}\nLimit: -${self.daily_loss_limit:.2f}\nNew trades paused. Existing positions still monitored for exits.")
                self.trading_halted_today = True
        else:
            self.trading_halted_today = False

        for symbol in self.symbols:
            try:
                self.process_symbol(symbol)
            except Exception as e:
                self._log(f"Error processing {symbol}: {e}", "ERROR")

    def check_exits(self):
        """Check stop-loss and profit-target for every open position, sell if triggered."""
        open_symbols = list(self.portfolio.positions.keys())
        for symbol in open_symbols:
            try:
                candles = self.broker.get_candles(symbol, granularity=self.granularity, limit=30)
                if not candles:
                    continue
                current_price = candles[-1]["close"]

                exit_reason = self.portfolio.check_stop_and_target(symbol, current_price)
                if exit_reason:
                    self._log(f"EXIT TRIGGERED: {symbol} - {exit_reason} at ${current_price:.6f}")
                    self.close_real_position(symbol, current_price, exit_reason)
            except Exception as e:
                self._log(f"Error checking exit for {symbol}: {e}", "ERROR")

    def close_real_position(self, symbol, current_price, exit_reason):
        try:
            position = self.portfolio.positions.get(symbol)
            if not position:
                return

            is_live = hasattr(self.broker, "place_market_order") and not getattr(self.broker, "paper_mode", True)

            if is_live:
                result = self.broker.place_market_order(
                    symbol=symbol,
                    side="SELL",
                    base_size=str(position.quantity)
                )
                if not result:
                    self._log(f"SELL order REJECTED for {symbol} - position remains open", "ERROR")
                    return
                self._log(f"SELL EXECUTED (LIVE, CONFIRMED): {symbol} qty={position.quantity:.6f} @ ${current_price:.6f} ({exit_reason})")
                send_telegram(
                    f"POSITION CLOSED\nSymbol: {symbol}\nReason: {exit_reason}\nExit price: ${current_price:.6f}"
                )
            else:
                self._log(f"SELL EXECUTED (PAPER): {symbol} qty={position.quantity:.6f} @ ${current_price:.6f} ({exit_reason})")

            closed_trade = self.portfolio.close_position(symbol, current_price, exit_reason)
            pnl = closed_trade.pnl if closed_trade else 0
            self._log(f"Position closed: {symbol} PnL=${pnl:.4f}")

        except Exception as e:
            self._log(f"Error closing position {symbol}: {e}", "ERROR")

    def process_symbol(self, symbol):
        try:
            if self.trading_halted_today:
                return

            if symbol in self.portfolio.positions:
                return

            if len(self.portfolio.positions) >= self.max_concurrent_positions:
                return

            base_currency = symbol.split("-")[0]
            if hasattr(self.broker, "get_holding_value_usd"):
                real_holding = self.broker.get_holding_value_usd(base_currency)
                if real_holding and real_holding > 0.10:
                    self._log(f"{symbol}: already hold {real_holding:.4f} USD worth on real Coinbase account, skipping", "DEBUG")
                    return

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
            position_size_usd = min(self.fixed_trade_size_usd, available_cash)

            if position_size_usd < 1.0:
                self._log(f"Insufficient cash for {signal.symbol}: only ${available_cash:.2f} left", "INFO")
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
                    self._log(f"Trade NOT executed for {signal.symbol} - Coinbase rejected the order", "ERROR")
                    return
                self._log(f"TRADE EXECUTED (LIVE, CONFIRMED): {signal.symbol} BUY ${position_size_usd:.2f}")
                send_telegram(
                    f"TRADE EXECUTED\nSymbol: {signal.symbol}\nSide: BUY\nAmount: ${position_size_usd:.2f}\n"
                    f"Entry: ${signal.entry_price:.6f}\nStop: ${signal.stop_loss:.6f}\nTarget: ${signal.profit_target:.6f}\n"
                    f"Strategy: {signal.strategy_name}\nConfidence: {signal.confidence:.0%}"
                )
            else:
                self._log(f"TRADE EXECUTED (PAPER): {signal.symbol} BUY ${position_size_usd:.2f}")

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
