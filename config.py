"""
Configuration loader — reads and validates environment variables.

Centralizes all config in one place. Use this instead of os.getenv()
throughout the codebase for consistency and validation.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class BrokerConfig:
    """Broker configuration."""
    api_key: str
    api_secret: str
    paper_mode: bool
    

@dataclass
class ExecutionConfig:
    """Execution mode configuration."""
    mode: str  # "paper" or "live"
    live_enabled: bool
    

@dataclass
class DatabaseConfig:
    """Database configuration."""
    url: str
    echo: bool
    

@dataclass
class SchedulerConfig:
    """Scheduler configuration."""
    symbols: list
    granularity: str
    candle_limit: int
    poll_interval_seconds: int
    starting_cash: float
    

@dataclass
class RiskConfig:
    """Risk management configuration."""
    daily_loss_limit: float
    max_position_size_pct: float
    max_portfolio_exposure_pct: float
    max_concurrent_positions: int
    risk_per_trade_pct: float
    max_consecutive_losses: int
    trade_cooldown_seconds: int
    

@dataclass
class NotificationConfig:
    """Notification configuration."""
    telegram_token: Optional[str]
    telegram_chat_id: Optional[str]
    discord_webhook: Optional[str]
    email_smtp_server: Optional[str]
    email_smtp_port: Optional[int]
    email_from: Optional[str]
    email_to: Optional[str]
    

@dataclass
class DashboardConfig:
    """Dashboard configuration."""
    enabled: bool
    host: str
    port: int
    

@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str
    format: str
    

@dataclass
class Config:
    """Complete configuration."""
    broker: BrokerConfig
    execution: ExecutionConfig
    database: DatabaseConfig
    scheduler: SchedulerConfig
    risk: RiskConfig
    notifications: NotificationConfig
    dashboard: DashboardConfig
    logging: LoggingConfig


def load_config() -> Config:
    """Load and validate configuration from environment."""
    
    # Broker
    api_key = os.getenv("COINBASE_API_KEY", "")
    api_secret = os.getenv("COINBASE_API_SECRET", "")
    live_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
    paper_mode = os.getenv("EXECUTION_MODE", "paper").lower() != "live" or not live_enabled
    
    broker_config = BrokerConfig(
        api_key=api_key,
        api_secret=api_secret,
        paper_mode=paper_mode,
    )
    
    # Execution
    execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()
    if execution_mode not in ("paper", "live"):
        raise ValueError(f"Invalid EXECUTION_MODE: {execution_mode}")
    
    execution_config = ExecutionConfig(
        mode=execution_mode,
        live_enabled=live_enabled,
    )
    
    # Database
    database_config = DatabaseConfig(
        url=os.getenv(
            "DATABASE_URL",
            "postgresql://trading_user:trading_password@localhost:5432/trading_db"
        ),
        echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
    )
    
    # Scheduler
    symbols_str = os.getenv("SYMBOLS", "BTC-USD,ETH-USD")
    symbols = [s.strip().upper() for s in symbols_str.split(",")]
    
    scheduler_config = SchedulerConfig(
        symbols=symbols,
        granularity=os.getenv("GRANULARITY", "ONE_HOUR"),
        candle_limit=int(os.getenv("CANDLE_LIMIT", "200")),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "300")),
        starting_cash=float(os.getenv("STARTING_CASH", "10000")),
    )
    
    # Risk
    risk_config = RiskConfig(
        daily_loss_limit=float(os.getenv("DAILY_LOSS_LIMIT", "500.00")),
        max_position_size_pct=float(os.getenv("MAX_POSITION_SIZE_PCT", "20.0")),
        max_portfolio_exposure_pct=float(os.getenv("MAX_PORTFOLIO_EXPOSURE_PCT", "80.0")),
        max_concurrent_positions=int(os.getenv("MAX_CONCURRENT_POSITIONS", "5")),
        risk_per_trade_pct=float(os.getenv("RISK_PER_TRADE_PCT", "1.0")),
        max_consecutive_losses=int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3")),
        trade_cooldown_seconds=int(os.getenv("TRADE_COOLDOWN_SECONDS", "60")),
    )
    
    # Notifications
    notifications_config = NotificationConfig(
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None,
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip() or None,
        discord_webhook=os.getenv("DISCORD_WEBHOOK_URL", "").strip() or None,
        email_smtp_server=os.getenv("EMAIL_SMTP_SERVER", "").strip() or None,
        email_smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "587")) if os.getenv("EMAIL_SMTP_PORT") else None,
        email_from=os.getenv("EMAIL_ADDRESS", "").strip() or None,
        email_to=os.getenv("EMAIL_TO_ADDRESS", "").strip() or None,
    )
    
    # Dashboard
    dashboard_config = DashboardConfig(
        enabled=os.getenv("DASHBOARD_ENABLED", "true").lower() == "true",
        host=os.getenv("DASHBOARD_HOST", "127.0.0.1"),
        port=int(os.getenv("DASHBOARD_PORT", "8000")),
    )
    
    # Logging
    logging_config = LoggingConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format=os.getenv("LOG_FORMAT", "json"),
    )
    
    return Config(
        broker=broker_config,
        execution=execution_config,
        database=database_config,
        scheduler=scheduler_config,
        risk=risk_config,
        notifications=notifications_config,
        dashboard=dashboard_config,
        logging=logging_config,
    )


def validate_production_config(config: Config) -> list:
    """
    Validate configuration for production.
    
    Returns list of warnings/errors (empty if valid).
    """
    errors = []
    
    # Check Coinbase credentials
    if config.execution.mode == "live" and config.execution.live_enabled:
        if not config.broker.api_key or not config.broker.api_secret:
            errors.append("LIVE trading requires COINBASE_API_KEY and COINBASE_API_SECRET")
    
    # Check risk limits are reasonable
    if config.risk.daily_loss_limit <= 0:
        errors.append("DAILY_LOSS_LIMIT must be > 0")
    if config.risk.max_position_size_pct <= 0 or config.risk.max_position_size_pct > 100:
        errors.append("MAX_POSITION_SIZE_PCT must be 0-100")
    if config.risk.max_portfolio_exposure_pct <= 0 or config.risk.max_portfolio_exposure_pct > 100:
        errors.append("MAX_PORTFOLIO_EXPOSURE_PCT must be 0-100")
    if config.risk.risk_per_trade_pct <= 0 or config.risk.risk_per_trade_pct > 10:
        errors.append("RISK_PER_TRADE_PCT should be 0.1-2%")
    
    # Check scheduler
    if not config.scheduler.symbols:
        errors.append("SYMBOLS must have at least one symbol")
    if config.scheduler.starting_cash <= 0:
        errors.append("STARTING_CASH must be > 0")
    if config.scheduler.poll_interval_seconds < 60:
        errors.append("POLL_INTERVAL_SECONDS should be >= 60 (1 minute)")
    
    return errors
