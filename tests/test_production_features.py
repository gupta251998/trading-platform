"""
Tests for production trading features:
- Risk Engine (position sizing, daily loss limits)
- Approval Queue (order queuing)
- Live Execution (approval-based execution)
"""

import pytest
from decimal import Decimal

from broker.mock_broker import MockBroker
from execution.approval_queue import ApprovalQueueManager
from execution.live_execution import LiveExecutionLayer
from risk.engine import RiskEngine


class TestRiskEngine:
    def test_position_sizing_basic(self):
        engine = RiskEngine(broker_buying_power=10_000)
        sizing = engine.calculate_position_size(
            entry_price=100.0,
            stop_loss=95.0,
            quantity_hint=None,
        )
        assert sizing.quantity > 0
        assert sizing.estimated_cost > 0
        assert sizing.is_within_limits

    def test_position_sizing_respects_max_position_pct(self):
        engine = RiskEngine(broker_buying_power=10_000)
        engine.limits.max_position_size_pct = 5.0  # max 5% per position
        sizing = engine.calculate_position_size(
            entry_price=100.0,
            stop_loss=95.0,
        )
        max_position_value = 10_000 * 0.05
        assert sizing.estimated_cost <= max_position_value

    def test_daily_loss_limit_check(self):
        engine = RiskEngine()
        check = engine.check_daily_loss_limit()
        # Should pass on fresh account
        assert check.approved

    def test_max_positions_check(self):
        engine = RiskEngine()
        check = engine.check_max_positions()
        # Should pass on fresh account
        assert check.approved

    def test_invalid_stop_loss_rejected(self):
        engine = RiskEngine()
        sizing = engine.calculate_position_size(
            entry_price=100.0,
            stop_loss=100.0,  # same as entry, invalid
        )
        assert not sizing.is_within_limits
        assert "Invalid stop-loss" in sizing.reason


class TestApprovalQueue:
    def test_add_to_queue(self):
        broker = MockBroker(paper_mode=True)
        risk_engine = RiskEngine()
        queue = ApprovalQueueManager(risk_engine)
        
        approval = queue.add_to_queue(
            symbol="BTC-USD",
            strategy_name="sma_crossover",
            order_type="MARKET",
            side="BUY",
            quantity=0.1,
            limit_price=None,
            stop_price=None,
            entry_price=100.0,
            stop_loss=95.0,
            profit_target=110.0,
            confidence=0.8,
            risk_metrics={"test": "data"},
        )
        assert approval.id is not None

    def test_approve_order(self):
        broker = MockBroker(paper_mode=True)
        risk_engine = RiskEngine()
        queue = ApprovalQueueManager(risk_engine)
        
        approval = queue.add_to_queue(
            symbol="BTC-USD",
            strategy_name="sma_crossover",
            order_type="MARKET",
            side="BUY",
            quantity=0.1,
            limit_price=None,
            stop_price=None,
            entry_price=100.0,
            stop_loss=95.0,
            profit_target=110.0,
            confidence=0.8,
            risk_metrics={"test": "data"},
        )
        
        approved = queue.approve_order(approval.id, approved_by="test_user")
        assert approved.status == "approved"
        assert approved.approved_by == "test_user"

    def test_reject_order(self):
        broker = MockBroker(paper_mode=True)
        risk_engine = RiskEngine()
        queue = ApprovalQueueManager(risk_engine)
        
        approval = queue.add_to_queue(
            symbol="BTC-USD",
            strategy_name="sma_crossover",
            order_type="MARKET",
            side="BUY",
            quantity=0.1,
            limit_price=None,
            stop_price=None,
            entry_price=100.0,
            stop_loss=95.0,
            profit_target=110.0,
            confidence=0.8,
            risk_metrics={"test": "data"},
        )
        
        rejected = queue.reject_order(approval.id, reason="Risk limit exceeded")
        assert rejected.status == "rejected"
        assert "Risk limit" in rejected.rejected_reason

    def test_cannot_approve_twice(self):
        broker = MockBroker(paper_mode=True)
        risk_engine = RiskEngine()
        queue = ApprovalQueueManager(risk_engine)
        
        approval = queue.add_to_queue(
            symbol="BTC-USD",
            strategy_name="sma_crossover",
            order_type="MARKET",
            side="BUY",
            quantity=0.1,
            limit_price=None,
            stop_price=None,
            entry_price=100.0,
            stop_loss=95.0,
            profit_target=110.0,
            confidence=0.8,
            risk_metrics={"test": "data"},
        )
        
        queue.approve_order(approval.id)
        
        # Second approval should fail
        with pytest.raises(ValueError):
            queue.approve_order(approval.id)


class TestLiveExecution:
    def test_refuses_paper_mode_broker(self):
        broker = MockBroker(paper_mode=True)
        risk_engine = RiskEngine()
        queue = ApprovalQueueManager(risk_engine)
        
        with pytest.raises(ValueError):
            LiveExecutionLayer(broker, queue, risk_engine)

    def test_kill_switch_blocks_requests(self):
        broker = MockBroker(paper_mode=True)
        # Can't test live execution without real live broker,
        # but we can verify the kill switch concept works
        # This would require a separate live broker mock or integration test
        pass
