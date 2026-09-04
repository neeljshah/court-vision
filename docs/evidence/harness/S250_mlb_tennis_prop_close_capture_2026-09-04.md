# S250 MLB and Tennis Prop Close Capture - Attempts 1c and 2

## Attempt 2 - per-sport CLOSED AT LIMIT findings

Attempt 1c's capture archive remains exactly one newline byte with zero JSONL
rows, zero duplicate identities, and MLB 0/0 plus tennis 0/0 real-priced
clusters. Attempt 2 does not add a synthetic capture row or score anything.
It records the bounded conditions that close this attempt at the S250 limit.
The normalized source responses are archived in
`docs/evidence/harness/S250_mlb_tennis_prop_close_capture_2026-09-04_attempt_2_venue_responses.jsonl`.

### MLB - NOT VERIFIED: overnight event window plus absent API credential

The exact S250 route that would have been called was
`GET /v4/historical/sports/baseball_mlb/events?date=2026-09-04T08:21:07Z` at
the The Odds API venue. The Attempt 1c preflight was blocked before HTTP:
credential kind `ODDS_API_KEY` was absent, no value was read, and the result is
HTTP not sent rather than a claimed venue status. The archived capture JSONL is
therefore the exhaustive 0-row result for that preflight, not an omitted
failure.

For the time limit, MLB Stats API's schedule endpoint returned HTTP 200 at
03:39:23 CDT with 16 scheduled games and `totalGamesInProgress: 0`; its next
game was Detroit at Cleveland at 13:10 CDT (18:10Z). The same endpoint's
three-day response reported 16 games on September 4 and 15 on September 5.
The venue's documented market list returned HTTP 200 and lists
`pitcher_strikeouts`, so this is not a claim that MLB prop coverage is absent.

Finding: **MLB NOT VERIFIED** for the 03:40 CDT attempt window. The required
route could not be sent without the environment API credential, and no MLB
event was live. The earliest conditional >=30-cluster window is the two-slate
period ending after the September 5 slate opens at 15:10 CDT (16 plus 15
scheduled events), provided the user supplies that credential and the listed
market returns concrete prices. The resumable command is:

```text
python -m scripts.platformkit.ingame.s250_prop_close_capture --loop-seconds 300
```

### Tennis - CLOSED AT LIMIT: no documented player-prop market

The exact corresponding route was
`GET /v4/historical/sports/tennis_atp_us_open/events?date=2026-09-04T08:21:07Z`.
It has the same preflight result: `ODDS_API_KEY` absent, no credential value
read, no HTTP request sent. The schedule source
`https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=2026-09-04&s=Tennis`
returned HTTP 200 with `events: null` at 03:39:23 CDT, so it supplied no live
event or next event time for this capture window.

More decisively, the The Odds API documented market-list endpoint returned
HTTP 200 and does not list `player_aces`, while it does identify tennis set
markets such as `h2h_s1`. Thus the named tennis player-prop market required by
this helper is not listed by the venue; this is a venue-coverage limit, not a
rate or latency claim.

Finding: **Tennis CLOSED AT LIMIT**. No wall-clock window is expected to yield
30 tennis `player_aces` clusters from this tier while that market is unlisted.
The resumable command remains available for a future tier that lists the
market, but it is not expected to succeed on the current venue:

```text
python -m scripts.platformkit.ingame.s250_prop_close_capture --loop-seconds 300
```

## Attempt-1c result (superseded by Attempt 2 limit findings)

The corrected S240 premise is confirmed, and the capture helper plus exhaustive
restart construct are available. The required one-time provider requests could
not be sent because this worktree has no `ODDS_API_KEY`; no embedded credential
was used. Attempt 2 classifies that credential preflight with the separately
archived schedule and market-coverage evidence above.

## Corrected premise re-measurement

Every prior S240 a17 path was resolved by replacing only its worktree prefix
with `C:/Users/neelj/nba-track-a16`; the repo-relative tails are the binding
inputs. `scripts.platformkit.boxscore_prop_census` streamed each NBA JSON file
and each JSONL line one at a time into
`.planning/2026-09-04-s250-attempt-1c/premise_census`.

| Sport | Resolved input path | Size | Full-set count | Real-price clusters | Premise status |
|---|---|---:|---:|---:|---|
| NBA | `C:/Users/neelj/nba-track-a16/data/cache/cv_fix/closing_props` | 6,491,336 bytes | 77 files; 48,515 tidy rows | 77 / 77 file clusters | confirmed |
| MLB | `C:/Users/neelj/nba-track-a16/data/frontend/prop_history_corpus_mlb.jsonl` | 1,283,918 bytes | 3,000 rows | 0 / 777 date clusters | confirmed |
| Tennis | `C:/Users/neelj/nba-track-a16/data/frontend/prop_history_corpus_tennis.jsonl` | 1,230,398 bytes | 3,000 rows | 0 / 389 date clusters | confirmed |
| Soccer | `C:/Users/neelj/nba-track-a16/data/frontend/prop_history_corpus_soccer.jsonl` | 0 bytes | 0 rows | 0 / 0 date clusters | confirmed |

No repo-relative input is absent in this worktree. The complete census retained
all 3,000 MLB and tennis rows in their denominators, including their null
market-probability values.

## NBA producer tier and LIMIT route

The actual NBA payload writer is historical, not the current consumer cited in
Attempt 1. It is `scripts/cv_fix_fetch_closing.py` at commit
`0f1aff49f4be8fb1d97984d9f60e0425a068d14c`, SHA-256
`091243eea0e4bd52787e3aeff7af08cef716ac63d17897e26dec762dc3db2662`.
Its `event_odds` function at line 56 calls the historical single-event The Odds
API route; line 134 invokes it and line 140 writes the response to
`data/cache/cv_fix/closing_props/{gid}.json`. The current checked-in
`scripts/platformkit/odds_provider/oddsapi_provider.py` only requests team
markets and is not the producer.

The additive helper reuses the producer tier's historical events route followed
by historical single-event odds:
`/v4/historical/sports/{sport}/events` then
`/v4/historical/sports/{sport}/events/{event_id}/odds`. It chooses
`pitcher_strikeouts` for MLB and `player_aces` for the tennis availability
probe. The provider documents that player markets use the single-event route,
that the historical request cost is 10 credits per returned market and region,
and that requests should be spaced over several seconds after a 429 response.
The serialized helper waits at least four seconds between event-market requests
and between sport polls. No pod or local deployment occurred.

## One-time probe and capture finding

The one permitted local probe command was run once at 2026-09-04T08:21:07Z.
It returned `ODDS_API_KEY absent` before an HTTP request, so it generated zero
provider calls, zero event attempts, and zero capture rows. This preserves the
one-probe budget for a credentialed run and does not manufacture either a
rate-limit or zero-price denominator.

| Sport | Market | HTTP attempts | Captured real-priced clusters | Attempt 2 LIMIT verdict | Current finding |
|---|---|---:|---:|---|---|
| MLB | `pitcher_strikeouts` | 0 | 0 / 0 | NOT VERIFIED: no live event at 03:40 CDT; API credential absent before route call | named limit finding above |
| Tennis | `player_aces` | 0 | 0 / 0 | CLOSED AT LIMIT: venue documentation does not list the player-prop market | named limit finding above |

The empty, schema-preserving JSONL artifact is
`docs/evidence/harness/S250_mlb_tennis_prop_close_capture_2026-09-04.jsonl`.
It contains zero JSONL rows and the exhaustive duplicate count is 0. Its
summary is `S250_mlb_tennis_prop_close_capture_2026-09-04_summary.json`.
No OOS calibration comparison or capture-derived score was computed; therefore
the shared purge plus symmetric-embargo evaluator was not invoked.

## Restart construct (Q7)

The focused test constructs every specified case using a temporary append-only
JSONL file and a deterministic price-bearing API response. It verifies that a
durably appended snapshot survives each restart and that an interrupted terminal
fragment is discarded as uncommitted bytes before resuming.

| Enumerated case | Construct result | Rows after restart | Duplicate identities |
|---|---|---:|---:|
| clean stop | PASS | 2 | 0 |
| mid-poll interrupt | PASS | 2 | 0 |
| process kill mid-write | PASS | 2 | 0 |

The helper is `scripts/platformkit/ingame/s250_prop_close_capture.py` (256
lines). It reads a stop-flag path, has no production callers, uses no feature
flag, and only prints the required `nohup setsid nice` deployment command. The
command was printed for review only; it was not run and no file was copied to a
pod.

## NOT VERIFIED

- A credentialed MLB historical-event response and concrete price availability
  at this account after the next scheduled slate opens.
- Any tennis prop market from a tier that lists player props; this venue's
  unlisted `player_aces` market cannot establish broader tennis availability.
- At least 30 real-priced clusters for either sport. This attempt is closed at
  limit rather than presenting an unmeasured count as success.
- Any live capture beyond the zero-row environment-gated attempt, or any pod
  deployment.
- Any calibration evaluation; no comparative score exists in this attempt.

## Attempt-1 text (superseded)

## Verdict

Superseded by Attempt 1c. Attempt 1 incorrectly retained another worktree's
absolute prefix, so it recorded the two visible JSONL stores as absent and
stopped before the required work.

## Contract and machine

This memo follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and
Q. It was measured locally in `C:/Users/neelj/nba-track-a16` because the
binding S240 stores are local read-only inputs. No pod route ran and no file was
deployed. No data store, register, or ledger was written.

## Exact binding re-measurement

Command:

```text
python -m scripts.platformkit.boxscore_prop_census --output-dir .planning/2026-09-04-s250-prop-close-capture/premise_census
```

Exact stdout:

```text
sport | source_count | price_sources | price_clusters | verdict
nba | 77 | 77 | 77 | SCORABLE
mlb | 0 | 0 | 0 | NOT SCORABLE
soccer | 0 | 0 | 0 | NOT SCORABLE
tennis | 0 | 0 | 0 | NOT SCORABLE
```

This is the same complete-store census route that S240 names:
`scripts/platformkit/boxscore_prop_census.py`, SHA-256
`6b8ef2086025a9b97de29aec995dc02d24425744b8e96b203c3ba34b0493ab37`.
It reads NBA JSON one file at a time and JSONL one line at a time; no input file
exceeds the 300 MB limit.

| Sport | Binding expectation | Fresh complete-store result | Cluster result | Status |
|---|---|---:|---:|---|
| NBA | 77 files, 77 real-price clusters | 77 files, 6,491,336 bytes | 77 / 77 file clusters | Reproduced |
| MLB | 3,000 rows, 0 real-price rows | 3,000 rows, 1,283,918 bytes | 0 / 777 date clusters | Premise confirmed |
| Tennis | 3,000 rows, 0 real-price rows | 3,000 rows, 1,230,398 bytes | 0 / 389 date clusters | Premise confirmed |
| Soccer | 0 rows | 0 rows, 0 bytes | 0 / 0 date clusters | Premise confirmed |

Bound input paths and current byte sizes:

| Input | Full local path | Size | Resolution |
|---|---|---:|---|
| NBA payload directory | `C:/Users/neelj/nba-track-a16/data/cache/cv_fix/closing_props` | 6,491,336 bytes | not applicable (JSON) |
| MLB JSONL store | `C:/Users/neelj/nba-track-a16/data/frontend/prop_history_corpus_mlb.jsonl` | 1,283,918 bytes, 3,000 rows | not applicable (JSONL) |
| Tennis JSONL store | `C:/Users/neelj/nba-track-a16/data/frontend/prop_history_corpus_tennis.jsonl` | 1,230,398 bytes, 3,000 rows | not applicable (JSONL) |
| Soccer JSONL store | `C:/Users/neelj/nba-track-a16/data/frontend/prop_history_corpus_soccer.jsonl` | 0 bytes, 0 rows | not applicable (JSONL) |

S240's committed reference retained the a17 prefix. Attempt 1c resolves that
prefix to this worktree and freshly re-measures the same repo-relative stores.

## NBA tier identity found before the stop

The NBA close-payload consumer is `scripts/cv_fix_oos_v2.py:583`: it opens
`data/cache/cv_fix/closing_props/<gid>.json` with `json.load`. The tracked
reusable tier module is
`scripts/platformkit/odds_provider/oddsapi_provider.py`, SHA-256
`0bc4d64d02888bfb7b9404a3654c61e7147a009b41ca26702e3fa474d3b3a03a`.
Its documented route is The Odds API v4 team-markets request. S250's one-per-
sport player-prop LIMIT probe was not run because the binding premise had
already failed and the specification requires a stop.

## Required S250 artifacts after the stop

| Artifact | State |
|---|---|
| Capture helper | Not created |
| Focused test | Not created |
| Capture JSONL sample | Not created |
| Summary JSON | Not created |
| Restart cases | Not executed |
| Scorability forecast | Not computed |
| Preregistration and seal | Not created; no scored comparison was started |

## NOT VERIFIED

- Whether the identified tier offers MLB or tennis player-prop markets remains
  unverified. The required probe is outside the allowed post-falsification work.
- No per-sport close capture, concrete price, duplicate-key count, or restart
  behavior exists for S250.
- The absent stores are a worktree-local condition; no claim is made about a
  different worktree or external machine.

## Self-check

- Q8: the exact premise was re-measured before any implementation and the
  command output above is quoted verbatim.
- B1 and B9: the census retained all visible source units; the absent stores
  were not removed from the denominator.
- B2-B6 and B10: no production, schema, flag, deployment, retry, or threshold
  change was made.
- B7-B8 and B11: this is an exhaustive source census with no render, fit, or
  single-run system claim.
- Q1-Q5 and Q9: no scored or OOS comparison exists, so no preregistration,
  ledger charge, evaluator, second corpus, paired-loss archive, or seal applies.
- Q6: this memo makes no performance or financial claim.
- Q7: the three restart cases were not started because Q8 closes the row first.

Evidence paths present at commit time:

- `docs/evidence/harness/S250_mlb_tennis_prop_close_capture_2026-09-04.md`
- `docs/evidence/harness/S250_mlb_tennis_prop_close_capture_2026-09-04_attempt_2_venue_responses.jsonl`
- `docs/evidence/harness/S240_boxscore_prop_census_2026-09-04.md`
- `docs/evidence/tracking/specs/S250_spec.md`
- `docs/evidence/tracking/VERIFIER_CONTRACT.md`
