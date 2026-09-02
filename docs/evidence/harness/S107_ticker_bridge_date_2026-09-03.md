# S107 -- the Kalshi-ticker -> live-game bridge now checks first pitch, not just teams

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S107 (ops), follow-on of S106.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked
below). Calibration language only (Q6); nothing here is a dollar, ROI or edge claim.

---

## STEP 0 -- PREMISE (Q8), printed before any change

### The exact bridge code path

`inplay_capture_loop._process_game` (pre-diff line 793) calls `ls_fn(sport, gid)`, which
is `ingame_live_state.live_state(sport, ticker)` and ALWAYS misses -- `gid` is a Kalshi
ticker, never the ESPN numeric event id. On that miss (pre-diff lines 796-798) it falls
through to `_scan_live_by_legs(sport, legs, gid=..., nowdt=..., states=...)`
(pre-diff lines 452-495), which scans `_ls.live_states(sport)` and returns the first
in-progress state whose home AND away display names both appear in the market's legs.

### What identifies the live game

`ingame_live_state._extract` builds each live state from one ESPN scoreboard event:
`game_id` = `ev["id"]` (the ESPN numeric event id, also aliased `espn_event_id`), plus
`home`/`away`, `home_display`/`away_display`, scores, `frac_elapsed`, `status`, and the
segment/base-out fields. **Before this diff it carried no date and no first pitch at
all.** That is the mechanical reason the bridge could not tell two nights of a series
apart: the only fields the scan could compare were the team names, which are identical
on both nights.

### What the ticker string encodes

`KXMLBGAME-26JUL061915NYMATL` = 2026-07-06, 19:15 **ET**, NYM at ATL. Parsers that
already exist in the repo, and what each one keeps:

| Parser | Keeps | Note |
|---|---|---|
| `odds_provider/kalshi_series_spec.ticker_game_date` | date only | the one the existing guard uses; the trailing `1915` is discarded |
| `ingame/ingame_id_resolver_mlb.parse_kalshi_mlb_ticker` | `{yy,mon,dd,hhmm,blob}` | MLB-only (`^KXMLBGAME-`) |
| `ingame/hist_mlb_outcome_resolver.parse_mlb_ticker` | date + doubleheader `G<n>` | drops the time |
| `eval_gate/close_join_mlb._TICKER` (+ `_ET_OFFSET_H = 4`) | date + HH + MM -> "first-pitch UTC" | **the precedent that the ticker HHMM is ET** |
| `ingame/ingame_outcome_label.py:230` | -- | states it outright: "Ticker HHMM is ET; box start_times are UTC" |
| `espn_wp_backfill_measure._TICKER_RE` | date + HHMM + team blob | same shape, different consumer |

None of them was wired into the bridge.

### Does a date check already exist on this path? YES -- so the row's wording is FALSIFIED

`_scan_live_by_legs` has carried a DATE GUARD since commit `441bf5507`
("fix(ingame): date-gate _scan_live_by_legs ticker->live-state binding (series
wrong-date class)", Fri Jul 10 18:16:25 2026 -0500). Pre-diff lines 480-484:

```python
game_date = _ticker_game_date(gid)
if game_date is not None:
    today = date.fromisoformat(_now_et_day(nowdt))
    if game_date not in (today, today - timedelta(days=1)):
        return None
```

**PREMISE PARTIALLY FALSIFIED (Q8).** The row says the bridge matches "by team pair with
no date check". A date check exists. But the DEFECT it names is not falsified, because
that check is a different predicate from the one the bar asks for:

1. It compares the TICKER to TODAY. It never looks at the matched game -- which, before
   this diff, carried no date to look at.
2. It is day-granular, so it cannot separate a doubleheader.
3. It **deliberately allows an ET-yesterday ticker** (`today - timedelta(days=1)`, for a
   game still live just after ET midnight). That is exactly the direction the row
   describes: a series' NEXT game binding to the PREVIOUS day's ticker.

So the bar ("the bridge requires the live game's date / first pitch to match the
ticker's") was genuinely unmet, and the smallest honest change is to add the missing
comparison rather than to close the row.

### Measured, from the store on disk (A2 -- recomputed here, not quoted)

`data/cache/ingame_grade_joined/mlb`: 227 files, 78,986 ticks, ts range
`2026-06-20T00:51:03Z` .. `2026-07-12T23:02:46Z`.

* S106's headline reproduced with `eval_gate/real_game_split.assign_real_game_seq`:
  **122 of 227 tickers hold > 1 real game (0.5374)**, 392 real games,
  22,768 / 78,986 ticks reassigned (28.8 pct), boundary reasons
  `{inning_decrease: 156, score_reset: 6, ts_gap: 3}`.
* Capture-side store `data/cache/ingame_grade/mlb` (what the pod actually writes, the
  denominator the verification query below uses): 401 tickers, **122 multi (0.3042)**,
  566 real games, 22,890 / 79,566 ticks reassigned.
* Signed gap of every tick against its own ticker's encoded first pitch:
  * **direction A** (tick more than 12 h BEFORE the ticker's first pitch = last night's
    game filed under a LATER ticker; this is the direction the existing guard rejects):
    **32,510 ticks**, last one `2026-07-12T03:57:03Z` on `KXMLBGAME-26JUL121610AZLAD`
    at -16.2 h.
  * **direction B** (tick more than 12 h AFTER = the next night's game filed under the
    EARLIER ticker; the direction the existing guard permits by design): **287 ticks**,
    1 ticker (`KXMLBGAME-26JUL101840MILPIT`), last one `2026-07-11T18:54:22Z` at +20.2 h.

Direction-A ticks continue for ~1.2 days AFTER the guard commit landed in master, so on
the node that wrote this corpus the guard was not in force during the corpus window
(deploy lag, or the capture node was running older code). This lane did not ssh to the
pod and cannot confirm which; it is listed as an orchestrator check below.

---

## THE CHANGE

New predicate module + one condition inside the existing scan. No behaviour change on
any path where either side lacks a time (missing != bad, B3).

`scripts/platformkit/ingame/ticker_date.py` (new, 128 LOC, pure, no I/O, `_demo()`
self-check under `__main__`):

* `ticker_first_pitch_utc(ref)` -- `-26JUL061915` -> 2026-07-06 19:15 ET -> aware UTC.
  A ticker with no HHMM (e.g. `KXWCGAME-26JUN22USAMEX`) -> `None` = no info.
  zoneinfo `America/New_York` when available, fixed EDT otherwise (same call
  `close_join_mlb` already makes, with the ceiling named in a `ponytail:` comment).
* `state_start_utc(state)` -- parses the state's `start_time`; `None` when absent.
* `bridge_gap_hours(gid, state)` -- absolute hours between the two, or `None` (NO INFO,
  never "far"). `bridge_date_ok(...)` is the boolean form. `BRIDGE_WINDOW_H = 12.0`.

`scripts/platformkit/ingame/ingame_live_state.py` `_extract` (+9 lines, 8 of them
comment): additive `"start_time": str(ev.get("date") or "") or None` -- the ESPN event's
own scheduled start, verbatim. No existing consumer reads this key (grepped).

`scripts/platformkit/ingame/inplay_capture_loop.py` `_scan_live_by_legs`: the loop no
longer returns the first team match. Among team-matching states it keeps the one whose
`start_time` is NEAREST the ticker's first pitch and within `BRIDGE_WINDOW_H`; a
candidate outside the window is skipped and, if the caller passed the new optional
`reason_out` dict, recorded as `bridge_date_mismatch`. `gap is None` (either side has no
time) returns that first match immediately -- byte-identical to the old behaviour. The
pre-existing DATE GUARD is untouched and still runs first (B10: no bar moved).

`inplay_capture_loop._process_game`: passes `reason_out=bridge_reason` and, on the
no-state return, reports `bridge_reason.get("reason") or "no_live_state"`. The heartbeat
already buckets that string into `grade_write_fail_by_reason`, so the named counter needs
no new plumbing.

A5 -- every reader of the reason string was grepped and the two that map it were updated
(B2):

* `ingame_placement_funnel._STAGE_OF_REASON` -- an UNMAPPED reason falls through as
  "cleared every stage", which would have silently inflated the funnel. Mapped to
  `live_state`, the same stage as `no_live_state`.
* `inplay_status._REASON_LABEL` -- already falls back to the raw string; a human label
  was added anyway.

`inplay_derivative_mlb._state_bridge` calls the same `_scan_live_by_legs` and therefore
inherits the fix (root cause fixed once, where both callers route through).

## TESTS (per-file only)

| File | Result |
|---|---|
| `scripts/platformkit/ingame/test_inplay_capture_bridge.py` | 15 passed, 1 failed |
| `scripts/platformkit/ingame/test_ingame_live_state.py` | 55 passed |
| `scripts/platformkit/ingame/test_ingame_placement_funnel.py` | 8 passed |
| `scripts/platformkit/ingame/test_inplay_status.py` | 4 passed |
| `scripts/platformkit/ingame/test_tennis_capture_bridge.py` | 2 passed |
| `tests/platformkit/ingame/test_inplay_derivative_mlb.py` | 32 passed |
| `python -m scripts.platformkit.ingame.ticker_date` | self-check OK |

**The one failure is PRE-EXISTING, not a regression.** `test_bridge_enables_ingame_bet`
fails identically on master: stashing this diff and re-running the same file gives
`1 failed, 10 passed` with the same test name (it pairs, `n_pairs == 1`, but no longer
bets). With the diff: `1 failed, 15 passed`. It is out of scope for this row and is
reported, not fixed.

Five tests added to the existing bridge test file (no new test module):

* `test_next_day_of_series_does_not_bridge_to_previous_ticker` -- day-2 of a MIL@PIT
  series (`start_time` 2026-07-07T22:40Z) against ticker `KXMLBGAME-26JUL061840MILPIT`,
  with `now` = 20:30 ET Jul 7 so the PRE-EXISTING day guard passes it as "yesterday".
  Asserts `None` and `reason_out == {"reason": "bridge_date_mismatch"}`.
* `test_same_day_game_still_bridges` -- same ticker, `start_time` 2026-07-06T22:40Z, binds.
* `test_doubleheader_binds_each_ticker_to_its_own_game` -- two same-day tickers (1305 /
  1915) and two live states (17:05Z / 23:15Z); each ticker takes its own game by time.
* `test_state_without_start_time_is_no_info_not_a_reject` -- B3: no `start_time` -> binds
  as before.
* `test_heartbeat_counts_bridge_date_mismatch` -- through `poll_once`: `n_pairs == 0` and
  `grade_write_fail_by_reason == {"bridge_date_mismatch": 1}`.

Plus `test_start_time_copied_from_event_date` in `test_ingame_live_state.py` -- the guard
is inert if the field is never populated, so this asserts the ESPN `date` is copied
verbatim and is `None` when the feed omits it.

## Self-check against the contract

B1 no exclusion set. B2 the two reason-string readers were updated; `start_time` is a new
additive key with no existing reader. B3 no-info on either side keeps the old behaviour.
B4 the roster is rebuilt from `legs_by_game` every tick, so a skip is retried next tick
and nothing becomes unclaimable. B5 **nothing was copied to the pod by this lane.** B6 no
module moved. B7/B8/B9 no sampling or fitting here. B10 the pre-existing guard's values
are unchanged; `BRIDGE_WINDOW_H` is a new bar, not a moved one. Q1/Q2/Q4/Q5 no scored
comparison and no ledger charge -- this is an ops fix, not a trial. Q3 the bar
(+/- 12 h) is the one the row names. Q6 calibration language only. Q7 the tests are
`n = 5 (CONSTRUCT)`: the enumerated cases are next-day, same-day, doubleheader-first,
doubleheader-second, and no-info. Q8 the premise was re-measured first and is reported
partially falsified above. Q9 no differential is claimed.

The 22,768 mislabelled ticks already on disk are NOT touched; `real_game_split` remains
the read-side correction, exactly as the row states.

---

## ORCHESTRATOR SECTION

### Which pod process runs this code

`inplay_capture_runner` -- **pid 19598**, one of the 11 supervisor children under
`python -u -m supervisor --profile paper` (**pid 19236**). It imports
`inplay_capture_loop.poll_once` / `serve_forever` directly
(`scripts/platformkit/ingame/inplay_capture_runner.py:38`) and is the process S105
recorded writing `data/cache/depth_history/mlb/` through the 300 s depth hook.

**The register row's restart target is wrong and must not be used.** Pids **21620 /
21622 are `mlb_book_capture.run_pod_capture`**, which does NOT import
`inplay_capture_loop` at all -- it bridges through `game_pk_bridge_live`, whose own
docstring records that "Kalshi tickers are matched by their OWN encoded date (from the
ticker string), not the caller's date arg". `mlb_book_capture.py` is untouched by this
diff. **Do not restart 21620 / 21622 for S107.**

`ingame_live_state.py` is imported far more widely, so every supervisor child picks up
the new `start_time` key at the same restart; it is additive and no consumer reads it.

### Deploy (only after ACCEPT -- B5)

```
git -C /c/Users/neelj/nba-ai-system archive <ACCEPTED_SHA> -- \
  scripts/platformkit/ingame/ticker_date.py \
  scripts/platformkit/ingame/inplay_capture_loop.py \
  scripts/platformkit/ingame/ingame_live_state.py \
  scripts/platformkit/ingame/ingame_placement_funnel.py \
  scripts/platformkit/ingame/inplay_status.py \
  | ssh -F ~/.ssh/config.pod pod 'tar -x -C /workspace/nba-ai-system'
```

### md5 parity

```
git -C /c/Users/neelj/nba-ai-system show <ACCEPTED_SHA>:scripts/platformkit/ingame/ticker_date.py | md5sum
git -C /c/Users/neelj/nba-ai-system show <ACCEPTED_SHA>:scripts/platformkit/ingame/inplay_capture_loop.py | md5sum
git -C /c/Users/neelj/nba-ai-system show <ACCEPTED_SHA>:scripts/platformkit/ingame/ingame_live_state.py | md5sum
git -C /c/Users/neelj/nba-ai-system show <ACCEPTED_SHA>:scripts/platformkit/ingame/ingame_placement_funnel.py | md5sum
git -C /c/Users/neelj/nba-ai-system show <ACCEPTED_SHA>:scripts/platformkit/ingame/inplay_status.py | md5sum

ssh -F ~/.ssh/config.pod pod 'cd /workspace/nba-ai-system && md5sum \
  scripts/platformkit/ingame/ticker_date.py \
  scripts/platformkit/ingame/inplay_capture_loop.py \
  scripts/platformkit/ingame/ingame_live_state.py \
  scripts/platformkit/ingame/ingame_placement_funnel.py \
  scripts/platformkit/ingame/inplay_status.py'
```

All five must match before the restart. (`git show` avoids any local-worktree drift; a
CRLF checkout would otherwise differ from the pod's LF copy -- compare against `git show`,
not against the working file.)

### Restart

The runner is a supervisor child, so kill **only the supervisor** and let the watchdog
relaunch it with its children. The cmdline is unchanged (no new flag):

```
current: /usr/local/bin/python -u -m supervisor --profile paper        (pid 19236)
after:   /usr/local/bin/python -u -m supervisor --profile paper        (identical)
```

Do not touch 4035 (track daemon), 21620 / 21622 (mlb book capture) or 254284. Confirm
adoption -- the capture heartbeat must be fresh and must now be able to carry the new
reason bucket:

```
ssh -F ~/.ssh/config.pod pod 'cd /workspace/nba-ai-system && \
  python -c "import json;h=json.load(open(\"data/cache/ingame_heartbeat.json\"));\
print(h[\"as_of\"], h[\"n_live\"], h[\"n_pairs\"], h[\"grade_write_fail_by_reason\"])"'
```

(If the heartbeat path differs on the node, read whichever file
`inplay_capture_runner` was started with -- the key to look at is
`grade_write_fail_by_reason`.)

### Orchestrator check this lane could not make

Direction-A misbinds continue to `2026-07-12T03:57:03Z`, ~1.2 days after `441bf5507`
landed in master. Confirm on the pod that the deployed
`scripts/platformkit/ingame/inplay_capture_loop.py` actually contained that guard during
the corpus window -- if the node had been running pre-`441bf5507` code, the deploy step
above is fixing two guards at once, not one.

### Verification query -- share of tickers spanning > 1 real game, over ONE live slate

Target **0**. Run it against the day the restarted runner writes (the capture-side store,
not the joined one), after that slate's last final:

```
ssh -F ~/.ssh/config.pod pod 'cd /workspace/nba-ai-system && python - <<PY
import json
from pathlib import Path
import pandas as pd
from scripts.platformkit.eval_gate.real_game_split import assign_real_game_seq

SLATE = "2026-09-XX"   # the ET day of the verified slate
rows = []
for f in sorted(Path("data/cache/ingame_grade/mlb").glob("*.jsonl")):
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("game_id") and str(r.get("ts") or "").startswith(SLATE):
            rows.append(r)
df, summary = assign_real_game_seq(pd.DataFrame(rows))
per = df.groupby("game_id")["real_game_seq"].nunique()
print("tickers", len(per), "multi", int((per > 1).sum()),
      "share %.4f" % ((per > 1).mean()), summary)
PY'
```

Baselines this lane measured locally with the same call, for the pre-fix corpus:

| Store | tickers | multi | share |
|---|---|---|---|
| `data/cache/ingame_grade/mlb` (capture side) | 401 | 122 | 0.3042 |
| `data/cache/ingame_grade_joined/mlb` (scored) | 227 | 122 | 0.5374 |

A one-slate run is a SINGLE WINDOW: it can only show the defect is gone on that slate,
never that the bridge is correct in general. Label it that way in the register row.
The complementary read is the heartbeat's `bridge_date_mismatch` count -- a non-zero
count on a series day is the guard firing, which is the intended behaviour, not a fault.

---

Evidence paths cited by this memo, all present at write time:
`scripts/platformkit/ingame/ticker_date.py`,
`scripts/platformkit/ingame/inplay_capture_loop.py`,
`scripts/platformkit/ingame/ingame_live_state.py`,
`scripts/platformkit/ingame/ingame_placement_funnel.py`,
`scripts/platformkit/ingame/inplay_status.py`,
`scripts/platformkit/ingame/test_inplay_capture_bridge.py`,
`scripts/platformkit/ingame/test_ingame_live_state.py`,
`scripts/platformkit/eval_gate/real_game_split.py`,
`data/cache/ingame_grade/mlb`, `data/cache/ingame_grade_joined/mlb` (local-only, gitignored).
