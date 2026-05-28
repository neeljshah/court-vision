"""Live Engine v2 — event-driven sub-30-second in-play intelligence.

Runs in parallel to the legacy 5-min `scripts/live_inplay_daemon.py`.
Entry point: `scripts/live_orchestrator.py`.

Modules
-------
event_bus           — asyncio pub/sub
latency_optimizer   — LRU cache + event coalescing + is_game_live
alert_dedup         — cooldown + severity tiers + digest bundling
"""
