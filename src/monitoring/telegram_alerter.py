"""
telegram_alerter.py — Send plain-text alerts via a Telegram bot.

Required env vars (both must be set for alerts to fire):
    TELEGRAM_BOT_TOKEN  — bot token from @BotFather
    TELEGRAM_CHAT_ID    — chat / channel ID to send to

If either var is missing, send_alert() logs a warning and returns without error.
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org"


def _get_credentials() -> tuple[str, str] | tuple[None, None]:
    """Return (bot_token, chat_id) or (None, None) if either is absent."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return None, None
    return token, chat_id


def send_alert(text: str, *, timeout: int = 10) -> bool:
    """Send *text* via Telegram.

    Returns True on success, False on any failure (network, config, etc.).
    Never raises — caller can fire-and-forget safely.
    """
    token, chat_id = _get_credentials()
    if token is None:
        log.warning(
            "Telegram alert suppressed: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID "
            "not set. Set both env vars to enable alerts."
        )
        return False

    url = f"{_TELEGRAM_API}/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    ).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                log.debug("Telegram alert sent: %s", text[:80])
                return True
            log.warning("Telegram API returned status %s", resp.status)
            return False
    except urllib.error.URLError as exc:
        log.warning("Telegram alert failed (network): %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("Telegram alert failed (unexpected): %s", exc)
        return False
