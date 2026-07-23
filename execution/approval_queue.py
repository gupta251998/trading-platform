"""
Approval Queue Manager — manages live orders pending human approval.

Every live order goes into this queue and must be explicitly approved or
rejected by a human before it's submitted to the broker.

Critical property: no order ever reaches the broker without explicit human
approval. This queue is the single point of control for all live trading.
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any

from database.connection import session_scope
from models.all import ApprovalQueue, Signal
from risk.engine import RiskEngine

logger = logging.getLogger("approval_queue")


class ApprovalQueueManager:
    """Manages the approval queue for live orders."""

    def __init__(self, risk_engine: RiskEngine):
        self.risk_engine = risk_engine

    def add_to_queue(
        self,
        symbol: str,
        strategy_name: str,
        order_type: str,
        side: str,
        quantity: float,
        limit_price: Optional[float],
        stop_price: Optional[float],
        entry_price: float,
        stop_loss: float,
        profit_target: float,
        confidence: float,
        risk_metrics: Dict[str, Any],
        signal_id: Optional[int] = None,
    ) -> ApprovalQueue:
        """
        Add a new order to the approval queue.
        
        Returns the created ApprovalQueue record.
        """
        estimated_cost = quantity * entry_price
        estimated_fee = estimated_cost * 0.006  # 0.6% fee
        
        reason = (
            f"Signal from {strategy_name}: {side} {quantity:.6f} {symbol} "
            f"@ {entry_price:.2f} (confidence: {confidence:.0%}, "
            f"stop: {stop_loss:.2f}, target: {profit_target:.2f})"
        )

        with session_scope() as session:
            approval = ApprovalQueue(
                symbol=symbol,
                strategy_name=strategy_name,
                signal_id=signal_id,
                order_type=order_type,
                side=side,
                quantity=Decimal(str(quantity)),
                limit_price=Decimal(str(limit_price)) if limit_price else None,
                stop_price=Decimal(str(stop_price)) if stop_price else None,
                reason=reason,
                estimated_cost=Decimal(str(estimated_cost)),
                estimated_fee=Decimal(str(estimated_fee)),
                risk_metrics=json.dumps(risk_metrics),
                status="pending",
            )
            session.add(approval)
            session.flush()
            approval_id = approval.id
            logger.info(f"Added order {approval_id} to approval queue: {symbol} {side} {quantity}")

        return ApprovalQueue(id=approval_id)

    def get_pending_approvals(self, limit: int = 50) -> List[ApprovalQueue]:
        """Get all pending orders awaiting approval."""
        with session_scope() as session:
            approvals = session.query(ApprovalQueue).filter(
                ApprovalQueue.status == "pending"
            ).order_by(
                ApprovalQueue.created_at.desc()
            ).limit(limit).all()
            return approvals

    def get_approval_by_id(self, approval_id: int) -> Optional[ApprovalQueue]:
        """Get a specific approval record."""
        with session_scope() as session:
            approval = session.query(ApprovalQueue).filter(
                ApprovalQueue.id == approval_id
            ).first()
            return approval

    def approve_order(
        self,
        approval_id: int,
        approved_by: str = "user",
    ) -> ApprovalQueue:
        """
        Approve an order and mark it ready for broker submission.
        
        This is the explicit human approval step. No order reaches the
        broker without this being called first.
        """
        with session_scope() as session:
            approval = session.query(ApprovalQueue).filter(
                ApprovalQueue.id == approval_id
            ).first()
            if not approval:
                raise ValueError(f"Approval {approval_id} not found")
            
            if approval.status != "pending":
                raise ValueError(
                    f"Cannot approve order {approval_id}: status is {approval.status}, not pending"
                )
            
            approval.status = "approved"
            approval.approved_by = approved_by
            approval.approved_at = datetime.now(timezone.utc)
            session.commit()
            logger.info(
                f"Approved order {approval_id}: {approval.symbol} {approval.side} "
                f"{approval.quantity} (approved by {approved_by})"
            )
            return approval

    def reject_order(
        self,
        approval_id: int,
        reason: str,
    ) -> ApprovalQueue:
        """
        Reject an order. It will not be submitted to the broker.
        """
        with session_scope() as session:
            approval = session.query(ApprovalQueue).filter(
                ApprovalQueue.id == approval_id
            ).first()
            if not approval:
                raise ValueError(f"Approval {approval_id} not found")
            
            if approval.status != "pending":
                raise ValueError(
                    f"Cannot reject order {approval_id}: status is {approval.status}, not pending"
                )
            
            approval.status = "rejected"
            approval.rejected_reason = reason
            session.commit()
            logger.info(
                f"Rejected order {approval_id}: {approval.symbol} "
                f"{approval.side} {approval.quantity} ({reason})"
            )
            return approval

    def mark_submitted_to_broker(
        self,
        approval_id: int,
        broker_order_id: str,
    ) -> ApprovalQueue:
        """
        Mark an approved order as submitted to the broker.
        """
        with session_scope() as session:
            approval = session.query(ApprovalQueue).filter(
                ApprovalQueue.id == approval_id
            ).first()
            if not approval:
                raise ValueError(f"Approval {approval_id} not found")
            
            approval.status = "submitted"
            approval.broker_order_id = broker_order_id
            approval.submitted_to_broker_at = datetime.now(timezone.utc)
            session.commit()
            logger.info(
                f"Submitted order {approval_id} to broker with ID {broker_order_id}"
            )
            return approval

    def get_approval_queue_stats(self) -> Dict[str, int]:
        """Get stats on the approval queue."""
        with session_scope() as session:
            pending = session.query(ApprovalQueue).filter(
                ApprovalQueue.status == "pending"
            ).count()
            approved = session.query(ApprovalQueue).filter(
                ApprovalQueue.status == "approved"
            ).count()
            submitted = session.query(ApprovalQueue).filter(
                ApprovalQueue.status == "submitted"
            ).count()
            rejected = session.query(ApprovalQueue).filter(
                ApprovalQueue.status == "rejected"
            ).count()
            return {
                "pending": pending,
                "approved": approved,
                "submitted": submitted,
                "rejected": rejected,
                "total": pending + approved + submitted + rejected,
            }
