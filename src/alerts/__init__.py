"""Alert pathways — Discord webhook, fallback queue, severity routing.

Tier-1 follow-up to R17 daemon suite (lineup, urgent_bets, risk, line-moves,
middles).  Each daemon previously wrote its alerts only to a vault Markdown
file or JSON cache — invisible until you check the file.  This package adds
a single Discord webhook helper (`discord_webhook.post_alert`) that the
daemons call when they detect a fire-worthy event.

The helper:

* Formats the alert as a Discord embed (color = severity).
* Is a NO-OP when `DISCORD_WEBHOOK_URL` is unset — graceful degradation
  so CI / unit tests / fresh installs don't crash.
* Rate-limits to 5 messages / 5 seconds (Discord webhook bucket).
* Spills overflow to `data/cache/discord_fallback_queue.jsonl` so nothing
  is lost.
"""
