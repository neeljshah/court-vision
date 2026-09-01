# E2 NBA Sub-Shock Latency Race Results

Clock basis: `detect_ts` is accepted only when the event manifest labels it a PBP/stint ingest timestamp. `reprice_ts` is the feed's recorded `captured_at`; no game-clock-to-wall-clock reconstruction is used.

| game | player | detect_ts | reprice_ts | delta_s | verdict |
| --- | --- | --- | --- | ---: | --- |

Event manifest: C:\Users\neelj\nba-track-a6\data\cache\team_system\subshock_events.jsonl (MISSING).
Line-history directory: C:\Users\neelj\nba-track-a6\data\cache\line_history\nba (MISSING).

Events read: 0; scoreable: 0.
FAIL: INSUFFICIENT_SCOREABLE_EVENTS: share=N/A (gate: >=60% of >=30 scoreable events).
