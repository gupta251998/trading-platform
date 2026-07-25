"""All models and TradeCandidate definition"""
from sqlalchemy import Column, String, Float, DateTime, Boolean, Integer
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from enum import Enum

Base = declarative_base()

class Direction(Enum):
    LONG = "long"
    SHORT = "short"

class TradeCandidate:
    """Trade signal candidate"""
    def __init__(self, symbol, direction, entry_price, stop_loss, profit_target, confidence, strategy_name, risk_reward_ratio):
        self.symbol = symbol
        self.direction = direction
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.profit_target = profit_target
        self.confidence = confidence
        self.strategy_name = strategy_name
        self.risk_reward_ratio = risk_reward_ratio

class Trade(Base):
    """Trade record"""
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50))
    direction = Column(String(10))
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float)
    entry_time = Column(DateTime, default=datetime.utcnow)
    exit_time = Column(DateTime, nullable=True)
    pnl = Column(Float, default=0)
    pnl_pct = Column(Float, default=0)
    strategy = Column(String(50))
    exit_reason = Column(String(100), nullable=True)
    status = Column(String(20), default='open')

class RiskLimit(Base):
    """Risk management limits"""
    __tablename__ = 'risk_limits'
    
    id = Column(Integer, primary_key=True)
    daily_loss_limit = Column(Float, default=5.0)
    max_position_size_pct = Column(Float, default=0.05)
    max_concurrent_positions = Column(Integer, default=1)
    max_portfolio_exposure_pct = Column(Float, default=10.0)
    risk_per_trade_pct = Column(Float, default=0.1)
    max_consecutive_losses = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow)

class Portfolio(Base):
    """Portfolio state"""
    __tablename__ = 'portfolio'
    
    id = Column(Integer, primary_key=True)
    total_equity = Column(Float, default=10000)
    cash = Column(Float, default=10000)
    crypto_value = Column(Float, default=0)
    daily_pnl = Column(Float, default=0)
    cumulative_pnl = Column(Float, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Signal(Base):
    """Trading signal log"""
    __tablename__ = 'signals'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50))
    strategy = Column(String(50))
    direction = Column(String(10))
    confidence = Column(Float)
    entry_price = Column(Float)
    stop_loss = Column(Float)
    profit_target = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    executed = Column(Boolean, default=False)
