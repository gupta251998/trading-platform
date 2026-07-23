"""
Live Execution Layer — the safe path from signal to live order.

This layer:
1. Validates risk limits (risk engine)
2. Routes to approval queue (requires human approval)
3. Waits for approval
4. Submits approved orders to the broker
5. Never executes without explicit human approval

Critical invariant: an order only reaches broker.place_order() after all
three conditions are met:
  (a) Risk checks passed
  (b) Order was added to approval queue
  (c) Human explicitly approved it via approval_queue.approve_order()

If any condition fails, the order never touches the broker.
"""

import json
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from broker.interface import BrokerInterface
from broker.types import OrderRequest, OrderSide, OrderType, Order
from database.connection import session_scope
from models.all import Order as OrderModel, ApprovalQueue
from execution.approval_queue import ApprovalQueueManager
from risk.engine import RiskEngine

logger = logging.getLogger("live_execution")


class LiveExecutionLayer:
    """Safe live execution with mandatory approval queue."""

    def __init__(self, broker: BrokerInterface, approval_queue: ApprovalQueueManager, risk_engine: RiskEngine):
        if broker.paper_mode:
            raise ValueError("LiveExecutionLayer requires a live-mode broker (paper_mode=False)")
        self.broker = broker
        self.approval_queue = approval_queue
        self.risk_engine = risk_engine
        self.kill_switch_active = False

    def request_live_trade(
        self,
        symbol: str,
        strategy_name: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        profit_target: float,
        confidence: float,
        technical_explanation: str,
        side: str = "buy",
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        signal_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        Request a live trade. Routes to approval queue.
        
        Returns the approval_id (not broker_order_id). The order sits in
        the queue until a human approves it.
        """
        if self.kill_switch_active:
            logger.critical("KILL SWITCH ACTIVE: refusing all trade requests")
            return None

        # Step 1: Risk checks
        risk_check = self.risk_engine.pre_execution_check(
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
        )
        if not risk_check.approved:
            logger.warning(f"Risk check failed for {symbol}: {risk_check.reason}")
            return None

        # Step 2: Build risk metrics for display in approval UI
        sizing = self.risk_engine.calculate_position_size(entry_price, stop_loss, quantity)
        risk_metrics = {
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "profit_target": profit_target,
            "quantity": quantity,
            "risk_amount": sizing.risk_amount,
            "reward_amount": sizing.reward_amount,
            "risk_reward_ratio": sizing.risk_reward_ratio,
            "estimated_cost": sizing.estimated_cost,
            "estimated_fee": sizing.estimated_fee,
            "portfolio_impact": {
                "daily_pnl_remaining": risk_check.daily_pnl_remaining,
                "exposure_remaining_pct": risk_check.exposure_remaining_pct,
                "positions_remaining": risk_check.positions_remaining,
            },
            "technical_explanation": technical_explanation,
        }

        # Step 3: Add to approval queue (THIS IS WHERE IT SITS UNTIL HUMAN APPROVES)
        approval = self.approval_queue.add_to_queue(
            symbol=symbol,
            strategy_name=strategy_name,
            order_type=order_type,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_loss if order_type == "STOP" else None,
            entry_price=entry_price,
            stop_loss=stop_loss,
            profit_target=profit_target,
            confidence=confidence,
            risk_metrics=risk_metrics,
            signal_id=signal_id,
        )
        logger.info(
            f"Added trade request {approval.id} to approval queue: "
            f"{symbol} {side} {quantity} @ {entry_price}"
        )
        return approval.id

    def execute_approved_order(self, approval_id: int) -> Optional[Order]:
        """
        Execute an approved order through the broker.
        
        This should ONLY be called after human approval via
        approval_queue.approve_order(approval_id).
        
        Returns the Order from the broker, or None if execution failed.
        """
        if self.kill_switch_active:
            logger.critical("KILL SWITCH ACTIVE: refusing all executions")
            return None

        # Fetch the approval record
        approval = self.approval_queue.get_approval_by_id(approval_id)
        if not approval:
            logger.error(f"Approval {approval_id} not found")
            return None

        if approval.status != "approved":
            logger.error(
                f"Cannot execute order {approval_id}: status is {approval.status}, not approved. "
                f"Did you call approval_queue.approve_order() first?"
            )
            return None

        # Build the order request
        order_request = OrderRequest(
            symbol=approval.symbol,
            side=OrderSide(approval.side.lower()),
            order_type=OrderType(approval.order_type.lower()),
            quantity=float(approval.quantity),
            limit_price=float(approval.limit_price) if approval.limit_price else None,
            stop_price=float(approval.stop_price) if approval.stop_price else None,
            client_order_id=f"approval-{approval_id}",
        )

        # Execute through the broker
        try:
            broker_order = self.broker.place_order(order_request)
            logger.info(
                f"Executed approved order {approval_id} on broker: "
                f"{broker_order.broker_order_id} ({broker_order.status})"
            )
            
            # Mark as submitted
            self.approval_queue.mark_submitted_to_broker(
                approval_id=approval_id,
                broker_order_id=broker_order.broker_order_id,
            )

            # Log to database
            with session_scope() as session:
                order_model = OrderModel(
                    broker_order_id=broker_order.broker_order_id,
                    symbol=broker_order.symbol,
                    side=broker_order.side.value,
                    order_type=broker_order.order_type.value,
                    quantity=Decimal(str(broker_order.quantity)),
                    status=broker_order.status.value,
                    submitted_at=broker_order.created_at,
                    raw_response=json.dumps({"broker_order": str(broker_order.__dict__)}),
                )
                session.add(order_model)
            
            return broker_order

        except Exception as exc:
            logger.error(
                f"Failed to execute approved order {approval_id} on broker: {exc}",
                exc_info=True,
            )
            return None

    def activate_kill_switch(self):
        """
        EMERGENCY: Stop all trading immediately.
        
        This is a hard stop — no new orders are accepted, no approved
        orders are executed. Used when something goes catastrophically wrong.
        """
        self.kill_switch_active = True
        logger.critical("KILL SWITCH ACTIVATED - ALL TRADING STOPPED")

    def deactivate_kill_switch(self):
        """Re-enable trading after emergency stop (use carefully)."""
        self.kill_switch_active = False
        logger.warning("Kill switch deactivated")
