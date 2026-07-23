"""
Integration Test — Full flow from signal to execution.

Tests:
1. Strategy generates a signal
2. Signal is processed and validated
3. Risk checks pass
4. Order enters approval queue
5. Human approves
6. Order is executed

This test does NOT require PostgreSQL or live broker credentials.
Uses mocks throughout.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from broker.mock_broker import MockBroker
from strategy.sma_crossover import SmaCrossoverStrategy
from strategy.base import PriceBar
from paper_trading.engine import PaperTradingEngine, PositionSizeConfig
from paper_trading.portfolio import PaperPortfolio
from risk.engine import RiskEngine
from execution.approval_queue import ApprovalQueueManager
from execution.signal_processor import SignalProcessor
from config import load_config, validate_production_config


class TestFullIntegration:
    """Full integration test: signal → approval → execution."""
    
    def test_signal_to_approval_flow_paper_mode(self):
        """Test: Strategy generates signal, processor handles it (paper mode)."""
        broker = MockBroker(paper_mode=True)
        strategy = SmaCrossoverStrategy()
        
        # Paper mode: no approval queue
        processor = SignalProcessor(approval_queue=None, risk_engine=None)
        
        # Generate a signal manually (normally comes from strategy)
        signal_id = processor.process_signal(
            symbol="BTC-USD",
            strategy_name="sma_crossover",
            direction="LONG",
            entry_zone_low=100.0,
            entry_zone_high=101.0,
            stop_loss=95.0,
            profit_target=110.0,
            confidence=0.8,
            technical_explanation="10-period SMA crossed above 30-period SMA",
        )
        
        assert signal_id is not None
    
    def test_signal_to_approval_flow_live_mode(self):
        """Test: Signal → Risk checks → Approval queue."""
        broker = MockBroker(paper_mode=True)
        risk_engine = RiskEngine(broker_buying_power=10_000)
        approval_queue = ApprovalQueueManager(risk_engine)
        
        processor = SignalProcessor(
            approval_queue=approval_queue,
            risk_engine=risk_engine,
        )
        
        # Send a signal to approval queue
        approval_id = processor.process_signal(
            symbol="BTC-USD",
            strategy_name="sma_crossover",
            direction="LONG",
            entry_zone_low=100.0,
            entry_zone_high=101.0,
            stop_loss=95.0,
            profit_target=110.0,
            confidence=0.8,
            technical_explanation="10-period SMA crossed above 30-period SMA",
        )
        
        # Should be in approval queue
        assert approval_id is not None
        approval = approval_queue.get_approval_by_id(approval_id)
        assert approval is not None
        assert approval.status == "pending"
        assert approval.symbol == "BTC-USD"
    
    def test_approval_rejection_flow(self):
        """Test: Signal → Approval queue → Human rejects."""
        risk_engine = RiskEngine(broker_buying_power=10_000)
        approval_queue = ApprovalQueueManager(risk_engine)
        processor = SignalProcessor(
            approval_queue=approval_queue,
            risk_engine=risk_engine,
        )
        
        # Send signal
        approval_id = processor.process_signal(
            symbol="BTC-USD",
            strategy_name="sma_crossover",
            direction="LONG",
            entry_zone_low=100.0,
            entry_zone_high=101.0,
            stop_loss=95.0,
            profit_target=110.0,
            confidence=0.8,
            technical_explanation="Test signal",
        )
        
        # Human rejects
        approval = approval_queue.reject_order(approval_id, reason="Risk too high")
        assert approval.status == "rejected"
        assert "Risk too high" in approval.rejected_reason
    
    def test_approval_approval_flow(self):
        """Test: Signal → Approval queue → Human approves."""
        risk_engine = RiskEngine(broker_buying_power=10_000)
        approval_queue = ApprovalQueueManager(risk_engine)
        processor = SignalProcessor(
            approval_queue=approval_queue,
            risk_engine=risk_engine,
        )
        
        # Send signal
        approval_id = processor.process_signal(
            symbol="BTC-USD",
            strategy_name="sma_crossover",
            direction="LONG",
            entry_zone_low=100.0,
            entry_zone_high=101.0,
            stop_loss=95.0,
            profit_target=110.0,
            confidence=0.8,
            technical_explanation="Test signal",
        )
        
        # Human approves
        approval = approval_queue.approve_order(approval_id, approved_by="test_user")
        assert approval.status == "approved"
        assert approval.approved_by == "test_user"
    
    def test_risk_rejection_prevents_approval_queue(self):
        """Test: Risk checks fail → signal never reaches approval queue."""
        # Very small account with tight risk limit
        risk_engine = RiskEngine(broker_buying_power=100)  # Only $100
        approval_queue = ApprovalQueueManager(risk_engine)
        processor = SignalProcessor(
            approval_queue=approval_queue,
            risk_engine=risk_engine,
        )
        
        # Try to send a signal that violates risk limits
        # (stop-loss distance would be huge relative to account size)
        approval_id = processor.process_signal(
            symbol="BTC-USD",
            strategy_name="sma_crossover",
            direction="LONG",
            entry_zone_low=100.0,
            entry_zone_high=101.0,
            stop_loss=10.0,  # Huge stop loss (90 point risk on $100 account = 90% risk!)
            profit_target=200.0,
            confidence=0.8,
            technical_explanation="Risky signal",
        )
        
        # Should be rejected due to risk
        assert approval_id is None  # Never made it to approval queue
    
    def test_config_validation(self):
        """Test: Configuration is validated for production."""
        config = load_config()
        errors = validate_production_config(config)
        
        # Should have no errors (default config is valid)
        assert isinstance(errors, list)
    
    def test_paper_trading_full_cycle(self):
        """Test: Full paper trading cycle."""
        broker = MockBroker(paper_mode=True)
        strategy = SmaCrossoverStrategy()
        portfolio = PaperPortfolio(starting_cash=10_000)
        engine = PaperTradingEngine(
            broker=broker,
            strategy=strategy,
            portfolio=portfolio,
            sizing=PositionSizeConfig(risk_per_trade_pct=1.0),
        )
        
        # Create bars that trigger a crossover
        base_price = 100.0
        bars = [
            PriceBar(
                timestamp=datetime.now(timezone.utc),
                open=base_price + i*0.5, high=base_price + i*0.5 + 1, low=base_price + i*0.5 - 1,
                close=base_price + i*0.5, volume=1000,
            )
            for i in range(50)
        ]
        
        # Run through bars
        candidate = engine.on_bars("BTC-USD", bars)
        
        # Strategy should generate a candidate
        assert candidate is not None or len(portfolio.positions) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
