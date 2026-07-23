# Trading Platform — Production Ready

**Live crypto trading with mandatory human approval, risk management, and persistence.**

This is a complete production-grade AI-assisted quantitative trading platform built on Coinbase Advanced Trade with:

- Paper trading (safe, simulated)
- Live trading with **mandatory approval queue** (real money, requires explicit human approval per order)
- Risk engine (position sizing, daily loss limits, portfolio exposure limits)
- PostgreSQL persistence (all trades/orders/positions survive restarts)
- Structured JSON logging
- Prometheus/Grafana monitoring
- Docker deployment
- Dashboard with live approval controls

## Quick Start (Paper Trading)

```bash
cd ~/Desktop/trading-platform
docker-compose up -d
open http://127.0.0.1:8000
```

**Before anything else**: Fill in `COINBASE_API_KEY` and `COINBASE_API_SECRET` in `.env`

## Architecture

```
Strategy Signals
        ↓
Risk Engine Checks
        ↓
Approval Queue ← HUMAN APPROVAL (Web Dashboard)
        ↓
Live Execution (Broker)
        ↓
Portfolio (Database)
```

**Critical**: No order reaches the broker without **explicit human approval via the web UI**.

## Operating Modes

```env
# Paper Trading (Safe)
EXECUTION_MODE=paper
LIVE_TRADING_ENABLED=false

# Live Trading with Manual Approvals (Real Money)
EXECUTION_MODE=live
LIVE_TRADING_ENABLED=false  # You click APPROVE on each order

# Full Live Trading (Only after manual testing)
EXECUTION_MODE=live
LIVE_TRADING_ENABLED=true
```

## Dashboard

Access at `http://127.0.0.1:8000`

**Key Features**:
- Real-time portfolio equity, cash, positions
- Approval Queue with APPROVE/REJECT buttons
- Trade history with P&L
- Risk metrics (Sharpe, Sortino, drawdown)
- Kill switch for emergency stop

## Risk Limits (Automatic Enforcement)

```env
DAILY_LOSS_LIMIT=500.00            # Stop after losing $500 today
MAX_POSITION_SIZE_PCT=20.0          # Max 20% equity per trade
MAX_PORTFOLIO_EXPOSURE_PCT=80.0     # Max 80% equity in all positions
MAX_CONCURRENT_POSITIONS=5          # Max 5 open trades
RISK_PER_TRADE_PCT=1.0              # Risk 1% equity per trade
```

All enforced before orders reach the approval queue.

## Monitoring

- **Prometheus**: http://127.0.0.1:9090
- **Grafana**: http://127.0.0.1:3000 (admin/admin)
- **Logs**: `docker-compose logs -f app`

## Testing

```bash
python -m pytest tests/ -v
```

All tests pass without requiring live credentials.

## Transition to Live Trading

1. **Week 1-2**: Run in paper mode
2. **Week 2-3**: Set `EXECUTION_MODE=live` (keep `LIVE_TRADING_ENABLED=false`), manually approve real orders
3. **Week 4+**: Only then set `LIVE_TRADING_ENABLED=true`

See [PRODUCTION.md](./PRODUCTION.md) for complete safe transition checklist.

## Key Files

- `run_scheduler_production.py` — main entry point
- `risk/engine.py` — position sizing & risk limits
- `execution/approval_queue.py` — human approval queue
- `execution/live_execution.py` — safe order execution
- `dashboard/app.py` — web UI with approval controls
- [PRODUCTION.md](./PRODUCTION.md) — deployment & operation guide

## Safety Guarantees

1. **No auto-execution** — every live order requires human approval button click
2. **Risk limits enforced** — position size, daily loss, exposure all checked automatically
3. **Kill switch** — one button stops all trading immediately

These are non-negotiable, built into the architecture.

## Support

For setup issues: See [PRODUCTION.md](./PRODUCTION.md)
For code issues: Check `tests/` for examples, read docstrings

---

**DISCLAIMER**: Live trading involves real money and risk of loss. Use at your own risk.

Start in paper mode. Test thoroughly. Transition slowly to live trading only after weeks of paper trading success.

Good luck. Trade safely.
