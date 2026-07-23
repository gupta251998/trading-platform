"""
Paper trading portfolio — tracks simulated cash, positions, and closed
trades in memory (this slice) with a clean seam to swap in Postgres
persistence later (see PORTFOLIO_PERSISTENCE_TODO below).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from broker.types import OrderSide

# PORTFOLIO_PERSISTENCE_TODO: replace the in-memory dict/list state below
# with a Postgres-backed repository (paper_positions, paper_trades tables)
# before this leaves "vertical slice" status. Keeping it in-memory for now
# so the engine logic can be unit tested without a DB dependency.


@dataclass
class PaperPosition:
    symbol: str
    quantity: float
    avg_entry_price: float
    stop_loss: Optional[float] = None
    profit_target: Optional[float] = None
    opened_at: datetime = field(default_factory=datetime.utcnow)
    strategy_name: str = ""


@dataclass
class ClosedTrade:
    symbol: str
    strategy_name: str
    side: OrderSide
    quantity: float
    entry_price: float
    exit_price: float
    opened_at: datetime
    closed_at: datetime
    fee_paid: float
    exit_reason: str  # "stop_loss" | "profit_target" | "manual"

    @property
    def pnl(self) -> float:
        gross = (self.exit_price - self.entry_price) * self.quantity
        return gross - self.fee_paid

    @property
    def pnl_pct(self) -> float:
        cost_basis = self.entry_price * self.quantity
        return (self.pnl / cost_basis) * 100 if cost_basis else 0.0


class PaperPortfolio:
    def __init__(self, starting_cash: float = 10_000.0, fee_rate: float = 0.006):
        """
        fee_rate default 0.6% approximates Coinbase Advanced's taker fee at
        the lowest volume tier — override with the account's actual tier
        for realistic paper results.
        """
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.fee_rate = fee_rate
        self.positions: Dict[str, PaperPosition] = {}
        self.closed_trades: List[ClosedTrade] = []

    # ---- Simulated execution -----------------------------------------

    def open_position(
        self,
        symbol: str,
        quantity: float,
        fill_price: float,
        strategy_name: str,
        stop_loss: Optional[float] = None,
        profit_target: Optional[float] = None,
    ) -> PaperPosition:
        cost = quantity * fill_price
        fee = cost * self.fee_rate
        total_cost = cost + fee
        if total_cost > self.cash:
            raise ValueError(
                f"Insufficient paper cash: need {total_cost:.2f}, have {self.cash:.2f}"
            )
        self.cash -= total_cost
        position = PaperPosition(
            symbol=symbol,
            quantity=quantity,
            avg_entry_price=fill_price,
            stop_loss=stop_loss,
            profit_target=profit_target,
            strategy_name=strategy_name,
        )
        self.positions[symbol] = position
        return position

    def close_position(self, symbol: str, fill_price: float, exit_reason: str = "manual") -> ClosedTrade:
        position = self.positions.pop(symbol, None)
        if position is None:
            raise KeyError(f"No open paper position for {symbol}")

        proceeds = position.quantity * fill_price
        fee = proceeds * self.fee_rate
        self.cash += proceeds - fee

        trade = ClosedTrade(
            symbol=symbol,
            strategy_name=position.strategy_name,
            side=OrderSide.SELL,
            quantity=position.quantity,
            entry_price=position.avg_entry_price,
            exit_price=fill_price,
            opened_at=position.opened_at,
            closed_at=datetime.utcnow(),
            fee_paid=fee,
            exit_reason=exit_reason,
        )
        self.closed_trades.append(trade)
        return trade

    # ---- Risk management checks (called each price update) -----------

    def check_stop_and_target(self, symbol: str, current_price: float) -> Optional[str]:
        """Returns 'stop_loss' or 'profit_target' if the position should be
        closed at current_price, else None."""
        position = self.positions.get(symbol)
        if position is None:
            return None
        if position.stop_loss is not None and current_price <= position.stop_loss:
            return "stop_loss"
        if position.profit_target is not None and current_price >= position.profit_target:
            return "profit_target"
        return None

    # ---- Reporting -----------------------------------------------------

    def equity(self, current_prices: Dict[str, float]) -> float:
        market_value = sum(
            pos.quantity * current_prices.get(sym, pos.avg_entry_price)
            for sym, pos in self.positions.items()
        )
        return self.cash + market_value

    def summary(self, current_prices: Dict[str, float]) -> dict:
        equity = self.equity(current_prices)
        return {
            "starting_cash": self.starting_cash,
            "cash": round(self.cash, 2),
            "equity": round(equity, 2),
            "total_return_pct": round((equity / self.starting_cash - 1) * 100, 2),
            "open_positions": len(self.positions),
            "closed_trades": len(self.closed_trades),
        }
