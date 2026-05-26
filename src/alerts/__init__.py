"""Alert pathways — Discord webhook, vault ledger, critical-stack fallback.

Tier-1 follow-up to R17 daemon suite (lineup, urgent_bets, risk, line-moves,
middles).  Each daemon previously wrote its alerts only to a vault Markdown
file or JSON cache — invisible until you check the file.  R18_K3 added a
Discord webhook helper, but local installs without ``DISCORD_WEBHOOK_URL``
saw alerts silently dropped (R19_L3 watchdog observed this directly).

R21_N3 layers three durable channels behind a single ``alert()`` call:

* Vault append → ``vault/Improvements/alerts.md`` (always, append-only).
* Critical stack → ``data/cache/alerts/critical_<date>.json`` when
  ``level == "critical"`` OR no Discord URL is configured.
* Discord push → fired only when ``DISCORD_WEBHOOK_URL`` is set; same
  rate-limit + spill-to-JSONL semantics as the original R18_K3 helper.

Legacy callers continue to import :func:`post_alert` unchanged.
"""

from .discord_webhook import alert, post_alert

__all__ = ["alert", "post_alert"]
