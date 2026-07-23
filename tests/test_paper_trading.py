"""
Unit tests for the paper trading vertical slice.

Run with: pytest tests/ -v
"""

from datetime import datetime, timedelta

import pytest

from broker.mock_broker import MockBroker
from paper_trading.engine import PaperTradingEngine, PositionSizeConfig
from paper_trading.portfolio import PaperPortfolio
from strategy.base import PriceBar
from strategy.sma_crossover import SmaCrossoverStrategy


def make_bars(closes, start=None):
    start = start or datetime(2026, 1, 1)
    bars = []
    for i, c in enumerate(closes):
        bars.append(
            PriceBar(
                timestamp=start + timedelta(hours=i),
                open=c, high=c * 1.001, low=c * 0.999, close=c, volume=100,
            )
        )
    return bars


def uptrend_crossover_series():
    """Flat series (fast == slow == 100) followed by a single sharp jump on
    the final bar, engineered so the 10/30 SMA crossover fires exactly on
    the last bar: fast[-2]=100<=slow[-2]=100 and fast[-1]=103>slow[-1]=101."""
    return [100.0] * 39 + [130.0]


class TestSmaCrossoverStrategy:
    def test_no_signal_on_flat_series(self):
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        bars = make_bars([100.0] * 40)
        assert strat.evaluate("BTC-USD", bars) is None

    def test_signal_on_crossover(self):
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        bars = make_bars(uptrend_crossover_series())
        candidate = strat.evaluate("BTC-USD", bars)
        assert candidate is not None
        assert candidate.direction.value == "long"
        assert candidate.stop_loss < bars[-1].close
        assert candidate.profit_target > bars[-1].close
        assert 0 <= candidate.confidence <= 1

    def test_not_enough_bars_returns_none(self):
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        bars = make_bars([100.0] * 5)
        assert strat.evaluate("BTC-USD", bars) is None


class TestPaperPortfolio:
    def test_open_and_close_position_pnl(self):
        pf = PaperPortfolio(starting_cash=10_000.0, fee_rate=0.0)
        pf.open_position("BTC-USD", quantity=1.0, fill_price=100.0, strategy_name="test")
        assert pf.cash == pytest.approx(9_900.0)

        trade = pf.close_position("BTC-USD", fill_price=110.0, exit_reason="manual")
        assert trade.pnl == pytest.approx(10.0)
        assert pf.cash == pytest.approx(10_010.0)
        assert len(pf.closed_trades) == 1

    def test_insufficient_cash_raises(self):
        pf = PaperPortfolio(starting_cash=100.0, fee_rate=0.0)
        with pytest.raises(ValueError):
            pf.open_position("BTC-USD", quantity=10.0, fill_price=100.0, strategy_name="test")

    def test_stop_loss_trigger(self):
        pf = PaperPortfolio(starting_cash=10_000.0, fee_rate=0.0)
        pf.open_position(
            "BTC-USD", quantity=1.0, fill_price=100.0, strategy_name="test", stop_loss=95.0
        )
        assert pf.check_stop_and_target("BTC-USD", 96.0) is None
        assert pf.check_stop_and_target("BTC-USD", 94.0) == "stop_loss"

    def test_profit_target_trigger(self):
        pf = PaperPortfolio(starting_cash=10_000.0, fee_rate=0.0)
        pf.open_position(
            "BTC-USD", quantity=1.0, fill_price=100.0, strategy_name="test", profit_target=120.0
        )
        assert pf.check_stop_and_target("BTC-USD", 119.0) is None
        assert pf.check_stop_and_target("BTC-USD", 121.0) == "profit_target"


class TestPaperTradingEngine:
    def test_rejects_live_mode_broker(self):
        broker = MockBroker(paper_mode=False)
        strat = SmaCrossoverStrategy()
        with pytest.raises(ValueError):
            PaperTradingEngine(broker=broker, strategy=strat)

    def test_opens_position_on_signal(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        engine = PaperTradingEngine(
            broker=broker, strategy=strat,
            sizing=PositionSizeConfig(risk_per_trade_pct=1.0, max_position_pct=50.0),
        )
        bars = make_bars(uptrend_crossover_series())
        candidate = engine.on_bars("BTC-USD", bars)

        assert candidate is not None
        assert "BTC-USD" in engine.portfolio.positions
        position = engine.portfolio.positions["BTC-USD"]
        assert position.quantity > 0
        # risking 1% of 10,000 equity should never eat the whole account
        assert position.quantity * 118.5 < 10_000.0

    def test_does_not_stack_positions(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        engine = PaperTradingEngine(broker=broker, strategy=strat)
        bars = make_bars(uptrend_crossover_series())

        engine.on_bars("BTC-USD", bars)
        assert "BTC-USD" in engine.portfolio.positions
        # second call with a position already open should not open another
        result = engine.on_bars("BTC-USD", bars)
        assert result is None
        assert len(engine.portfolio.positions) == 1

    def test_closes_on_stop_loss(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        engine = PaperTradingEngine(broker=broker, strategy=strat)
        bars = make_bars(uptrend_crossover_series())

        engine.on_bars("BTC-USD", bars)
        stop = engine.portfolio.positions["BTC-USD"].stop_loss

        broker.set_price("BTC-USD", stop - 1)
        engine.on_bars("BTC-USD", bars)  # triggers management check at top of on_bars

        assert "BTC-USD" not in engine.portfolio.positions
        assert len(engine.portfolio.closed_trades) == 1
        assert engine.portfolio.closed_trades[0].exit_reason == "stop_loss"

    def test_never_calls_place_order(self):
        """The paper engine must never touch broker.place_order — MockBroker
        raises if it's called, so this test fails loudly if that contract breaks."""
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        engine = PaperTradingEngine(broker=broker, strategy=strat)
        bars = make_bars(uptrend_crossover_series())
        # Should not raise — if it did, place_order was called somewhere.
        engine.on_bars("BTC-USD", bars)
