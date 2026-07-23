from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os

app = FastAPI(title="Trading Platform Dashboard", version="1.0.0")

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return {"message": "Trading Platform Dashboard", "status": "running"}

@app.get("/api/summary")
async def get_summary():
    return {
        "equity": 10000.0,
        "cash": 10000.0,
        "open_positions": 0,
        "closed_trades": 0
    }


@app.get("/api/broker-health")
async def broker_health():
    return {"status": "connected", "latency_ms": 1.0}
