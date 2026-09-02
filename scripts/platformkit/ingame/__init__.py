"""scripts.platformkit.ingame -- sport-blind in-game STATE spine (Milestone-6).

The in-game spine ingests realized live game state (period/clock/score/possession)
into a sport-blind GameState and a tiny in-process bus, so the repricer + live loop
can read a single normalized snapshot regardless of sport.

HONEST + SAFE: these modules carry STATE only -- they never predict, never claim an
edge, and never fabricate a missing game (malformed/absent -> None). The validated
in-game number is produced downstream (eval-gated); this layer is plumbing.
"""
