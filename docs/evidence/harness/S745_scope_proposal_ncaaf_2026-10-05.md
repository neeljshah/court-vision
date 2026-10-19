# S745 scope proposal (PROPOSED ONLY, nothing built): college football (ncaaf) as the next served sport

Author: all-games coverage lead, 2026-10-05. PAPER ONLY; coverage wording only. Not a register row and
not adopted. The row S745 inventory counts: 334 listed game or match series, 13 captured; football 10 listed
/ 1 captured (nfl); hockey 11 listed / 0 captured.

## Why ncaaf before hockey

| Piece of the served path | ncaaf today | nhl today |
|---|---|---|
| State capture source | present: local_state_capture_sources.py:297 ncaaf_poll; state2 runs `--sports ...,ncaaf,...`; rows in data/cache/ingame_state_local_v2/state/ncaaf | absent (no nhl poller) |
| D1 schedule source | present: forward_schedule_sources.py:21 ROUTES ncaaf = football/college-football | absent (no ESPN route) |
| Kalshi books capture | absent: no ncaaf books folder; forward_schedule_writer.py:34 `"ncaaf": ()` (no landed series) | absent |
| Game-to-market link | team path exists, alias table empty (game_market_link.py:27 `"ncaaf": {}`) | absent |
| Desk allowlist | not admitted (paper_desk_actions.py D1 tuple: mlb, nfl, nba, tennis) | not admitted |

ncaaf needs two of five pieces (books series + aliases); nhl needs all five. A Saturday ncaaf slate is far
larger than the three focus games the anonymous REST budget holds (S742), so ncaaf adds choice inside the
budget, not more simultaneous games; the S742 floor of one slot per live sport keeps mlb/nfl/nba served.

## Proposed steps (each its own row, spec first, two verifier tiers)

1. Read-only: confirm the venue's college football game series ticker (believed KXNCAAFGAME, NOT VERIFIED)
   and its per-week open-event count with one unauthenticated series GET and one events GET.
2. Books capture: add the series to kalshi_series_scope.SERIES_BY_SPORT and the capture runner sport list;
   S561-style measured offset (expected expiration minus true start) for ncaaf from the first captured
   week. Adoption = one books restart inside 06:00Z-16:00Z with no game live.
3. Link: an ncaaf alias table from verbatim ESPN abbreviations vs Kalshi ticker codes on one captured
   Saturday; measured link rate with refusal reasons; refuse ambiguous codes (many schools share prefixes).
4. Desk: ncaaf in the D1 tuple and the config on an adoption branch (S562 (ii) pattern), with
   `capacity_rule live_concurrency` already on.

## NOT VERIFIED

The series ticker, open-event counts per week, the ESPN-to-Kalshi code agreement for college teams, and
whether ncaaf games overlap the Sunday nfl and evening mlb windows enough to be starved by the per-sport
floor.
