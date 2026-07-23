"""
Paper Trading Engine — the loop that ties broker market data, a strategy,
and the paper portfolio together.

Critical safety property: this engine NEVER calls broker.place_order().
It reads real market data through the BrokerInterface (get_quote, and in
a fuller build, candles) and simulates fills against real prices inside
PaperPortfolio. A broker adapter's place_order() is only ever reachable
from a separate, explicit, human-approved live-execution path — which is
intentionally not built in this slice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from broker.interface import BrokerInterface
from notifications.base import Notifier
from paper_trading.portfolio import PaperPortfolio
from strategy.base import PriceBar, Strategy, TradeCandidate

logger = logging.getLogger("paper_trading.engine")


@dataclass
class PositionSizeConfig:
    risk_per_trade_pct: float = 1.0  # % of equity risked per trade
    max_position_pct: float = 20.0  # cap any single position at % of equity


class PaperTradingEngine:
    def __init__(
        self,
        broker: BrokerInterface,
        strategy: Strategy,
        portfolio: Optional[PaperPortfolio] = None,
        sizing: Optional[PositionSizeConfig] = None,
        notifiers: Optional[List[Notifier]] = None,
    ):
        if not broker.paper_mode:
            raise ValueError(
                "PaperTradingEngine requires a broker adapter constructed with "
                "paper_mode=True. Refusing to run against a live-mode adapter."
            )
        self.broker = broker
        self.strategy = strategy
        self.portfolio = portfolio or PaperPortfolio()
        self.sizing = sizing or PositionSizeConfig()
        self.notifiers = notifiers or []

    def _notify(self, method_name: str, *args) -> None:
        """Call a notifier method on every registered notifier, best-effort.
        A broken notifier must never take down the trading loop."""
        for notifier in self.notifiers:
            try:
                getattr(notifier, method_name)(*args)
            except Exception as exc:
                logger.warning("Notifier %s failed on %s: %s", notifier.name, method_name, exc)

    def _position_size(self, candidate: TradeCandidate, current_price: float) -> float:
        equity = self.portfolio.equity({candidate.symbol: current_price})
        risk_amount = equity * (self.sizing.risk_per_trade_pct / 100)
        per_unit_risk = abs(current_price - candidate.stop_loss)
        if per_unit_risk <= 0:
            return 0.0
        qty_by_risk = risk_amount / per_unit_risk

        max_position_value = equity * (self.sizing.max_position_pct / 100)
        qty_by_cap = max_position_value / current_price

        return round(min(qty_by_risk, qty_by_cap), 6)

    def on_bars(self, symbol: str, bars: List[PriceBar]) -> Optional[TradeCandidate]:
        """
        Call this each time a new bar closes. Evaluates the strategy,
        opens a simulated position sized by risk if a candidate appears
        and no position is already open on that symbol.
        """
        # Manage any open position against the live quote first.
        if symbol in self.portfolio.positions:
            quote = self.broker.get_quote(symbol)
            exit_reason = self.portfolio.check_stop_and_target(symbol, quote.last)
            if exit_reason:
                trade = self.portfolio.close_position(symbol, quote.last, exit_reason)
                logger.info(
                    "Closed paper position %s via %s at %.2f (pnl=%.2f)",
                    symbol, exit_reason, quote.last, trade.pnl,
                )
                self._notify("notify_position_closed", trade)
            return None  # don't stack a new entry while a position is open

        candidate = self.strategy.evaluate(symbol, bars)
        if candidate is None:
            return None

        quote = self.broker.get_quote(symbol)
        current_price = quote.last
        quantity = self._position_size(candidate, current_price)
        if quantity <= 0:
            logger.warning("Position size computed as 0 for %s, skipping candidate", symbol)
            return candidate

        self.portfolio.open_position(
            symbol=symbol,
            quantity=quantity,
            fill_price=current_price,
            strategy_name=candidate.strategy_name,
            stop_loss=candidate.stop_loss,
            profit_target=candidate.profit_target,
        )
        logger.info(
            "Opened paper position %s qty=%.6f @ %.2f (stop=%.2f target=%.2f, confidence=%.2f)",
            symbol, quantity, current_price, candidate.stop_loss,
            candidate.profit_target, candidate.confidence,
        )
        self._notify("notify_candidate_opened", candidate, quantity, current_price)
        return candidate

    def mark_to_market(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch current prices for all symbols with open positions, for reporting."""
        prices = {}
        for symbol in symbols:
            try:
                prices[symbol] = self.broker.get_quote(symbol).last
            except Exception as exc:
                logger.warning("Failed to fetch quote for %s: %s", symbol, exc)
        return prices

    def performance_report(self, symbols: List[str]) -> dict:
        prices = self.mark_to_market(symbols)
        summary = self.portfolio.summary(prices)
        summary["strategy"] = self.strategy.name

        trades = self.portfolio.closed_trades
        if trades:
            wins = [t for t in trades if t.pnl > 0]
            summary["win_rate_pct"] = round(len(wins) / len(trades) * 100, 1)
            summary["avg_return_pct"] = round(
                sum(t.pnl_pct for t in trades) / len(trades), 2
            )
            gross_profit = sum(t.pnl for t in wins) or 0.0
            losses = [t for t in trades if t.pnl <= 0]
            gross_loss = abs(sum(t.pnl for t in losses)) or 1e-9
            summary["profit_factor"] = round(gross_profit / gross_loss, 2)
        return summary
