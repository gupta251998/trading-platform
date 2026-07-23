"""
Multi-symbol scheduler — runs the paper trading engine across a list of
symbols on a repeating interval, indefinitely.

Design choice: a SINGLE PaperTradingEngine (and therefore a single shared
PaperPortfolio) handles all symbols. This is deliberate, not an oversight —
symbols compete for the same paper cash, which is how a real account
behaves. `PaperPortfolio.positions` is already keyed by symbol, so nothing
about the engine needed to change to support this.

This module only contains the *logic* (what happens each tick, per
symbol, and across a full cycle). The actual "run forever on a timer"
wiring lives in `run_scheduler.py` so this class can be unit tested by
calling `run_full_cycle()` directly, without waiting on real time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from broker.interface import BrokerInterface
from notifications.base import Notifier
from paper_trading.engine import PaperTradingEngine, PositionSizeConfig
from paper_trading.portfolio import PaperPortfolio
from strategy.base import PriceBar, Strategy

logger = logging.getLogger("scheduler.multi_symbol")


@dataclass
class SymbolTickResult:
    symbol: str
    ok: bool
    candidate_found: bool = False
    error: Optional[str] = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MultiSymbolScheduler:
    def __init__(
        self,
        broker: BrokerInterface,
        strategy: Strategy,
        symbols: List[str],
        granularity: str = "ONE_HOUR",
        candle_limit: int = 200,
        starting_cash: float = 10_000.0,
        sizing: Optional[PositionSizeConfig] = None,
        candle_fetcher: Optional[Callable[[str, str, int], List[PriceBar]]] = None,
        notifiers: Optional[List[Notifier]] = None,
        failure_escalation_threshold: int = 5,
    ):
        if not symbols:
            raise ValueError("symbols list must not be empty")

        self.symbols = symbols
        self.granularity = granularity
        self.candle_limit = candle_limit
        self.failure_escalation_threshold = failure_escalation_threshold
        self.notifiers = notifiers or []
        self.portfolio = PaperPortfolio(starting_cash=starting_cash)
        self.engine = PaperTradingEngine(
            broker=broker,
            strategy=strategy,
            portfolio=self.portfolio,
            sizing=sizing or PositionSizeConfig(),
            notifiers=self.notifiers,
        )
        # Injectable so tests can supply canned bars instead of hitting the
        # network. Defaults to pulling real candles from the broker.
        self._fetch_bars = candle_fetcher or self._default_candle_fetcher(broker)

        self.tick_count = 0
        self.last_cycle_results: List[SymbolTickResult] = []
        self._consecutive_symbol_failures: Dict[str, int] = {s: 0 for s in symbols}
        self._escalation_sent: Dict[str, bool] = {s: False for s in symbols}

    @staticmethod
    def _default_candle_fetcher(broker: BrokerInterface):
        def fetch(symbol: str, granularity: str, limit: int) -> List[PriceBar]:
            raw = broker.get_candles(symbol, granularity=granularity, limit=limit)
            return [
                PriceBar(
                    timestamp=datetime.fromtimestamp(c["start"], tz=timezone.utc),
                    open=c["open"], high=c["high"], low=c["low"],
                    close=c["close"], volume=c["volume"],
                )
                for c in raw
            ]
        return fetch

    def run_symbol_tick(self, symbol: str) -> SymbolTickResult:
        """
        Process one symbol: fetch bars, run the engine. Any exception is
        caught and returned as a failed result — one bad symbol (rate
        limit, bad data, network blip) must never take down the whole
        scheduler loop or the other symbols in the cycle.
        """
        try:
            bars = self._fetch_bars(symbol, self.granularity, self.candle_limit)
            if not bars:
                return SymbolTickResult(symbol=symbol, ok=False, error="no bars returned")

            candidate = self.engine.on_bars(symbol, bars)
            self._consecutive_symbol_failures[symbol] = 0
            self._escalation_sent[symbol] = False
            return SymbolTickResult(symbol=symbol, ok=True, candidate_found=candidate is not None)

        except Exception as exc:
            self._consecutive_symbol_failures[symbol] = self._consecutive_symbol_failures.get(symbol, 0) + 1
            failures = self._consecutive_symbol_failures[symbol]
            logger.error("Tick failed for %s (consecutive failures: %d): %s",
                         symbol, failures, exc, exc_info=True)
            if failures >= self.failure_escalation_threshold and not self._escalation_sent[symbol]:
                self._escalation_sent[symbol] = True
                for notifier in self.notifiers:
                    try:
                        notifier.notify_symbol_failing(symbol, failures, str(exc))
                    except Exception as notify_exc:
                        logger.warning("Notifier %s failed on notify_symbol_failing: %s",
                                       notifier.name, notify_exc)
            return SymbolTickResult(symbol=symbol, ok=False, error=str(exc))

    def run_full_cycle(self) -> List[SymbolTickResult]:
        """Run one tick across every configured symbol, then log a portfolio summary."""
        self.tick_count += 1
        logger.info("=== Cycle %d starting (%d symbols) ===", self.tick_count, len(self.symbols))

        results = [self.run_symbol_tick(symbol) for symbol in self.symbols]
        self.last_cycle_results = results

        failures = [r for r in results if not r.ok]
        signals = [r for r in results if r.candidate_found]
        if failures:
            logger.warning("Cycle %d: %d/%d symbols failed: %s",
                           self.tick_count, len(failures), len(results),
                           ", ".join(f"{r.symbol}({r.error})" for r in failures))
        if signals:
            logger.info("Cycle %d: new candidates on %s",
                        self.tick_count, ", ".join(r.symbol for r in signals))

        report = self.engine.performance_report(self.symbols)
        logger.info("Cycle %d portfolio: %s", self.tick_count, report)

        for symbol, failure_count in self._consecutive_symbol_failures.items():
            if failure_count >= self.failure_escalation_threshold:
                logger.error(
                    "%s has failed %d consecutive cycles — check credentials/connectivity/symbol validity",
                    symbol, failure_count,
                )

        return results

    def final_report(self) -> dict:
        return self.engine.performance_report(self.symbols)
