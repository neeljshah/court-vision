# S95 -- the truncation path closed, provenance made per-row, sibling resolver opt-in

Date: 2026-09-03 | Lane: harness (system) | Row: S95 in `docs/evidence/HARNESS_GAPS_2026-09-03.md`
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections A, B and Q (self-checked below).
Calibration language only. No dollar / ROI / edge claim anywhere in this work.
NOT CHARGED: `_charge_ledger` never called; `backtest_fwer.jsonl` untouched at 18 rows;
`data/registry/` untouched; no flag flipped ON; no bar moved; nothing pushed.

---

## STEP 0 -- PREMISE (Q8)

### (a) CONFIRMED, still live. The exact lines (`domains/mlb/ingest_espn_box.py:242-254`, pre-fix):

```
242    if out.exists() and not new_df.empty:
243        try:
244            existing = pd.read_parquet(out)
...
247            new_df = (pd.concat([existing, new_df], ignore_index=True)
248                      .drop_duplicates(subset=["event_id"], keep="last"))
249        except Exception as exc:  # noqa: BLE001
250            log.warning("Could not read existing parquet %s: %s - overwriting", out, exc)
251
252    out.parent.mkdir(parents=True, exist_ok=True)
253    if not new_df.empty:
254        new_df.to_parquet(out, index=False)
```

There was NO shrink guard and NO atomicity: after a failed read, `new_df` is still just the
current batch and line 254 writes it over the whole corpus. `to_parquet` also writes in place,
so a crash mid-write leaves a torn target that the NEXT run fails to read -> the same branch ->
total loss. Both halves of the S91 mechanism are reproduced by reading the code alone.

### The same shape, repo-wide -- 19 sites in 18 files (all found, all wired)

Grep used: `grep -rn -i "overwrit" --include=*.py domains/ scripts/platformkit/`, then each hit
read in context. Every one is `read existing -> concat/dedup -> except: log "overwriting" ->
df.to_parquet(dest, index=False)`.

| file:line (pre-fix, the `log.warning` line) | write line |
|---|---|
| domains/baseball_kbo/ingest_kbo.py:249 | 255 |
| domains/baseball_npb/ingest_npb.py:226 | 233 |
| domains/basketball_nba/backfill_box_espn.py:94 | 96 |
| domains/basketball_nba/ingest_espn_box.py:281 | 286 |
| domains/basketball_nba/ingest_linescores.py:88 | 91 |
| domains/basketball_wnba/ingest_espn.py:191 | 196 |
| domains/basketball_wnba/ingest_espn_injuries.py:189 | 200-203 (tmp+replace, no shrink guard) |
| domains/basketball_wnba/ingest_linescores.py:177 | 182 |
| domains/mlb/ingest_espn_box.py:250 | 254 |
| domains/mlb/ingest_injuries.py:172 | 184 |
| domains/mlb/ingest_injuries.py:261 | 268 |
| domains/mlb/ingest_player_stats.py:257 | 261 |
| domains/mlb/ingest_probables.py:251 | 258 |
| domains/mlb/ingest_umpire_assignments.py:163 | 170 |
| domains/soccer/ingest_espn_athlete.py:208 | 211 |
| domains/soccer/ingest_espn_box.py:258 | 262 |
| domains/soccer/ingest_espn_players.py:271 | 275 |
| domains/soccer_intl/ingest_espn_finals.py:152 | 156 |
| domains/tennis/ingest_espn.py:266 | 271 |

`n = 19 (CONSTRUCT)` -- this is the exhaustive enumeration of the pattern, not a sample (Q7).
One of the 19 (wnba injuries) already wrote via a temp file + `Path.replace`, so it was safe
against a torn write but NOT against the shrink; the other 18 were unsafe against both.
`label_finals_refresh.py` -- the autonomous driver that calls several of these -- was read: it
already wraps each fetcher in `except Exception` and logs "fetch failed", so a raise here fails
that spec closed instead of crashing the loop.

### The provenance label site -- CONFIRMED drifted

`scripts/platformkit/ingame/ticker_settlement_join.py:60-68`, `_CLOSE_SOURCE_LABEL["mlb"] =
"ingame_outcome_label:espn_boxscores_parquet"`, written to every joined row at line 189/199.
Since S91 the mlb resolver answers most tickers from the `games.parquet` fallback map, so that
single per-sport constant no longer names the corpus a given row's outcome came from.

### The sibling resolver's constructor -- CONFIRMED identical dependency

`scripts/platformkit/ingame/hist_mlb_outcome_resolver.py:162-183`:
`def __init__(self, boxscore_df: Any = None, boxscore_parquet: Optional[Path] = None)`, falling
back to `DEFAULT_BOXSCORE_PARQUET = data/domains/mlb/espn_boxscores.parquet` -- the same 2-row
file. It already accepts an injected frame (`boxscore_df=`), which is how its tests run.

Nothing in the row was falsified.

---

## (a) THE WRITE GUARD

New: `scripts/platformkit/ops/safe_parquet_write.py` (`write_parquet_atomic`, `ShrinkRefused`,
`existing_row_count`). Ladder check: `scripts/platformkit/io_atomic.py` is the nearest existing
util but declares "stdlib only" and covers text/JSON only; `basketball_claims_io.
atomic_write_parquet` takes a `pa.Table` and has no shrink guard and no temp cleanup. A ~60-line
module reusing io_atomic's proven mkstemp + bounded-backoff `os.replace` shape was the smallest
correct thing.

* temp file in the SAME directory + `os.replace` (bounded retry on Windows `PermissionError`);
  any failure unlinks the temp and leaves the target untouched.
* row-count precondition read from the parquet FOOTER (metadata only, no full load): replacing
  an existing parquet with FEWER rows raises `ShrinkRefused` unless `allow_shrink=True`.
* if the footer read fails, the exception PROPAGATES -- an unreadable existing file is never
  silently overwritten.

Why refusing to shrink is safe for exactly these writers: each concats existing+new and dedups
`keep="last"`, so the merged frame is a superset of what is on disk and its count can only grow
or stay equal. A shrink therefore means the merge did not happen -- the S91 bug.

Wiring, all 19 sites: `log.warning(... "overwriting" ...)` -> `raise RuntimeError("S95:
unreadable existing parquet %s" % out) from exc` (the two sites that then set `combined = new_df`
lost that line), and `df.to_parquet(out, index=False)` -> `write_parquet_atomic(df, out)`.

Tests -- `scripts/platformkit/ops/test_safe_parquet_write.py`, **6 passed**: grow allowed; equal
row count allowed (a corrected re-run must still land); shrink refused AND the 20-row file still
reads back 20 rows; `allow_shrink=True` permits it; a garbage existing file raises (not
`ShrinkRefused`) and its bytes are unchanged; a write that blows up mid-serialisation leaves the
old file intact and no stray temp in the directory.

Existing per-file tests for the touched ingesters, re-run in master, all green:
kbo+npb **26 passed**, wnba espn/injuries/linescores **21 passed**, mlb
injuries/player_stats/probables/umpire **29 passed**, soccer athlete/players + soccer_intl
finals **19 passed**.

## (b) PER-ROW PROVENANCE

`MlbOutcomeResolver._pick` now records which map it read into `self.last_source`
(`"espn_boxscores_parquet"` / `"games_parquet_fallback"`). It is set at the top of `_pick`, not
at each return, because `_resolve` returns the FIRST non-None `_pick` -- so the last map consulted
is the one that answered. `ticker_settlement_join.join_ticker_file` writes an ADDITIVE
`outcome_source` column: `getattr(resolver, "last_source", None) or close_source`, so every other
sport (whose resolvers expose no such attribute) records its existing label and no existing key
changes value. `close_source` is deliberately NOT rewritten -- it is the resolver-family label and
several readers assert it; the comment above `_CLOSE_SOURCE_LABEL` now says so.

Additive, not a rename (B2): no key removed, no value changed, key order preserved with
`outcome_source` appended after `close_source`. Existing joined rows on disk are untouched -- the
live store was not re-joined.

Tests: `test_ticker_settlement_join.py` **9 passed** (the schema-freeze test now names
`outcome_source`, plus a new parametrised test asserting the row carries `espn_boxscores_parquet`
or `games_parquet_fallback` exactly as the resolver reports, while `close_source` stays put);
`test_ingame_outcome_label.py` **19 passed** (new test: the real resolver reports `espn...` for a
game in the ESPN map and `games_parquet_fallback` for one only in `_fb`).

## (c) SIBLING RESOLVER -- OPT-IN, MEASURED, LEFT OFF

`MlbTickerOutcomeResolver(games_fallback=False)` (default OFF) now optionally loads
`mlb_games_outcome_fallback.load_games_box_frame()` into a SEPARATE `_fb` map -- never merged into
`_final`, ESPN answers first, and the fallback is EXACT-DATE only (S91 measured that the +/-1 hop
mislabelled a postponement doubleheader). Tests `test_hist_mlb_outcome_resolver.py` **16 passed**
(new: the map is empty unless asked for; it answers on the exact date, is not consulted for the +1
hop, and never displaces an ESPN answer). `test_hist_mlb_forward_gate.py` **10 passed** unchanged.

DRY measurement of `run_forward_gate()`, no artifact written, no charge:

| | espn rows | fallback rows | n_games_captured | n_games_resolved | n_rows | verdict |
|---|---|---|---|---|---|---|
| flag OFF (master) | 2 | 0 | 27 | 0 | 0 | INSUFFICIENT_DATA |
| flag ON | 2 | 38,619 | 27 | 0 | 0 | INSUFFICIENT_DATA |

**The headline numbers do not move.** Reason, measured: the forward Kalshi capture corpus covers
2026-07-27..2026-07-28 (27 tickers), while the `games{,_current}.parquet` finals end 2026-07-12 --
the fallback carries 38,619 finals and not one of them is in this corpus's window. This is the
same residual S91 recorded ("3 after games_current's last date 2026-07-12"), here binding on 27
of 27. The gate was already INSUFFICIENT_DATA before this lane and still is; the flag stays OFF
and no new row is warranted for a delta of zero.

---

## Self-check against the contract

* B1 no circular metric -- the only measurement here is the forward-gate DRY run, computed over
  every captured ticker with nothing excluded.
* B2 additive schema -- `outcome_source` added, no key renamed/removed; the one test that pins the
  exact non-player key set was updated; a repo grep for exact key-set assertions on joined rows
  found no other reader.
* B3 no fall-through loss -- a resolver with no `last_source` records its existing label rather
  than dropping the row; an absent fallback map is empty, never fatal.
* B6 no orphans -- no module moved or retired.
* B10 / Q3 no bar moved -- this lane defines no bar and changed none.
* Q1/Q2 no prereg, no seal, no charge -- nothing scored is claimed; the DRY run is a reproduction,
  not a trial.
* Q6 calibration language only; none of the retracted figures appears.
* Q7 `n = 19 (CONSTRUCT)` for the writer enumeration; the forward-gate DRY run reports n_rows = 0
  honestly rather than sampling.
* Q8 premise re-measured first; every part CONFIRMED, none falsified.
* Human-gated paths untouched: no edit under `src/`, `kernel/`, `api/`, `intel/`,
  `scripts/team_system/`. `domains/<sport>/` and `scripts/platformkit/` are safe areas. No file
  owned by the concurrent S87b / S93 / S94 lanes was touched.

## NOT VERIFIED

The shrink guard is proven on synthetic frames in the per-file test, not against a real ingest
run -- these ingesters fetch from ESPN and this lane never fetches. Nothing was re-ingested, so
the live `espn_boxscores.parquet` is still the 2-row file S91 found; the guard prevents the NEXT
truncation, it does not restore the lost rows. And `write_parquet_atomic`'s Windows replace-retry
is copied in shape from `io_atomic._replace_via_tmp`, which is itself exercised only by the
text-path tests.
