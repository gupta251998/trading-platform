"""
SQLAlchemy ORM models for trading platform.

Models represent database tables for:
- Trades (completed trades)
- Orders (live and filled orders)
- Positions (open positions)
- Signals (strategy signals)
- ApprovalQueue (pending orders awaiting approval)
- PortfolioSnapshot (historical portfolio state)
- RiskLimit (risk configuration)
- AuditLog (audit trail)
- BacktestResult (backtesting history)
- HistoricalPrice (historical OHLCV data for backtesting)
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Column, String, Float, Numeric, DateTime, Boolean, Text, Integer, Enum as SQLEnum, ForeignKey
)
from sqlalchemy.orm import relationship

from models.base import BaseModel


class OrderStatus(str, Enum):
    """Order status enumeration."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TradeStatus(str, Enum):
    """Trade status enumeration."""
    OPEN = "open"
    CLOSED = "closed"


class ExitReason(str, Enum):
    """Reason for closing a position."""
    STOP_LOSS = "stop_loss"
    PROFIT_TARGET = "profit_target"
    MANUAL = "manual"
    RISK_LIMIT = "risk_limit"
    EMERGENCY_STOP = "emergency_stop"


class Trade(BaseModel):
    """Represents a completed trade (entry and exit)."""

    __tablename__ = "trades"

    symbol = Column(String(20), nullable=False, index=True)
    strategy_name = Column(String(100), nullable=False)
    side = Column(String(10), nullable=False)  # BUY or SELL
    quantity = Column(Numeric(20, 8), nullable=False)
    entry_price = Column(Numeric(20, 8), nullable=False)
    exit_price = Column(Numeric(20, 8), nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True), nullable=False)
    pnl = Column(Numeric(20, 8), nullable=False)  # gross P&L
    pnl_pct = Column(Float, nullable=False)  # P&L percentage
    fee_paid = Column(Numeric(20, 8), nullable=False, default=0)
    exit_reason = Column(SQLEnum(ExitReason), nullable=False)
    tags = Column(Text, nullable=True)  # JSON string of metadata


class Order(BaseModel):
    """Represents an order (pending, filled, or cancelled)."""

    __tablename__ = "orders"

    broker_order_id = Column(String(100), unique=True, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)  # BUY or SELL
    order_type = Column(String(20), nullable=False)  # MARKET, LIMIT, STOP, etc.
    quantity = Column(Numeric(20, 8), nullable=False)
    filled_quantity = Column(Numeric(20, 8), nullable=False, default=0)
    limit_price = Column(Numeric(20, 8), nullable=True)
    stop_price = Column(Numeric(20, 8), nullable=True)
    avg_fill_price = Column(Numeric(20, 8), nullable=True)
    status = Column(SQLEnum(OrderStatus), nullable=False, default=OrderStatus.PENDING, index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    raw_response = Column(Text, nullable=True)  # JSON string of broker response


class Position(BaseModel):
    """Represents an open position."""

    __tablename__ = "positions"

    symbol = Column(String(20), nullable=False, unique=True, index=True)
    quantity = Column(Numeric(20, 8), nullable=False)
    avg_entry_price = Column(Numeric(20, 8), nullable=False)
    current_price = Column(Numeric(20, 8), nullable=True)
    stop_loss = Column(Numeric(20, 8), nullable=True)
    profit_target = Column(Numeric(20, 8), nullable=True)
    strategy_name = Column(String(100), nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    unrealized_pnl = Column(Numeric(20, 8), nullable=True)  # marked-to-market
    unrealized_pnl_pct = Column(Float, nullable=True)


class Signal(BaseModel):
    """Represents a strategy signal."""

    __tablename__ = "signals"

    symbol = Column(String(20), nullable=False, index=True)
    strategy_name = Column(String(100), nullable=False)
    direction = Column(String(10), nullable=False)  # LONG or SHORT
    entry_zone_low = Column(Numeric(20, 8), nullable=False)
    entry_zone_high = Column(Numeric(20, 8), nullable=False)
    stop_loss = Column(Numeric(20, 8), nullable=False)
    profit_target = Column(Numeric(20, 8), nullable=False)
    confidence = Column(Float, nullable=False)  # 0-1
    technical_explanation = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, approved, rejected, executed
    approved_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)


class ApprovalQueue(BaseModel):
    """Pending orders awaiting human approval before live execution."""

    __tablename__ = "approval_queue"

    symbol = Column(String(20), nullable=False, index=True)
    strategy_name = Column(String(100), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    order_type = Column(String(20), nullable=False)  # MARKET, LIMIT, etc.
    side = Column(String(10), nullable=False)  # BUY or SELL
    quantity = Column(Numeric(20, 8), nullable=False)
    limit_price = Column(Numeric(20, 8), nullable=True)
    stop_price = Column(Numeric(20, 8), nullable=True)
    reason = Column(Text, nullable=False)  # Human-readable explanation
    estimated_cost = Column(Numeric(20, 8), nullable=False)
    estimated_fee = Column(Numeric(20, 8), nullable=False)
    risk_metrics = Column(Text, nullable=False)  # JSON: stop_loss, risk, reward, R:R, portfolio_impact
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending, approved, rejected
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_reason = Column(Text, nullable=True)
    submitted_to_broker_at = Column(DateTime(timezone=True), nullable=True)
    broker_order_id = Column(String(100), nullable=True, unique=True)


class PortfolioSnapshot(BaseModel):
    """Historical snapshot of portfolio state."""

    __tablename__ = "portfolio_snapshots"

    cash = Column(Numeric(20, 8), nullable=False)
    equity = Column(Numeric(20, 8), nullable=False)
    total_positions_value = Column(Numeric(20, 8), nullable=False)
    open_positions_count = Column(Integer, nullable=False)
    closed_trades_count = Column(Integer, nullable=False)
    daily_pnl = Column(Numeric(20, 8), nullable=False)
    total_pnl = Column(Numeric(20, 8), nullable=False)
    total_return_pct = Column(Float, nullable=False)
    drawdown_pct = Column(Float, nullable=False)
    max_exposure_pct = Column(Float, nullable=False)
    extra_metadata = Column(Text, nullable=True)  # JSON of additional metrics


class RiskLimit(BaseModel):
    """Risk management configuration."""

    __tablename__ = "risk_limits"

    daily_loss_limit = Column(Numeric(20, 8), nullable=False)  # max loss in $ per day
    max_position_size_pct = Column(Float, nullable=False)  # max % of equity per position
    max_portfolio_exposure_pct = Column(Float, nullable=False)  # max % of equity in all positions
    max_concurrent_positions = Column(Integer, nullable=False)
    risk_per_trade_pct = Column(Float, nullable=False)  # % of equity risked per trade
    max_consecutive_losses = Column(Integer, nullable=False)
    trade_cooldown_seconds = Column(Integer, nullable=False)  # cooldown between trades
    is_active = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(100), nullable=True)


class AuditLog(BaseModel):
    """Audit trail for all significant actions."""

    __tablename__ = "audit_logs"

    action = Column(String(100), nullable=False, index=True)  # e.g., "order_approved", "trade_closed"
    entity_type = Column(String(50), nullable=False)  # e.g., "Order", "Trade", "Position"
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)  # JSON details
    severity = Column(String(20), nullable=False)  # INFO, WARNING, ERROR, CRITICAL
    user = Column(String(100), nullable=True)


class BacktestResult(BaseModel):
    """Stores results of backtesting runs."""

    __tablename__ = "backtest_results"

    strategy_name = Column(String(100), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    initial_capital = Column(Numeric(20, 8), nullable=False)
    final_equity = Column(Numeric(20, 8), nullable=False)
    total_return_pct = Column(Float, nullable=False)
    sharpe_ratio = Column(Float, nullable=True)
    sortino_ratio = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=False)
    win_rate_pct = Column(Float, nullable=False)
    profit_factor = Column(Float, nullable=False)
    total_trades = Column(Integer, nullable=False)
    winning_trades = Column(Integer, nullable=False)
    losing_trades = Column(Integer, nullable=False)
    cagr_pct = Column(Float, nullable=True)
    extra_data = Column(Text, nullable=True)  # Full results as JSON


class HistoricalPrice(BaseModel):
    """Historical OHLCV data for backtesting."""

    __tablename__ = "historical_prices"

    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, unique=True)
    open = Column(Numeric(20, 8), nullable=False)
    high = Column(Numeric(20, 8), nullable=False)
    low = Column(Numeric(20, 8), nullable=False)
    close = Column(Numeric(20, 8), nullable=False)
    volume = Column(Numeric(20, 8), nullable=False)
    granularity = Column(String(20), nullable=False, default="ONE_HOUR")  # ONE_MINUTE, FIVE_MINUTE, ONE_HOUR, ONE_DAY
