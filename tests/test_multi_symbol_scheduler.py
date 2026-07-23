"""
Tests for MultiSymbolScheduler. Uses an injected candle_fetcher so no
real time or network is involved — run_full_cycle() is called directly,
the way the real BlockingScheduler would call it on each tick.
"""

from datetime import datetime, timedelta, timezone

import pytest

from broker.mock_broker import MockBroker
from paper_trading.engine import PositionSizeConfig
from scheduler.multi_symbol_scheduler import MultiSymbolScheduler
from strategy.base import PriceBar
from strategy.sma_crossover import SmaCrossoverStrategy


def make_bars(closes):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        PriceBar(
            timestamp=start + timedelta(hours=i),
            open=c, high=c * 1.001, low=c * 0.999, close=c, volume=100,
        )
        for i, c in enumerate(closes)
    ]


FLAT = [100.0] * 40
CROSSOVER = [100.0] * 39 + [130.0]


def fetcher_factory(bars_by_symbol, fail_symbols=None):
    fail_symbols = fail_symbols or set()

    def fetch(symbol, granularity, limit):
        if symbol in fail_symbols:
            raise ConnectionError(f"simulated network failure for {symbol}")
        return bars_by_symbol[symbol]

    return fetch


class TestMultiSymbolScheduler:
    def test_requires_at_least_one_symbol(self):
        broker = MockBroker(paper_mode=True)
        strat = SmaCrossoverStrategy()
        with pytest.raises(ValueError):
            MultiSymbolScheduler(broker=broker, strategy=strat, symbols=[])

    def test_runs_across_multiple_symbols(self):
        broker = MockBroker(
            paper_mode=True,
            starting_prices={"BTC-USD": 130.0, "ETH-USD": 130.0, "SOL-USD": 100.0},
        )
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        fetch = fetcher_factory({
            "BTC-USD": make_bars(CROSSOVER),
            "ETH-USD": make_bars(CROSSOVER),
            "SOL-USD": make_bars(FLAT),
        })
        runner = MultiSymbolScheduler(
            broker=broker, strategy=strat,
            symbols=["BTC-USD", "ETH-USD", "SOL-USD"],
            starting_cash=10_000.0,
            sizing=PositionSizeConfig(risk_per_trade_pct=1.0, max_position_pct=20.0),
            candle_fetcher=fetch,
        )
        results = runner.run_full_cycle()

        assert len(results) == 3
        assert all(r.ok for r in results)
        by_symbol = {r.symbol: r for r in results}
        assert by_symbol["BTC-USD"].candidate_found is True
        assert by_symbol["ETH-USD"].candidate_found is True
        assert by_symbol["SOL-USD"].candidate_found is False

        # Both crossover symbols should have opened paper positions, sharing
        # the same portfolio/cash pool.
        assert "BTC-USD" in runner.portfolio.positions
        assert "ETH-USD" in runner.portfolio.positions
        assert "SOL-USD" not in runner.portfolio.positions

    def test_symbol_positions_compete_for_shared_cash(self):
        """Risking 1% per trade across many symbols should never blow the
        shared paper account, even if every symbol signals at once."""
        symbols = [f"COIN{i}-USD" for i in range(10)]
        prices = {s: 130.0 for s in symbols}
        broker = MockBroker(paper_mode=True, starting_prices=prices)
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        fetch = fetcher_factory({s: make_bars(CROSSOVER) for s in symbols})
        runner = MultiSymbolScheduler(
            broker=broker, strategy=strat, symbols=symbols,
            starting_cash=10_000.0,
            sizing=PositionSizeConfig(risk_per_trade_pct=1.0, max_position_pct=20.0),
            candle_fetcher=fetch,
        )
        runner.run_full_cycle()
        assert runner.portfolio.cash >= 0
        assert len(runner.portfolio.positions) == 10

    def test_one_failing_symbol_does_not_break_the_cycle(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0, "ETH-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        fetch = fetcher_factory(
            {"BTC-USD": make_bars(CROSSOVER), "ETH-USD": make_bars(CROSSOVER)},
            fail_symbols={"ETH-USD"},
        )
        runner = MultiSymbolScheduler(
            broker=broker, strategy=strat, symbols=["BTC-USD", "ETH-USD"],
            candle_fetcher=fetch,
        )
        results = runner.run_full_cycle()

        by_symbol = {r.symbol: r for r in results}
        assert by_symbol["BTC-USD"].ok is True
        assert by_symbol["ETH-USD"].ok is False
        assert "simulated network failure" in by_symbol["ETH-USD"].error
        # the healthy symbol still traded despite the other symbol's failure
        assert "BTC-USD" in runner.portfolio.positions

    def test_repeated_cycles_do_not_stack_positions(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        fetch = fetcher_factory({"BTC-USD": make_bars(CROSSOVER)})
        runner = MultiSymbolScheduler(
            broker=broker, strategy=strat, symbols=["BTC-USD"], candle_fetcher=fetch,
        )
        runner.run_full_cycle()
        runner.run_full_cycle()
        runner.run_full_cycle()

        assert runner.tick_count == 3
        assert len(runner.portfolio.positions) == 1  # not stacked across cycles

    def test_consecutive_failures_are_tracked_per_symbol(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        fetch = fetcher_factory({"BTC-USD": make_bars(CROSSOVER)}, fail_symbols={"BTC-USD"})
        runner = MultiSymbolScheduler(
            broker=broker, strategy=strat, symbols=["BTC-USD"], candle_fetcher=fetch,
        )
        for _ in range(3):
            runner.run_full_cycle()
        assert runner._consecutive_symbol_failures["BTC-USD"] == 3

    def test_final_report_reflects_shared_portfolio(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        fetch = fetcher_factory({"BTC-USD": make_bars(FLAT)})
        runner = MultiSymbolScheduler(
            broker=broker, strategy=strat, symbols=["BTC-USD"], starting_cash=5_000.0,
            candle_fetcher=fetch,
        )
        runner.run_full_cycle()
        report = runner.final_report()
        assert report["starting_cash"] == 5_000.0
        assert report["equity"] == pytest.approx(5_000.0)  # no signal fired, nothing traded
