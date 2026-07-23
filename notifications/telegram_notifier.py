"""
Telegram notifier.

Setup:
1. Message @BotFather on Telegram, /newbot, get a bot token.
2. Message your new bot once (or add it to a group), then hit
   https://api.telegram.org/bot<TOKEN>/getUpdates to find your chat_id.
3. Put both in .env as TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.

Uses the raw Bot API over HTTPS (no telegram SDK dependency) — one
`requests.post` per notification, sent in a background thread so a slow
or failing Telegram call never blocks the trading loop.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import requests

from notifications.base import Notifier
from paper_trading.portfolio import ClosedTrade
from strategy.base import TradeCandidate

logger = logging.getLogger("notifications.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"
REQUEST_TIMEOUT_SECONDS = 10


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"

    def _send(self, text: str) -> None:
        """Fire-and-forget in a background thread — never block the caller."""
        thread = threading.Thread(target=self._send_sync, args=(text,), daemon=True)
        thread.start()

    def _send_sync(self, text: str) -> None:
        try:
            resp = requests.post(
                self._url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if resp.status_code != 200:
                logger.warning("Telegram send failed (%d): %s", resp.status_code, resp.text)
        except Exception as exc:
            # Never let a notification failure propagate — it must not affect trading.
            logger.warning("Telegram send raised: %s", exc)

    def notify_candidate_opened(
        self, candidate: TradeCandidate, quantity: float, fill_price: float
    ) -> None:
        text = (
            f"*Paper position opened*\n"
            f"`{candidate.symbol}` {candidate.direction.value.upper()} "
            f"via `{candidate.strategy_name}`\n"
            f"Qty: `{quantity:.6f}` @ `{fill_price:.2f}`\n"
            f"Stop: `{candidate.stop_loss:.2f}` | Target: `{candidate.profit_target:.2f}` "
            f"| R:R `{candidate.risk_reward_ratio}`\n"
            f"Confidence: `{candidate.confidence:.2f}`\n"
            f"{candidate.technical_explanation}"
        )
        self._send(text)

    def notify_position_closed(self, trade: ClosedTrade) -> None:
        emoji = "🟢" if trade.pnl >= 0 else "🔴"
        text = (
            f"{emoji} *Paper position closed*\n"
            f"`{trade.symbol}` via `{trade.strategy_name}`, reason: `{trade.exit_reason}`\n"
            f"Entry: `{trade.entry_price:.2f}` -> Exit: `{trade.exit_price:.2f}`\n"
            f"PnL: `{trade.pnl:.2f}` (`{trade.pnl_pct:.2f}%`)"
        )
        self._send(text)

    def notify_symbol_failing(self, symbol: str, consecutive_failures: int, error: Optional[str]) -> None:
        text = (
            f"⚠️ *{symbol}* has failed `{consecutive_failures}` consecutive cycles.\n"
            f"Last error: `{error}`\n"
            f"Check credentials, connectivity, or whether the symbol is still valid."
        )
        self._send(text)
