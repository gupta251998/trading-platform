from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os
import shared_state

app = FastAPI(title="Trading Platform Dashboard", version="1.0.0")

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def _get_current_prices(portfolio, broker):
    """Fetch latest price for each open position's symbol (best-effort)."""
    prices = {}
    if not portfolio or not broker:
        return prices
    for symbol in portfolio.positions.keys():
        try:
            candles = broker.get_candles(symbol, granularity="ONE_HOUR", limit=5)
            if candles:
                prices[symbol] = candles[-1]["close"]
        except Exception:
            continue
    return prices


@app.get("/")
async def root():
    return {"message": "Trading Platform Dashboard", "status": "running"}


@app.get("/api/summary")
async def get_summary():
    portfolio = shared_state.get_portfolio()
    broker = shared_state.get_broker()

    if portfolio is None:
        return {
            "status": "not_yet_initialized",
            "equity": None,
            "cash": None,
            "open_positions": 0,
            "closed_trades": 0
        }

    current_prices = _get_current_prices(portfolio, broker)
    summary = portfolio.summary(current_prices)
    summary["status"] = "live"
    summary["open_position_symbols"] = list(portfolio.positions.keys())
    return summary


@app.get("/api/stats")
async def get_stats():
    portfolio = shared_state.get_portfolio()
    if portfolio is None:
        return {"status": "not_yet_initialized"}

    stats = portfolio.win_rate_stats()
    stats["daily_pnl"] = round(portfolio.daily_pnl(), 4) if hasattr(portfolio, "daily_pnl") else None
    stats["status"] = "live"
    return stats


@app.get("/api/positions")
async def get_positions():
    portfolio = shared_state.get_portfolio()
    if portfolio is None:
        return {"status": "not_yet_initialized", "positions": []}

    broker = shared_state.get_broker()
    current_prices = _get_current_prices(portfolio, broker)

    positions = []
    for symbol, pos in portfolio.positions.items():
        current_price = current_prices.get(symbol, pos.avg_entry_price)
        unrealized_pnl = (current_price - pos.avg_entry_price) * pos.quantity
        positions.append({
            "symbol": symbol,
            "quantity": pos.quantity,
            "entry_price": pos.avg_entry_price,
            "current_price": current_price,
            "stop_loss": pos.stop_loss,
            "profit_target": pos.profit_target,
            "unrealized_pnl": round(unrealized_pnl, 4),
            "strategy": pos.strategy_name,
        })
    return {"status": "live", "positions": positions}


@app.get("/api/broker-health")
async def broker_health():
    broker = shared_state.get_broker()
    if broker is None:
        return {"status": "not_yet_initialized"}
    try:
        balance = broker.get_usdt_balance()
        return {"status": "connected", "usdt_balance": balance}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
