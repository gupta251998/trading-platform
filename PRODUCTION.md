**# Production Deployment Guide

## Overview

This guide covers deploying the trading platform to production with live cryptocurrency trading using Coinbase Advanced Trade.

**CRITICAL SAFETY WARNING**: Live trading involves real money. Mistakes can result in significant losses. This platform is designed with multiple safety mechanisms (approval queues, risk limits, kill switches), but you must understand what you're doing before enabling live trading.

## Prerequisites

- **macOS, Linux, or Windows (WSL2)**
- **Docker & Docker Compose** (for containerized deployment)
  - Or: PostgreSQL 15+, Python 3.12+, pip
- **Coinbase Advanced Trade account** with trading API credentials
- **Telegram account** (optional, for alerts)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Coinbase Advanced Trade API                                 │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ Broker Interface (market data, quotes)                       │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ Strategy Engine (SMA Crossover → signals)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ Risk Engine (position sizing, daily loss limits)             │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ Approval Queue (orders await human approval)                │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴────────────┐
         │                        │
    ┌────▼────────────┐  ┌───────▼──────────┐
    │ Approve         │  │ Reject           │
    │ (Web UI button) │  │ (Web UI button)  │
    └────┬────────────┘  └──────────────────┘
         │
┌────────▼────────────────────────────────────────────────────┐
│ Live Execution Layer (submits to broker only after approval) │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ Coinbase Advanced Trade API (place order)                    │
└─────────────────────────────────────────────────────────────┘
```

**Key Safety Feature**: No order reaches the broker without explicit human approval.

## Setup with Docker (Recommended)

### 1. Clone/Extract the Project

```bash
cd ~/Desktop/trading-platform
```

### 2. Create `.env` File

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```
# Required: Coinbase API credentials
COINBASE_API_KEY=organizations/your_key/apiKeys/your_id
COINBASE_API_SECRET="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"

# IMPORTANT: Start in paper mode
EXECUTION_MODE=paper

# Only set to "true" when ready for live trading
LIVE_TRADING_ENABLED=false

# Database (Docker will use these defaults)
DATABASE_URL=postgresql://trading_user:trading_password@postgres:5432/trading_db

# Risk limits (adjust to your comfort level)
DAILY_LOSS_LIMIT=500.00
MAX_POSITION_SIZE_PCT=20.0
MAX_PORTFOLIO_EXPOSURE_PCT=80.0
MAX_CONCURRENT_POSITIONS=5

# Optional: Telegram alerts
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. Start All Services

```bash
docker-compose up -d
```

This starts:
- Trading app (port 8000)
- PostgreSQL database
- Redis cache
- Prometheus (port 9090)
- Grafana (port 3000)

### 4. Initialize Database

```bash
docker exec trading_app python -m alembic upgrade head
```

### 5. Verify It's Running

```bash
# Check containers
docker-compose ps

# Check logs
docker-compose logs -f app

# Access dashboard
open http://127.0.0.1:8000
```

## Manual Setup (Without Docker)

### 1. Install PostgreSQL

**macOS:**
```bash
brew install postgresql
brew services start postgresql
createdb trading_db
createuser trading_user -P  # set password to: trading_password
```

**Linux:**
```bash
sudo apt-get install postgresql
sudo -u postgres createdb trading_db
sudo -u postgres createuser trading_user -P  # set password
```

### 2. Install Python Dependencies

```bash
cd ~/Desktop/trading-platform
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Initialize Database

```bash
python -m alembic upgrade head
```

### 4. Create and Configure `.env`

Same as Docker setup above.

### 5. Run the Platform

```bash
python run_scheduler_production.py
```

## Transitioning from Paper to Live

**IMPORTANT**: Follow this sequence carefully.

### Step 1: Verify in Paper Mode (1-2 weeks recommended)

```
EXECUTION_MODE=paper
LIVE_TRADING_ENABLED=false
```

Run the platform and watch for 1-2 weeks:
- Check strategy performance in paper trading
- Verify signals make sense
- Test the approval queue manually (approve/reject orders)
- Ensure risk limits are set correctly

### Step 2: Enable Live Mode (Approval Queue Active, No Auto-Execution)

```
EXECUTION_MODE=live
LIVE_TRADING_ENABLED=false  # Still not live execution
```

In this mode:
- Real signals are generated
- Orders go to approval queue
- You manually approve each order
- Orders execute on the real Coinbase account
- Real money is at risk

**This is the critical testing phase.** Manually approve a few small orders, watch them execute, close them. Understand the latency, fees, and real broker behavior.

### Step 3: Full Live Mode (After Thorough Testing)

```
EXECUTION_MODE=live
LIVE_TRADING_ENABLED=true
```

Only set `LIVE_TRADING_ENABLED=true` after:
- 2+ weeks of paper trading success
- Manual approval of 5-10 real orders
- Understanding of your risk limits
- Backup plan if something goes wrong

## Risk Limits (Critical)

These are in your `.env` file. Understand each one:

```
DAILY_LOSS_LIMIT=500.00          # Stop trading after losing $500 in one day
MAX_POSITION_SIZE_PCT=20.0        # No single trade is >20% of your equity
MAX_PORTFOLIO_EXPOSURE_PCT=80.0   # No more than 80% of equity in all positions combined
MAX_CONCURRENT_POSITIONS=5        # Max 5 open trades at once
RISK_PER_TRADE_PCT=1.0            # Risk 1% of equity per trade (recommended: 0.5-2%)
```

**You control these limits.** If you change them, you change your risk profile. Be conservative.

## Dashboard - Approval Queue

Access the dashboard at `http://127.0.0.1:8000`

**Approval Tab** shows pending orders:
- Strategy name and symbol
- Entry price, stop-loss, profit target
- Risk/reward ratio
- **APPROVE** button (turns on only after risk checks pass)
- **REJECT** button (cancel the order)

Every live trade requires you to click **APPROVE**.

## Emergency Stop (Kill Switch)

If something goes wrong:

1. **In the dashboard**: Click the red **KILL SWITCH** button (top-right corner)
   - Stops all new signals
   - Prevents execution of pending orders
   - No new trades are accepted

2. **Via API**: 
   ```bash
   curl -X POST http://127.0.0.1:8000/kill-switch
   ```

3. **Manually**: Stop the container/process
   ```bash
   docker-compose down
   # or Ctrl+C if running manually
   ```

After activating the kill switch, reconnect to the platform only after you've identified and fixed the problem.

## Monitoring

### Logs

```bash
# Docker
docker-compose logs -f app

# Or manually (when running directly)
tail -f logs/trading.log
```

Logs are JSON-formatted for easy parsing:
```json
{
  "timestamp": "2026-07-20T00:00:00Z",
  "level": "INFO",
  "logger": "scheduler.multi_symbol_scheduler",
  "message": "Cycle 1 starting (3 symbols)"
}
```

### Prometheus Metrics

Access at `http://127.0.0.1:9090`

Key metrics to watch:
- `orders_submitted_total` — total orders sent to broker
- `orders_filled_total` — total orders that filled
- `portfolio_equity` — current account value
- `open_positions_count` — number of open trades
- `daily_pnl` — today's profit/loss

### Grafana Dashboard

Access at `http://127.0.0.1:3000` (default: admin/admin)

Pre-configured dashboards show:
- Portfolio equity over time
- Daily P&L
- Open positions
- Drawdown chart

## Troubleshooting

### "LIVE trading mode requires LIVE_TRADING_ENABLED=true"

You set `EXECUTION_MODE=live` but didn't set `LIVE_TRADING_ENABLED=true`. This is intentional — live mode requires explicit confirmation.

### "Broker health check failed"

Your Coinbase API credentials are wrong or Coinbase is down.
- Verify your API key and secret in `.env`
- Confirm the key has "Trade" permissions (not just "View")
- Check Coinbase API status page

### "Daily loss limit exceeded"

You've lost >= your `DAILY_LOSS_LIMIT` today. No new trades will be approved until the next day resets.

**This is working as intended.** The risk engine is protecting you.

### "Max concurrent positions reached"

You have `MAX_CONCURRENT_POSITIONS=5` (for example) and already have 5 open trades. Close one to open another.

### Orders not executing after approval

Check:
1. Do you have enough buying power?
2. Is the order in the approval queue with status "approved"?
3. Check the logs for broker errors

## Backup & Recovery

### Database Backups

```bash
# Docker
docker exec trading_postgres pg_dump -U trading_user trading_db > backup.sql

# Restore
docker exec -i trading_postgres psql -U trading_user trading_db < backup.sql
```

### Trade History

All trades are persisted in PostgreSQL in the `trades` table. You can query them:

```bash
docker exec trading_postgres psql -U trading_user trading_db \
  -c "SELECT symbol, side, quantity, entry_price, exit_price, pnl, exit_reason FROM trades ORDER BY exit_time DESC LIMIT 10;"
```

## Performance Tuning

### Reduce API Calls

```env
POLL_INTERVAL_SECONDS=600  # Check every 10 minutes instead of 5
CANDLE_LIMIT=100           # Fewer historical bars
```

### Scale Database

PostgreSQL default pooling works for 1-2 users. For more symbols/strategies:

```env
DATABASE_URL=postgresql://trading_user:trading_password@postgres:5432/trading_db?pool_size=20&max_overflow=10
```

## Production Checklist

Before going live with real money:

- [ ] Successfully ran in paper mode for 2+ weeks
- [ ] Manually approved 5+ real orders (in EXECUTION_MODE=live with LIVE_TRADING_ENABLED=false)
- [ ] Verified risk limits are appropriate for your account size
- [ ] Set up Telegram alerts (so you know what's happening)
- [ ] Tested the kill switch
- [ ] Backed up your database
- [ ] Understand all logs and metrics
- [ ] Have an exit plan if something breaks
- [ ] Read this guide one more time

## Support & Further Reading

- **Strategy Development**: See `strategy/sma_crossover.py` for how to add new strategies
- **Risk Engine**: See `risk/engine.py` for position sizing logic
- **Approval Queue**: See `execution/approval_queue.py` for approval flow
- **Dashboard**: See `dashboard/app.py` for the web UI

Good luck. Trade safely.
