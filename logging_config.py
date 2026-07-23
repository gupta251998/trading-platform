"""
Structured logging and monitoring setup.

Logs are JSON-formatted for easy parsing and aggregation.
Prometheus metrics are exposed for monitoring.
"""

import json
import logging
import logging.config
import os
from datetime import datetime, timezone

from prometheus_client import Counter, Histogram, Gauge


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_dict["exception"] = self.formatException(record.exc_info)
        
        # Add any extra fields from the record
        if hasattr(record, "extra_fields"):
            log_dict.update(record.extra_fields)
        
        return json.dumps(log_dict)


def setup_logging(log_level: str = "INFO", log_format: str = "json"):
    """Configure logging based on environment."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    if log_format == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)
    
    # Suppress verbose loggers
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    
    return root_logger


# ---- Prometheus Metrics ----

# Counters (monotonically increasing)
orders_submitted = Counter(
    "orders_submitted_total",
    "Total orders submitted to broker",
    ["symbol", "side"],
)

orders_filled = Counter(
    "orders_filled_total",
    "Total orders filled",
    ["symbol"],
)

trades_closed = Counter(
    "trades_closed_total",
    "Total trades closed",
    ["symbol", "exit_reason"],
)

approval_queue_approved = Counter(
    "approval_queue_approved_total",
    "Total orders approved",
)

approval_queue_rejected = Counter(
    "approval_queue_rejected_total",
    "Total orders rejected",
)

risk_check_failures = Counter(
    "risk_check_failures_total",
    "Total risk check failures",
    ["check_type"],
)

# Histograms (distribution of values)
order_latency_ms = Histogram(
    "order_latency_ms",
    "Order submission latency in milliseconds",
    buckets=[10, 50, 100, 500, 1000, 5000],
)

execution_time_ms = Histogram(
    "execution_time_ms",
    "Strategy execution time in milliseconds",
    buckets=[10, 50, 100, 500, 1000],
)

# Gauges (point-in-time values)
portfolio_equity = Gauge(
    "portfolio_equity",
    "Current portfolio equity",
)

portfolio_cash = Gauge(
    "portfolio_cash",
    "Current portfolio cash",
)

open_positions_count = Gauge(
    "open_positions_count",
    "Number of open positions",
)

approval_queue_pending = Gauge(
    "approval_queue_pending",
    "Orders pending approval",
)

daily_pnl = Gauge(
    "daily_pnl",
    "Daily P&L",
)


def record_order_submitted(symbol: str, side: str):
    """Record that an order was submitted."""
    orders_submitted.labels(symbol=symbol, side=side).inc()


def record_trade_closed(symbol: str, exit_reason: str):
    """Record that a trade was closed."""
    trades_closed.labels(symbol=symbol, exit_reason=exit_reason).inc()


def record_risk_check_failure(check_type: str):
    """Record a risk check failure."""
    risk_check_failures.labels(check_type=check_type).inc()
