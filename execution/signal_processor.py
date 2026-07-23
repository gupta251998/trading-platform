"""
Signal Processor — converts strategy signals to approval queue entries.

This layer bridges the strategy engine (which generates signals) to the
approval queue (which routes to human approval).

Works in both paper and live modes:
- Paper mode: signals are logged but not sent to approval queue
- Live mode: signals are sent to approval queue for human approval
"""

import json
import logging
from typing import Optional

from broker.types import OrderSide
from execution.approval_queue import ApprovalQueueManager
from models.all import Signal
from risk.engine import RiskEngine
from database.connection import session_scope
from decimal import Decimal

logger = logging.getLogger("signal_processor")


class SignalProcessor:
    """Processes strategy signals and routes them appropriately."""

    def __init__(
        self,
        approval_queue: Optional[ApprovalQueueManager] = None,
        risk_engine: Optional[RiskEngine] = None,
    ):
        self.approval_queue = approval_queue
        self.risk_engine = risk_engine

    def process_signal(
        self,
        symbol: str,
        strategy_name: str,
        direction: str,  # LONG or SHORT
        entry_zone_low: float,
        entry_zone_high: float,
        stop_loss: float,
        profit_target: float,
        confidence: float,
        technical_explanation: str,
    ) -> Optional[int]:
        """
        Process a strategy signal.
        
        Paper mode: logs the signal to database, does NOT send to approval queue
        Live mode: sends to approval queue for human approval
        
        Returns:
          - approval_id if sent to queue (live mode)
          - signal_id if just logged (paper mode)
          - None if signal was rejected
        """
        # Normalize direction
        direction = direction.upper()
        if direction not in ("LONG", "SHORT"):
            logger.error(f"Invalid direction: {direction}")
            return None
        
        # Save signal to database
        signal_id = self._save_signal_to_db(
            symbol=symbol,
            strategy_name=strategy_name,
            direction=direction,
            entry_zone_low=entry_zone_low,
            entry_zone_high=entry_zone_high,
            stop_loss=stop_loss,
            profit_target=profit_target,
            confidence=confidence,
            technical_explanation=technical_explanation,
        )
        logger.info(
            f"Signal {signal_id}: {strategy_name} {direction} {symbol} @ "
            f"{entry_zone_low:.2f}-{entry_zone_high:.2f} "
            f"(confidence: {confidence:.0%})"
        )

        # If we have approval queue + risk engine, route to live execution
        if self.approval_queue and self.risk_engine:
            return self._route_to_approval_queue(
                signal_id=signal_id,
                symbol=symbol,
                strategy_name=strategy_name,
                direction=direction,
                entry_zone_low=entry_zone_low,
                entry_zone_high=entry_zone_high,
                stop_loss=stop_loss,
                profit_target=profit_target,
                confidence=confidence,
                technical_explanation=technical_explanation,
            )
        
        # Otherwise, just return the signal ID (paper mode)
        return signal_id

    def _save_signal_to_db(
        self,
        symbol: str,
        strategy_name: str,
        direction: str,
        entry_zone_low: float,
        entry_zone_high: float,
        stop_loss: float,
        profit_target: float,
        confidence: float,
        technical_explanation: str,
    ) -> int:
        """Save signal to database and return ID."""
        with session_scope() as session:
            signal = Signal(
                symbol=symbol,
                strategy_name=strategy_name,
                direction=direction,
                entry_zone_low=Decimal(str(entry_zone_low)),
                entry_zone_high=Decimal(str(entry_zone_high)),
                stop_loss=Decimal(str(stop_loss)),
                profit_target=Decimal(str(profit_target)),
                confidence=confidence,
                technical_explanation=technical_explanation,
                status="pending",
            )
            session.add(signal)
            session.flush()
            return signal.id

    def _route_to_approval_queue(
        self,
        signal_id: int,
        symbol: str,
        strategy_name: str,
        direction: str,
        entry_zone_low: float,
        entry_zone_high: float,
        stop_loss: float,
        profit_target: float,
        confidence: float,
        technical_explanation: str,
    ) -> Optional[int]:
        """Route a signal to the approval queue for live execution."""
        # Determine entry price (use midpoint of entry zone)
        entry_price = (entry_zone_low + entry_zone_high) / 2.0
        
        # Determine quantity (let risk engine calculate based on stop-loss)
        sizing = self.risk_engine.calculate_position_size(
            entry_price=entry_price,
            stop_loss=stop_loss,
        )
        
        if not sizing.is_within_limits:
            logger.warning(f"Position sizing rejected for {symbol}: {sizing.reason}")
            return None
        
        # Run full pre-execution risk checks
        risk_check = self.risk_engine.pre_execution_check(
            symbol=symbol,
            entry_price=entry_price,
            quantity=sizing.quantity,
            stop_loss=stop_loss,
        )
        
        if not risk_check.approved:
            logger.warning(f"Risk check rejected for {symbol}: {risk_check.reason}")
            return None
        
        # All checks passed, route to approval queue
        try:
            approval = self.approval_queue.add_to_queue(
                symbol=symbol,
                strategy_name=strategy_name,
                order_type="MARKET",
                side="BUY" if direction == "LONG" else "SELL",
                quantity=sizing.quantity,
                limit_price=None,
                stop_price=None,
                entry_price=entry_price,
                stop_loss=stop_loss,
                profit_target=profit_target,
                confidence=confidence,
                risk_metrics={
                    "technical_explanation": technical_explanation,
                    "entry_zone": [entry_zone_low, entry_zone_high],
                    "sizing_result": {
                        "quantity": sizing.quantity,
                        "estimated_cost": sizing.estimated_cost,
                        "estimated_fee": sizing.estimated_fee,
                        "risk_reward_ratio": sizing.risk_reward_ratio,
                    },
                },
                signal_id=signal_id,
            )
            logger.info(f"Routed signal {signal_id} to approval queue {approval.id}")
            return approval.id
        except Exception as exc:
            logger.error(f"Failed to add signal {signal_id} to approval queue: {exc}")
            return None

    def get_pending_signals(self, limit: int = 50):
        """Get pending signals from database."""
        with session_scope() as session:
            from models.all import Signal
            signals = session.query(Signal).filter(
                Signal.status == "pending"
            ).order_by(Signal.created_at.desc()).limit(limit).all()
            return signals
