# R2: cross-sport served capacity, local days 2026-10-01..10-06 (readiness lead, 2026-09-30 ~00:4xZ)

Read-only. Sources: ESPN site scoreboards (default urllib headers; a browser User-Agent gets HTTP 403) and Kalshi public events (series KXMLBGAME, KXNFLGAME, KXNBAGAME, KXWNBAGAME), queried 2026-09-30 ~00:35Z. No archive reads. Probe: scratchpad r2_capacity.py (RSS 30 MB).
Rule applied: schedule_d1._subset (schedule_d1.py:97-120). Rows are sorted by (start, game_id, ticker). A row is kept if fewer than two are kept, or if its start is at least 3600 s after the start of the second-to-last kept row. This is the capture_scheduler.py:113 rule of at most two starts per rolling hour, applied globally across sports. Ties at one start go to the lexically first game_id, so KXMLBGAME wins over KXNFLGAME.
The D1 for local day D is written at 12:00Z on D-1 (paper_desk_config: sports [mlb, nfl], local tz America/Chicago).
Labels: MEASURED = observed in this query. INFERRED = derived from code or listing behaviour, not observed. ESTIMATE = depends on start times or listings that do not exist yet.

## Listing facts (MEASURED)
- Kalshi MLB has 6 open events, the Wild Card G1s and G2s only. All 6 were created together at 2026-09-28T01:55Z. No Game 3 "if necessary" event exists in any status (open, unopened, closed). No Division Series event exists.
- Kalshi NFL has 31 open events, covering 10-01 (TNF PIT@CLE), 10-04 (14 games including London IND@WAS), 10-05 (MNF ATL@NO), and further weeks. All were created 2026-09-22T04:05Z, about 10 days ahead.
- Kalshi NBA has 3 events, all on 10-20. Kalshi WNBA lists only 09-29 and 09-30 events. No preseason NBA games are listed.
- ESPN soccer (eng.1, esp.1, ger.1, ita.1, fra.1, uefa.champions) has 0 fixtures on local 10-01..10-06.

## The "if necessary" answer
The four Wild Card Game 3s (10-01 PHI@ATL 18:00Z, CHW@HOU 21:00Z, BOS@NYY 00:00Z, CHC@SD 02:00Z) are NOT listed on Kalshi at 00:35Z 09-30 (MEASURED).
INFERRED: Kalshi creates a Game 3 only once it is needed, which is after the G2s end between about 21:00Z 09-30 and 05:00Z 10-01. That is after D1(10-01) runs at 12:00Z 09-30. So D1(10-01) will serve TNF only, and every Game 3 that is played is DROPPED.
The same risk applies to D1(10-03) for the Division Series Game 1s. Their teams are TBD until the Wild Card ends at about 05:00Z 10-02, and D1(10-03) runs at 12:00Z 10-02 (NOT VERIFIED).

## Table (served / excluded by the cap / unlisted at D1 time)
| Local day | Candidates (ESPN) | Served if every game is listed at D1 time | Served with the listings expected at D1 time |
|---|---|---|---|
| 10-01 | MLB WC G3 x4 (if necessary), NFL TNF PIT@CLE 00:15Z | 5 of 5 (the cap keeps all: 18:00, 21:00, 00:00, 00:15, 02:00) | 1: TNF only. The G3s are unlisted, so they are dropped (INFERRED) |
| 10-02 | MLB NLDS G1 x2, both dated 04:00Z 10-03 with teams TBD (ESPN time placeholder) | ESTIMATE 0-2; the placeholder start is wrong for capture focus | 0 (teams TBD), so nothing_schedulable (S582 tick path) |
| 10-03 | MLB ALDS G1 17:00Z (at CLE) and 22:30Z (at TB) | 2 of 2 | ESTIMATE 0-2 (depends on DS listing before 12:00Z 10-02) |
| 10-04 | NFL 14 (London 13:30Z; 8 at 17:00Z; 20:05Z; 3 at 20:25Z; SNF 00:20Z) plus MLB NLDS G2 x2 (20:00Z at MIL, 00:00Z at LAD) | 7 of 16: IND@WSH, ARI@NYG, DAL@HOU, NLDS G2 (MIL), MIA@MIN, NLDS G2 (LAD), DET@CAR. EXCLUDED by the cap: 9 (6 of the 8 at 17:00Z, and DEN@SF, KC@LV, LAC@SEA at 20:25Z) | IND@WSH and JAX@CIN do not link (INFERRED: the game_market_link nfl alias table is empty; ESPN has WSH/JAX where Kalshi has WAS/JAC). With the NLDS G2s listed: 4 NFL (ARI@NYG, DAL@HOU, MIA@MIN, DET@CAR) + 2 MLB. Without them: 5 NFL (adds DEN@SF at 20:25Z) |
| 10-05 | MLB ALDS G2 21:00Z and 00:00Z; NFL MNF ATL@NO 00:15Z; NLDS G3 x2 at the 04:00Z placeholder | 5 of 5 | ESTIMATE 1-5 (MNF is certain; the MLB games depend on DS listings) |
| 10-06 | MLB ALDS G3 x2 and NLDS G4 x2 (if necessary), all at the 04:00Z placeholder | ESTIMATE 2 of 4 (4 identical starts, and the cap keeps 2) | ESTIMATE 0-2 (the G4s are created only if needed) |

NBA preseason (10-03 MIA@TOR; 10-04 x2; 10-05 x5; 10-06 x4) and the WNBA semifinals are not in the D1 sports and are not listed on Kalshi. Soccer: 0.

## Consequences
- Soccer displacement (S531 acceptance): soccer has no fixture before 10-09, so it cannot displace MLB or NFL on 10-01..10-06.
  - The binding week-one squeeze is NFL Sunday 10-04, where only 4-5 of the 14 NFL games are served (the global two-per-hour cap plus the two alias gaps) before soccer is ever added.
  - S531's "no MLB/NFL displacement" check must use a day that has soccer fixtures (10-09..10-12) and compare against this baseline.
- A D1 revision is needed for the "if necessary" games: a pre-first-pitch D1 rerun WITH --now once the G3/G4/DS events are listed (for 10-01, after about 05:00Z and before the 18:00Z first pitch).
  - No row owns this today. The plan routes it to a row from the soccer-readiness lead's block.
- The nfl alias gaps (WSH/WAS, JAX/JAC) cost linked NFL games on the writer side as well as the state side (S560 recorded only the state side).

## CORRECTION (2026-09-30 ~01:4xZ, readiness lead R3): D1 days are UTC dates, and three MLB codes plus two NFL codes never link
The table above groups games by America/Chicago local date. That is WRONG for D1. build_schedule keeps a game only when `lower <= start < lower + 86400` with `lower = D + T00:00:00Z` (forward_schedule_writer.py:195, :203-204; refusal `outside_utc_date`), and schedule_d1 sets D = UTC date of --now + 1 (schedule_d1.py:167). The table above stays as the record; this section supersedes it.

MEASURED by the R3 rehearsal: schedule_d1 --sports mlb,nfl on the candidate S611 code at 00:55Z 09-30 wrote D1 2026-10-01 with full 1, served 1.
- Served: BOS@NYY G2 at 00:00Z 10-01 (KXMLBGAME-26SEP302000BOSNYY).
- mlb refusals:
  - missing_directional_team_evidence 1: CHC@SD G2 at 02:00Z 10-01.
  - no_kalshi_event_for_date_and_team 2: PHI@ATL G3 and CHW@HOU G3, which are unlisted.
  - outside_utc_date 2: the BOS@NYY and CHC@SD G3s, which fall on UTC 10-02.
- nfl refusals: TNF PIT@CLE at 00:15Z 10-02 is outside_utc_date, because it belongs to D1(10-02).

MEASURED over all 7 tracked D1 census files (docs/evidence/forward/schedules/*census.json): no MLB game involving TB, KC, WSH, SF, SD or AZ was ever linked (0 of 33 mlb full-selection rows); 16 such games were refused missing_directional_team_evidence. The writer compares alias(mlb, x) against the Kalshi ticker codes. The mlb alias table is live_board._MLB_ABBR (live_board.py:55: SD->SDG, SF->SFG, KC->KAN, TB->TAM, WSH->WAS, AZ->ARI, CHW->CWS), while Kalshi uses SD, SF, KC, TB, WSH and AZ.
- Postseason impact: every Padres home game, and the Rays-hosted ALDS G1 (22:30Z 10-03) and G2 (00:00Z 10-06), cannot be served.
- The NFL twin is the empty nfl alias table: ESPN WSH/JAX against Kalshi WAS/JAC.

Corrected table (UTC days). "If listed" assumes the event is listed before D1 runs at 12:00Z on D-1.
| UTC day | Candidates | Served, all listed | Served, expected |
|---|---|---|---|
| 10-01 | BOS@NYY G2 00:00Z, CHC@SD G2 02:00Z, PHI@ATL G3 18:00Z, CHW@HOU G3 21:00Z | 3 (CHC@SD alias-refused) | 1, MEASURED (BOS@NYY) |
| 10-02 | BOS@NYY G3 00:00Z, TNF PIT@CLE 00:15Z, CHC@SD G3 02:00Z | 2 (CHC@SD alias-refused) | 1-2: TNF is certain; the G3 is listed by 12:00Z 10-01 if a G3 is played |
| 10-03 | NLDS G1 x2 at an ESPN 04:00Z placeholder (teams TBD), ALDS G1 17:00Z (at CLE), ALDS G1 22:30Z (at TB) | 3 (the TB game is alias-refused) | 0-3 (depends on DS listing and real NLDS times) |
| 10-04 | NFL: London 13:30Z, 8 at 17:00Z, 20:05Z, 3 at 20:25Z. MLB: NLDS G2 20:00Z (at MIL) | 5 (IND@WSH, ARI@NYG, DAL@HOU, NLDS G2, MIA@MIN) | 4: ARI@NYG, DAL@HOU, MIA@MIN, plus the NLDS G2, or DEN@SF if it is unlisted. IND@WSH and JAX@CIN are alias-refused |
| 10-05 | NLDS G2 00:00Z (at LAD), SNF DET@CAR 00:20Z, ALDS G2 21:00Z (at CLE) | 3 | 1-3 (SNF is certain) |
| 10-06 | ALDS G2 00:00Z (at TB), MNF ATL@NO 00:15Z, NLDS G3 x2 at the 04:00Z placeholder | 4 (the TB game is alias-refused, so 3) | 1-3 (MNF is certain) |

The soccer displacement verdict is unchanged: there are 0 soccer fixtures before 10-09. The NFL Sunday squeeze is unchanged in kind: 3-4 of 14 NFL games are served on UTC 10-04 (SNF falls on UTC 10-05).
Follow-up row S612 (readiness lead): writer-side D1 link aliases for MLB (TB, KC, WSH, SF, SD, AZ) and NFL (WAS/JAC). The fix must not touch game_market_link.py before the 10-01 read-out, because it is an S490 dependency file under the IDENTITY FREEZE.
