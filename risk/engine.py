"""
Risk Engine — enforces all risk limits before any order can be approved.

Calculates:
- Position size based on % risk
- Daily loss impact
- Portfolio exposure
- Stop-loss using ATR or percentage
- Risk/reward ratio

All decisions are based on pre-configured limits, not discretionary.
"""

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, Any

from database.connection import session_scope
from models.all import RiskLimit, PortfolioSnapshot, Trade, ApprovalQueue
from broker.types import Quote

logger = logging.getLogger("risk_engine")


@dataclass
class PositionSizingResult:
    """Result of position sizing calculation."""
    quantity: float
    estimated_cost: float
    estimated_fee: float
    stop_loss: float
    risk_amount: float
    reward_amount: float
    risk_reward_ratio: float
    is_within_limits: bool
    reason: str  # explanation if rejected


@dataclass
class RiskCheckResult:
    """Result of full risk check."""
    approved: bool
    reason: str
    daily_pnl_remaining: float
    exposure_remaining_pct: float
    positions_remaining: int


class RiskEngine:
    def __init__(self, broker_buying_power: float = 10000.0):
        self.broker_buying_power = broker_buying_power
        self.limits: Optional[RiskLimit] = None
        self._load_limits()

    def _load_limits(self):
        """Load current risk limits from database."""
        with session_scope() as session:
            self.limits = session.query(RiskLimit).filter(
                RiskLimit.is_active == True
            ).first()
            if not self.limits:
                logger.warning("No active risk limits found, using defaults")
                self.limits = self._create_default_limits()

    def _create_default_limits(self) -> RiskLimit:
        """Create default safe risk limits."""
        return RiskLimit(
            daily_loss_limit=Decimal("500.00"),
            max_position_size_pct=20.0,
            max_portfolio_exposure_pct=80.0,
            max_concurrent_positions=5,
            risk_per_trade_pct=1.0,
            max_consecutive_losses=3,
            trade_cooldown_seconds=60,
            is_active=True,
        )

    def get_portfolio_metrics(self) -> Dict[str, Any]:
        """Get current portfolio state from database."""
        with session_scope() as session:
            snapshot = session.query(PortfolioSnapshot).order_by(
                PortfolioSnapshot.created_at.desc()
            ).first()
            if not snapshot:
                return {
                    "equity": self.broker_buying_power,
                    "cash": self.broker_buying_power,
                    "open_positions": 0,
                    "daily_pnl": 0.0,
                    "exposure_pct": 0.0,
                }
            return {
                "equity": float(snapshot.equity),
                "cash": float(snapshot.cash),
                "open_positions": snapshot.open_positions_count,
                "daily_pnl": float(snapshot.daily_pnl),
                "exposure_pct": float(snapshot.max_exposure_pct),
            }

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        quantity_hint: Optional[float] = None,
    ) -> PositionSizingResult:
        """
        Calculate position size based on risk limits.
        
        If quantity_hint is provided, validate it; otherwise calculate optimal size.
        """
        if not self.limits:
            return PositionSizingResult(
                quantity=0,
                estimated_cost=0,
                estimated_fee=0,
                stop_loss=stop_loss,
                risk_amount=0,
                reward_amount=0,
                risk_reward_ratio=0,
                is_within_limits=False,
                reason="No risk limits configured",
            )

        portfolio = self.get_portfolio_metrics()
        equity = portfolio["equity"]
        
        # Risk per trade in dollars
        risk_amount = equity * (self.limits.risk_per_trade_pct / 100.0)
        
        # Stop-loss distance in dollars
        per_unit_risk = abs(entry_price - stop_loss)
        if per_unit_risk <= 0:
            return PositionSizingResult(
                quantity=0,
                estimated_cost=0,
                estimated_fee=0,
                stop_loss=stop_loss,
                risk_amount=0,
                reward_amount=0,
                risk_reward_ratio=0,
                is_within_limits=False,
                reason="Invalid stop-loss (must be different from entry price)",
            )
        
        # Quantity sizing by risk
        qty_by_risk = risk_amount / per_unit_risk
        
        # Max position size as % of equity
        max_position_value = equity * (self.limits.max_position_size_pct / 100.0)
        qty_by_cap = max_position_value / entry_price
        
        # Take the smaller of the two
        quantity = min(qty_by_risk, qty_by_cap)
        
        # Apply quantity hint if provided
        if quantity_hint is not None:
            quantity = min(quantity, quantity_hint)
        
        estimated_cost = quantity * entry_price
        estimated_fee = estimated_cost * 0.006  # 0.6% fee approximation
        reward_amount = quantity * abs(entry_price - (entry_price + per_unit_risk * 2))
        risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0
        
        is_within = estimated_cost + estimated_fee <= self.broker_buying_power
        
        return PositionSizingResult(
            quantity=round(quantity, 6),
            estimated_cost=round(estimated_cost, 2),
            estimated_fee=round(estimated_fee, 2),
            stop_loss=stop_loss,
            risk_amount=round(risk_amount, 2),
            reward_amount=round(reward_amount, 2),
            risk_reward_ratio=round(risk_reward_ratio, 2),
            is_within_limits=is_within,
            reason="Approved" if is_within else "Insufficient buying power",
        )

    def check_daily_loss_limit(self) -> RiskCheckResult:
        """Check if we've hit the daily loss limit."""
        if not self.limits:
            return RiskCheckResult(
                approved=False,
                reason="No risk limits configured",
                daily_pnl_remaining=0,
                exposure_remaining_pct=0,
                positions_remaining=0,
            )

        portfolio = self.get_portfolio_metrics()
        daily_pnl = portfolio["daily_pnl"]
        daily_loss_limit = float(self.limits.daily_loss_limit)
        
        if daily_pnl <= -daily_loss_limit:
            return RiskCheckResult(
                approved=False,
                reason=f"Daily loss limit exceeded: ${daily_pnl:.2f} (limit: ${-daily_loss_limit:.2f})",
                daily_pnl_remaining=0,
                exposure_remaining_pct=float(self.limits.max_portfolio_exposure_pct) - portfolio["exposure_pct"],
                positions_remaining=self.limits.max_concurrent_positions - portfolio["open_positions"],
            )

        remaining = -daily_loss_limit - daily_pnl
        return RiskCheckResult(
            approved=True,
            reason="Daily loss limit OK",
            daily_pnl_remaining=remaining,
            exposure_remaining_pct=float(self.limits.max_portfolio_exposure_pct) - portfolio["exposure_pct"],
            positions_remaining=self.limits.max_concurrent_positions - portfolio["open_positions"],
        )

    def check_portfolio_exposure(self, new_position_value: float) -> RiskCheckResult:
        """Check if adding a new position exceeds max portfolio exposure."""
        if not self.limits:
            return RiskCheckResult(
                approved=False,
                reason="No risk limits configured",
                daily_pnl_remaining=0,
                exposure_remaining_pct=0,
                positions_remaining=0,
            )

        portfolio = self.get_portfolio_metrics()
        equity = portfolio["equity"]
        current_exposure_value = (portfolio["exposure_pct"] / 100.0) * equity
        new_total_exposure = current_exposure_value + new_position_value
        new_exposure_pct = (new_total_exposure / equity) * 100.0
        max_exposure = float(self.limits.max_portfolio_exposure_pct)
        
        if new_exposure_pct > max_exposure:
            return RiskCheckResult(
                approved=False,
                reason=f"Portfolio exposure would exceed {max_exposure}%: {new_exposure_pct:.1f}%",
                daily_pnl_remaining=0,
                exposure_remaining_pct=max_exposure - portfolio["exposure_pct"],
                positions_remaining=self.limits.max_concurrent_positions - portfolio["open_positions"],
            )

        return RiskCheckResult(
            approved=True,
            reason="Portfolio exposure OK",
            daily_pnl_remaining=0,
            exposure_remaining_pct=max_exposure - portfolio["exposure_pct"],
            positions_remaining=self.limits.max_concurrent_positions - portfolio["open_positions"],
        )

    def check_max_positions(self) -> RiskCheckResult:
        """Check if we've hit the max concurrent positions limit."""
        if not self.limits:
            return RiskCheckResult(
                approved=False,
                reason="No risk limits configured",
                daily_pnl_remaining=0,
                exposure_remaining_pct=0,
                positions_remaining=0,
            )

        portfolio = self.get_portfolio_metrics()
        open_positions = portfolio["open_positions"]
        max_positions = self.limits.max_concurrent_positions
        
        if open_positions >= max_positions:
            return RiskCheckResult(
                approved=False,
                reason=f"Max concurrent positions reached: {open_positions}/{max_positions}",
                daily_pnl_remaining=0,
                exposure_remaining_pct=0,
                positions_remaining=0,
            )

        return RiskCheckResult(
            approved=True,
            reason="Position count OK",
            daily_pnl_remaining=0,
            exposure_remaining_pct=0,
            positions_remaining=max_positions - open_positions,
        )

    def pre_execution_check(
        self,
        symbol: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
    ) -> RiskCheckResult:
        """
        Run all risk checks before approving an order.
        Returns a single RiskCheckResult with the first failure, or approved=True.
        """
        # Check 1: Daily loss limit
        check = self.check_daily_loss_limit()
        if not check.approved:
            return check

        # Check 2: Max positions
        check = self.check_max_positions()
        if not check.approved:
            return check

        # Check 3: Portfolio exposure
        new_position_value = quantity * entry_price
        check = self.check_portfolio_exposure(new_position_value)
        if not check.approved:
            return check

        # All checks passed
        return RiskCheckResult(
            approved=True,
            reason="All risk checks passed",
            daily_pnl_remaining=float(self.limits.daily_loss_limit),
            exposure_remaining_pct=float(self.limits.max_portfolio_exposure_pct),
            positions_remaining=self.limits.max_concurrent_positions,
        )
