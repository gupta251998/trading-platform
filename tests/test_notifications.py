"""
Tests for the notifier interface, the Telegram implementation (with
requests.post mocked — no real network calls), and the engine's wiring
that fires notifications on open/close events without ever letting a
broken notifier break the trading loop.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from broker.mock_broker import MockBroker
from notifications.base import Notifier
from notifications.telegram_notifier import TelegramNotifier
from paper_trading.engine import PaperTradingEngine
from strategy.base import PriceBar
from strategy.sma_crossover import SmaCrossoverStrategy


def make_bars(closes):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        PriceBar(timestamp=start + timedelta(hours=i), open=c, high=c * 1.001,
                  low=c * 0.999, close=c, volume=100)
        for i, c in enumerate(closes)
    ]


CROSSOVER = [100.0] * 39 + [130.0]


class RecordingNotifier(Notifier):
    name = "recording"

    def __init__(self):
        self.opened = []
        self.closed = []
        self.failures = []

    def notify_candidate_opened(self, candidate, quantity, fill_price):
        self.opened.append((candidate.symbol, quantity, fill_price))

    def notify_position_closed(self, trade):
        self.closed.append((trade.symbol, trade.pnl))

    def notify_symbol_failing(self, symbol, consecutive_failures, error):
        self.failures.append((symbol, consecutive_failures, error))


class BrokenNotifier(Notifier):
    """A notifier that always raises — the engine must survive this."""
    name = "broken"

    def notify_candidate_opened(self, *a, **k):
        raise RuntimeError("boom")

    def notify_position_closed(self, *a, **k):
        raise RuntimeError("boom")

    def notify_symbol_failing(self, *a, **k):
        raise RuntimeError("boom")


class TestEngineNotifierWiring:
    def test_fires_on_open(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        recorder = RecordingNotifier()
        engine = PaperTradingEngine(broker=broker, strategy=strat, notifiers=[recorder])

        engine.on_bars("BTC-USD", make_bars(CROSSOVER))

        assert len(recorder.opened) == 1
        assert recorder.opened[0][0] == "BTC-USD"

    def test_fires_on_close(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        recorder = RecordingNotifier()
        engine = PaperTradingEngine(broker=broker, strategy=strat, notifiers=[recorder])

        engine.on_bars("BTC-USD", make_bars(CROSSOVER))
        stop = engine.portfolio.positions["BTC-USD"].stop_loss
        broker.set_price("BTC-USD", stop - 1)
        engine.on_bars("BTC-USD", make_bars(CROSSOVER))

        assert len(recorder.closed) == 1
        assert recorder.closed[0][0] == "BTC-USD"

    def test_broken_notifier_does_not_break_engine(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        engine = PaperTradingEngine(broker=broker, strategy=strat, notifiers=[BrokenNotifier()])

        # Should not raise, even though the notifier always does.
        candidate = engine.on_bars("BTC-USD", make_bars(CROSSOVER))
        assert candidate is not None
        assert "BTC-USD" in engine.portfolio.positions

    def test_multiple_notifiers_all_fire(self):
        broker = MockBroker(paper_mode=True, starting_prices={"BTC-USD": 130.0})
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        rec1, rec2 = RecordingNotifier(), RecordingNotifier()
        engine = PaperTradingEngine(broker=broker, strategy=strat, notifiers=[rec1, rec2])

        engine.on_bars("BTC-USD", make_bars(CROSSOVER))
        assert len(rec1.opened) == 1
        assert len(rec2.opened) == 1


class TestTelegramNotifier:
    def test_sends_expected_payload_on_open(self):
        notifier = TelegramNotifier(bot_token="TESTTOKEN", chat_id="12345")
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        candidate = strat.evaluate("BTC-USD", make_bars(CROSSOVER))
        assert candidate is not None

        with patch("notifications.telegram_notifier.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            notifier._send_sync("test message")  # bypass the background thread for determinism

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.telegram.org/botTESTTOKEN/sendMessage"
        assert kwargs["json"]["chat_id"] == "12345"
        assert kwargs["json"]["text"] == "test message"

    def test_send_failure_is_swallowed(self):
        notifier = TelegramNotifier(bot_token="TESTTOKEN", chat_id="12345")
        with patch("notifications.telegram_notifier.requests.post", side_effect=ConnectionError("down")):
            # Must not raise even though the HTTP call fails.
            notifier._send_sync("test message")

    def test_non_200_response_is_handled(self):
        notifier = TelegramNotifier(bot_token="TESTTOKEN", chat_id="12345")
        with patch("notifications.telegram_notifier.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=403, text="Forbidden")
            notifier._send_sync("test message")  # should not raise

    def test_notify_candidate_opened_builds_message_and_sends(self):
        notifier = TelegramNotifier(bot_token="T", chat_id="C")
        strat = SmaCrossoverStrategy(fast_period=10, slow_period=30)
        candidate = strat.evaluate("BTC-USD", make_bars(CROSSOVER))

        with patch.object(notifier, "_send") as mock_send:
            notifier.notify_candidate_opened(candidate, quantity=0.5, fill_price=130.0)

        mock_send.assert_called_once()
        text = mock_send.call_args[0][0]
        assert "BTC-USD" in text
        assert "0.500000" in text
