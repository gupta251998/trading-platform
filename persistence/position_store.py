"""Postgres-backed persistence for open positions and closed trades.
Survives both container restarts AND fresh redeploys, since Postgres is a
separate Railway service from the app container's own (ephemeral) disk."""
import os


def _get_connection():
    import psycopg2
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    return psycopg2.connect(database_url)


def ensure_tables():
    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_open_positions (
                    symbol TEXT PRIMARY KEY,
                    quantity DOUBLE PRECISION NOT NULL,
                    entry_price DOUBLE PRECISION NOT NULL,
                    stop_loss DOUBLE PRECISION,
                    profit_target DOUBLE PRECISION,
                    strategy_name TEXT,
                    opened_at TIMESTAMP NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_closed_trades (
                    id SERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    strategy_name TEXT,
                    quantity DOUBLE PRECISION,
                    entry_price DOUBLE PRECISION,
                    exit_price DOUBLE PRECISION,
                    opened_at TIMESTAMP,
                    closed_at TIMESTAMP,
                    fee_paid DOUBLE PRECISION,
                    pnl DOUBLE PRECISION,
                    exit_reason TEXT
                )
            """)
        conn.commit()
    finally:
        conn.close()


def save_position(symbol, quantity, entry_price, stop_loss, profit_target, strategy_name, opened_at):
    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bot_open_positions
                (symbol, quantity, entry_price, stop_loss, profit_target, strategy_name, opened_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    entry_price = EXCLUDED.entry_price,
                    stop_loss = EXCLUDED.stop_loss,
                    profit_target = EXCLUDED.profit_target,
                    strategy_name = EXCLUDED.strategy_name,
                    opened_at = EXCLUDED.opened_at
            """, (symbol, quantity, entry_price, stop_loss, profit_target, strategy_name, opened_at))
        conn.commit()
    finally:
        conn.close()


def delete_position(symbol):
    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bot_open_positions WHERE symbol = %s", (symbol,))
        conn.commit()
    finally:
        conn.close()


def load_all_positions():
    conn = _get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol, quantity, entry_price, stop_loss, profit_target, strategy_name, opened_at
                FROM bot_open_positions
            """)
            rows = cur.fetchall()
        return [
            {
                "symbol": r[0], "quantity": r[1], "entry_price": r[2],
                "stop_loss": r[3], "profit_target": r[4],
                "strategy_name": r[5], "opened_at": r[6],
            }
            for r in rows
        ]
    finally:
        conn.close()


def save_closed_trade(symbol, strategy_name, quantity, entry_price, exit_price,
                       opened_at, closed_at, fee_paid, pnl, exit_reason):
    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bot_closed_trades
                (symbol, strategy_name, quantity, entry_price, exit_price, opened_at, closed_at, fee_paid, pnl, exit_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (symbol, strategy_name, quantity, entry_price, exit_price, opened_at, closed_at, fee_paid, pnl, exit_reason))
        conn.commit()
    finally:
        conn.close()


def load_all_closed_trades():
    conn = _get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol, strategy_name, quantity, entry_price, exit_price,
                       opened_at, closed_at, fee_paid, pnl, exit_reason
                FROM bot_closed_trades ORDER BY closed_at
            """)
            return cur.fetchall()
    finally:
        conn.close()
