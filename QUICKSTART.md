# Quick Start — Get Trading in 5 Minutes

This guide gets you from zero to running in paper mode (safe, no real money).

## Prerequisites

- **Docker & Docker Compose** installed
  - OR: Python 3.12+, PostgreSQL 15+, pip

## Step 1: Extract (30 seconds)

```bash
cd ~/Desktop
unzip trading-platform-production.zip
cd trading-platform
```

## Step 2: Configure (1 minute)

```bash
cp .env.example .env
```

Edit `.env`:
```bash
nano .env
```

**Only 2 fields are required for paper trading:**

```env
# Get these from https://portal.cdp.coinbase.com
COINBASE_API_KEY=organizations/your_key/apiKeys/your_id
COINBASE_API_SECRET="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"

# Paper mode (safe, simulated)
EXECUTION_MODE=paper
LIVE_TRADING_ENABLED=false
```

Everything else has defaults.

## Step 3: Start (30 seconds)

**With Docker (Recommended):**
```bash
docker-compose up -d
```

**Or without Docker:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
python run_scheduler_production.py
```

## Step 4: Open Dashboard (1 minute)

Open your browser:
```
http://127.0.0.1:8000
```

You'll see:
- Portfolio equity and cash
- Open positions (none yet)
- Closed trades (none yet)
- Approval queue (orders waiting for approval)

## Step 5: Watch It Trade (Real-time)

The scheduler starts immediately and runs every 5 minutes (configurable).

**What happens each cycle:**
1. Fetches latest price bars from Coinbase
2. Runs SMA crossover strategy
3. If a signal fires, it appears in the dashboard
4. You can manually approve it (if live mode) or it auto-trades (paper mode)
5. Positions and trades appear in the dashboard in real-time

Check the logs:
```bash
docker-compose logs -f app
```

You'll see something like:
```json
{"timestamp": "2026-07-20T00:00:00Z", "level": "INFO", "message": "Cycle 1: new candidates on BTC-USD"}
```

## Next Steps

### To Verify It's Working

1. **Open Dashboard** → http://127.0.0.1:8000
2. **Check Logs** → `docker-compose logs -f app`
3. **Monitor Performance** → Watch for Trades tab to populate

### To Transition to Live Trading

Read `PRODUCTION.md` for the safe transition checklist (2-4 weeks):
1. Paper trading: 2 weeks
2. Live with manual approvals: 1-2 weeks
3. Full live (only then): after proven success

### To Stop Everything

```bash
# Docker
docker-compose down

# Or manual
Ctrl+C  # stops the Python process
```

## Troubleshooting

### "Broker health check failed"

Your Coinbase API key is wrong or Coinbase is down.
- Verify API key in `.env`
- Check Coinbase API status

### "No quote data returned"

This is normal for testing. The SMA strategy takes time to generate signals (needs 30+ price bars).

### "Database connection refused"

If using Docker: `docker-compose ps` should show all services running
If manual: PostgreSQL isn't running → `brew services start postgresql`

### Dashboard won't load

Try `http://127.0.0.1:8000` explicitly (not `localhost`)

## Key Files to Know

```
QUICKSTART.md          ← You are here
README.md              ← Feature overview
PRODUCTION.md          ← Complete deployment guide
.env.example           ← All configuration options
run_scheduler_production.py  ← Main entry point
```

## What's Actually Running

- **Trading Engine** — Evaluates strategy every 5 minutes
- **Paper Portfolio** — Simulated account (no real money)
- **Dashboard** — Web UI showing positions, trades, metrics
- **PostgreSQL** — Stores all historical data
- **Redis** — Caching layer
- **Prometheus** — Metrics database (optional, for monitoring)
- **Grafana** — Visualization dashboard (optional)

All persisted to database, survives restarts.

## Configuration Quick Reference

```env
EXECUTION_MODE=paper              # paper or live
SYMBOLS=BTC-USD,ETH-USD,SOL-USD   # symbols to trade
POLL_INTERVAL_SECONDS=300         # run every 5 min
STARTING_CASH=10000               # paper account size
DAILY_LOSS_LIMIT=500              # stop after losing $500/day
MAX_POSITION_SIZE_PCT=20           # no trade > 20% equity
TELEGRAM_BOT_TOKEN=               # optional: alerts
DASHBOARD_PORT=8000               # web UI port
LOG_LEVEL=INFO                    # logging verbosity
```

See `.env.example` for all options.

## Common Next Steps

1. **Watch the strategy trade for a few days**
   - Check dashboard daily
   - Read logs for insights
   - Verify risk limits make sense

2. **Test the dashboard approval queue** (if interested in live trading)
   - Switch to `EXECUTION_MODE=live` (keep `LIVE_TRADING_ENABLED=false`)
   - Manually approve a few orders
   - Watch them execute

3. **Read PRODUCTION.md**
   - Safe transition to live trading
   - Detailed troubleshooting
   - Deployment options

## Support

- **Quick issues?** Check Troubleshooting section above
- **Setup problems?** See PRODUCTION.md
- **Code questions?** Check README.md or docstrings in code

---

**You're now running a production-grade trading platform in paper mode.**

Spend 2-3 weeks here. Get comfortable. Then read PRODUCTION.md for safe transition to live trading.

Good luck!
