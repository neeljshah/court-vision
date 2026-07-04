"""scripts.platformkit.venue_history -- venue historical-odds backfill lanes.

Per-venue candle/tick backfills (Kalshi candlesticks, Polymarket CLOB history, ...)
into physically separate VALIDATION corpora under data/venue_history/<venue>/<sport>/.
These are never pooled with the forward pre-registered gates (ingame_tail_gate) --
see each module's PROVENANCE note.
"""
