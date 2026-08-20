"""Interactive Telegram bot commands - polls for messages and responds
with real, live data from shared_state. Runs in its own background thread."""
import os
import time
import json
import requests
from datetime import datetime, timezone

import shared_state


def _get_bot_token():
    return os.getenv("TELEGRAM_BOT_TOKEN")


def _get_chat_id():
    return os.getenv("TELEGRAM_CHAT_ID")


def _send(text):
    token = _get_bot_token()
    chat_id = _get_chat_id()
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception:
        pass


def _log(message, level="INFO"):
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": f"[telegram_commands] {message}"
    }), flush=True)


MENU_TEXT = (
    "<b>Trading Bot Menu</b>\n\n"
    "/status - Account summary (cash, equity, open positions)\n"
    "/positions - Currently open trades\n"
    "/stats - Win rate and closed trade performance\n"
    "/closed - List of recently closed trades\n"
    "/menu - Show this menu again"
)


def _handle_status():
    portfolio = shared_state.get_portfolio()
    broker = shared_state.get_broker()
    if portfolio is None:
        return "Bot is starting up, no data yet. Try again in a moment."

    current_prices = {}
    for symbol in portfolio.positions.keys():
        try:
            candles = broker.get_candles(symbol, granularity="ONE_HOUR", limit=5)
            if candles:
                current_prices[symbol] = candles[-1]["close"]
        except Exception:
            continue

    summary = portfolio.summary(current_prices)
    return (
        f"<b>Account Status</b>\n\n"
        f"Cash: ${summary['cash']:.2f}\n"
        f"Equity: ${summary['equity']:.2f}\n"
        f"Return: {summary['total_return_pct']}%\n"
        f"Open positions: {summary['open_positions']}\n"
        f"Closed trades: {summary['closed_trades']}"
    )


def _handle_positions():
    portfolio = shared_state.get_portfolio()
    broker = shared_state.get_broker()
    if portfolio is None or not portfolio.positions:
        return "No open positions right now."

    lines = ["<b>Open Positions</b>\n"]
    for symbol, pos in portfolio.positions.items():
        current_price = pos.avg_entry_price
        try:
            candles = broker.get_candles(symbol, granularity="ONE_HOUR", limit=5)
            if candles:
                current_price = candles[-1]["close"]
        except Exception:
            pass
        unrealized = (current_price - pos.avg_entry_price) * pos.quantity
        lines.append(
            f"\n<b>{symbol}</b> ({pos.strategy_name})\n"
            f"Qty: {pos.quantity:.6f}\n"
            f"Entry: ${pos.avg_entry_price:.6f}\n"
            f"Current: ${current_price:.6f}\n"
            f"P&L: ${unrealized:.4f}\n"
            f"Stop: ${pos.stop_loss:.6f} | Target: ${pos.profit_target:.6f}"
        )
    return "\n".join(lines)


def _handle_stats():
    portfolio = shared_state.get_portfolio()
    if portfolio is None:
        return "Bot is starting up, no data yet."

    stats = portfolio.win_rate_stats()
    if stats["total_trades"] == 0:
        return "No closed trades yet. Win rate will show once trades complete."

    return (
        f"<b>Performance Stats</b>\n\n"
        f"Total closed trades: {stats['total_trades']}\n"
        f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
        f"Win rate: {stats['win_rate_pct']}%\n"
        f"Avg win: ${stats['avg_win']}\n"
        f"Avg loss: ${stats['avg_loss']}\n"
        f"Total realized P&L: ${stats['total_realized_pnl']}"
    )


def _handle_closed():
    portfolio = shared_state.get_portfolio()
    if portfolio is None or not portfolio.closed_trades:
        return "No closed trades yet."

    lines = ["<b>Recent Closed Trades</b>\n"]
    for t in portfolio.closed_trades[-10:]:
        lines.append(
            f"\n<b>{t.symbol}</b> ({t.exit_reason})\n"
            f"Entry: ${t.entry_price:.6f} -> Exit: ${t.exit_price:.6f}\n"
            f"P&L: ${t.pnl:.4f}"
        )
    return "\n".join(lines)


def _process_command(text):
    text = text.strip().lower()
    if text in ("/start", "/menu"):
        return MENU_TEXT
    elif text == "/status":
        return _handle_status()
    elif text == "/positions":
        return _handle_positions()
    elif text == "/stats":
        return _handle_stats()
    elif text == "/closed":
        return _handle_closed()
    else:
        return "Unknown command. Send /menu to see available options."


def run_command_listener():
    """Long-polls Telegram for new messages and responds. Runs forever in a thread."""
    token = _get_bot_token()
    if not token:
        _log("No TELEGRAM_BOT_TOKEN set, command listener not starting", "ERROR")
        return

    _log("Starting Telegram command listener...")
    last_update_id = None

    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"timeout": 30}
            if last_update_id is not None:
                params["offset"] = last_update_id + 1

            resp = requests.get(url, params=params, timeout=35)
            data = resp.json()

            if not data.get("ok"):
                time.sleep(5)
                continue

            for update in data.get("result", []):
                last_update_id = update["update_id"]
                message = update.get("message", {})
                text = message.get("text", "")
                chat_id = str(message.get("chat", {}).get("id", ""))

                configured_chat_id = _get_chat_id()
                if configured_chat_id and chat_id != str(configured_chat_id):
                    continue

                if text.startswith("/"):
                    reply = _process_command(text)
                    _send(reply)

        except Exception as e:
            _log(f"Command listener error: {e}", "ERROR")
            time.sleep(5)
