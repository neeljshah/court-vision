"""src/notifications — outbound alert transports (cycle 88k+).

Currently provides :class:`WebhookNotifier` for Slack / Discord webhook
fan-out. Telegram alerts live in ``src/monitoring/telegram_alerter.py``
for historical reasons.
"""

from .webhook_alerts import WebhookNotifier

__all__ = ["WebhookNotifier"]
