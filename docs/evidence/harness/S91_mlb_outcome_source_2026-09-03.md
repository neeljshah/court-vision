# S91 -- MLB outcome source: espn_boxscores.parquet was TRUNCATED; games.parquet closes it

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S91 (data) -- "MLB OUTCOME SOURCE TRUNCATED".
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked below).
Verdict: **CLOSED** -- bar met at 95.74 pct (bar: >= 95 pct), with one named residual.
Calibration/label space only; no dollar, ROI or edge quantity appears anywhere in this row.

---

## STEP 0 -- PREMISE (re-measured today, Q8)

### The file

| fact | value |
|---|---|
| path | `data/domains/mlb/espn_boxscores.parquet` |
| rows | **2** |
| columns | 105 (`event_id, home_abbr, away_abbr, home_score, away_score, status, start_time, venue, attendance, home_bat_*, home_pit_*, home_fld_*, away_*, date`) |
| size / mtime | 69,645 bytes / **2026-07-17 00:01:35** |
| row 1 | `401817370  2026-07-14  STATUS_FINAL  NL vs AL  0-4  start 2026-07-15T00:00Z` (the All-Star game) |
| row 2 | `401816143  2026-07-16  STATUS_FINAL  PHI vs NYM  1-4  start 2026-07-16T22:00Z` |

### Was it always 2 rows, or truncated? -- **TRUNCATED.** Four independent pieces of evidence.

1. **The live joined store could not exist otherwise.** `data/cache/ingame_grade_joined/mlb`
   holds **227 ticker files / 78,986 rows**, every one carrying an `outcome` that
   `ticker_settlement_join.join_ticker_file` obtained from
   `ingame_outcome_label.MlbOutcomeResolver` reading *this* parquet. 227 resolved games
   cannot come from 2 rows.
2. **A committed docstring measured it fuller.** `scripts/platformkit/gate_run_mlb_espn_box.py`
   (committed `d7dd811a6`, 2026-06-21): "data/domains/mlb/espn_boxscores.parquet holds only
   ~3 weeks of current-season box rows" -- weeks of daily MLB slates, i.e. a few hundred rows.
3. **Two resolver docstrings were grounded against it.** `hist_mlb_outcome_resolver.py` and
   `ingame_outcome_label.py` both record team-code overrides "grounded from the 201 real
   tickers' team-code tails cross-checked against espn_boxscores.parquet's home_abbr/away_abbr
   for the same date" -- that cross-check needed the 2026-06-28..07-04 slates on disk.
4. **The mechanism is in the builder.** `domains/mlb/ingest_espn_box.py:242-250` merges the new
   batch into the existing parquet inside a `try`, and on ANY read failure logs
   `"Could not read existing parquet %s: %s -- overwriting"` and writes **only the new batch**.
   The only caller is the bounded refresher
   `scripts/platformkit/autonomy/label_finals_refresh.py` (spec `mlb_espn_boxscores`, capped at
   `max_dates_per_tick`), which passes just the missing dates. One bad read on one tick therefore
   truncates the file to that tick's finals. The two surviving rows are exactly one such batch:
   the 2026-07-14..07-16 All-Star break, which contains only two FINAL games. mtime 2026-07-17
   00:01 is that tick.

   Honest limit: the parquet is gitignored, so there is no version history to diff and the
   read-failure branch left no surviving log line. Points 1-3 establish that it WAS fuller;
   point 4 is the only overwrite path in the only writer, so it is the mechanism by elimination,
   not by a captured log.

### Is a fuller copy anywhere on disk? -- **No.**

- `data/backups/` holds `eval_gate/`, `tennis_source_2026-09-02/`,
  `gamelog_2025-26_pre_playoff_merge_20260526/` and two `pnl_ledger.csv.*.gz` -- no MLB box.
- `find data -iname "*espn_box*" -o -iname "*boxscore*"` returns only the NBA
  (`data/domains/basketball_nba/espn_boxscores*.parquet`), the WNBA `cdn_backfill/*/boxscore.json`
  tree, and `data/domains/mlb/asof_espn_box.parquet` -- 40 rows of *derived as-of feature diffs*
  keyed `E00000...`, carrying **no scores at all**. Not an outcome source.

### Do games.parquet / the settled ledgers cover the 235 ticker dates?

The 235 tickers are the non-numeric stems of `data/cache/ingame_grade/mlb/*.jsonl`
(405 files total; the numeric ones are ESPN-id keyed). Their dates run **2026-06-19 .. 2026-07-27**.

| candidate on-disk source | rows | covers? |
|---|---|---|
| `data/domains/mlb/games.parquet` | 27,983 (2010-04-04..2021-11-02) | out of era, but same schema |
| `data/domains/mlb/games_current.parquet` | 11,179 (2022-04-07..**2026-07-12**) | **yes** -- `home_runs`/`away_runs` finals for 558 games since 2026-06-01; misses only the 3 tickers after 07-12 |
| the two combined | **39,162** (the row count named in the S91 row) | the source used below |
| `scripts/platformkit/clv_ledger.py` DEFAULT_LEDGER = `data/frontend/clv_ledger.jsonl` | **20 rows total, 2 `KXMLBGAME` tickers** | no (0.9 pct) |
| `data/cache/settled_bets.json` | 644 rows, all NBA player props (`player_name`/`stat`/`line`) | no (0 pct) |
| `data/cache/pm_paper` | **does not exist** | no |

So the settled-Kalshi / paper-ledger route is a dead end at under 1 pct, and
`games{,_current}.parquet` is the only on-disk source that covers the corpus.

**PREMISE CONFIRMED** (truncated, not born small) and the row's own suggested source
(games.parquet outcomes) is the viable one.

---

## THE CHANGE (smallest additive diff, ESPN path untouched)

**New** `scripts/platformkit/ingame/mlb_games_outcome_fallback.py` (112 lines) --
`load_games_box_frame(paths=None)` reads `games{,_current}.parquet` and returns them in the
espn_boxscores column shape (`event_id/date/status/home_abbr/away_abbr/home_score/away_score/
start_time`), so a resolver ingests it with no new parsing code. Two deliberate narrowings:

- team codes mapped to ESPN abbrs (`CUB->CHC, CWS->CHW, KAN->KC, SDG->SD, SFO->SF, TAM->TB,
  WAS->WSH, OAK->ATH, LOS->LAD, SFG->SF`) and **any row whose mapped code is not one of the 30
  current franchises is dropped**. games.parquet carries relic codes (LOS 2010-2017, and
  one-off BRS / SFG / CHC rows in 2020) that would otherwise widen the ticker tail-split
  alphabet and could make a split ambiguous.
- `start_time` is empty, so a doubleheader key (2 rows) fails **closed** in the resolver rather
  than guessing.

**Changed** `scripts/platformkit/ingame/ingame_outcome_label.py` (280 -> 300 lines, at the cap):
`MlbOutcomeResolver.__init__` gains `games_fallback: bool = True`; the fallback rows land in a
**separate** `self._fb` map (never mixed into `self._rows`), so ESPN always wins and the fallback
is consulted only after the ESPN attempts miss. `_ingest` gains an `into=` target and now
unions `self._abbrs` instead of assigning it; `_pick` gains a `rows_map=` argument; `available`
now also counts `_fb`. Nothing renamed or removed (B2): all 11 emitted join keys, every existing
signature, and the ESPN-only behaviour with `games_fallback=False` are unchanged.

### Why the fallback is EXACT-DATE only

`_resolve` tries the ticker date and +1 day for ESPN rows (ESPN start_times are UTC, so a late
game files on the next UTC day), plus a heavily-guarded -1. games.parquet dates are the **local
game date**, so those hops do not apply. Measured: letting the fallback use the +1 hop raised
coverage from 224 to 229 of 235 but produced a **wrong label** --
`KXMLBGAME-26JUL071415MILSTLG1` (a postponement doubleheader with no clock to order it) settled
against the **2026-07-08** MIL@STL game and came out 1 where the store says 0. That is exactly
the landmine `ingame_outcome_label._resolve` already documents from the live 2026-07-07
mis-settlement. Exact-date only gives **zero** wrong labels (see verification) and still clears
the bar, so the 5 extra tickers are given up deliberately.

**Test** (new, per-file): `scripts/platformkit/ingame/test_mlb_games_outcome_fallback.py` --
5 tests, **5 passed**. The synthetic 3-ticker case the row asked for: `T_ESPN_ONLY` (ESPN row
only), `T_GAMES_ONLY` (games row only -- unresolvable before this change), `T_BOTH` (both
sources present and **deliberately disagreeing**; the ESPN row must win, asserted on both
`home_win` and `final_score`). Plus: exact-date-only (a +/-1 day ticker must return `None`),
relic-code dropping / abbr mapping, and a real-disk smoke check.

Regression tests re-run in master: `test_ingame_outcome_label.py` **18 passed**,
`test_ticker_settlement_join.py` **7 passed**.

---

## MEASURED -- resolved share of the 235 tickers

`today` pinned to 2026-09-02 so the -1-day age guard is deterministic.
n = 235 is a **CONSTRUCT** (every ticker-keyed file in the corpus), not a sample (Q7).

| | resolved | share |
|---|---|---|
| BEFORE (`games_fallback=False`, i.e. master) | **1 / 235** | 0.43 pct |
| AFTER (`games_fallback=True`, default) | **225 / 235** | **95.74 pct** |

The one ticker ESPN could already resolve (`KXMLBGAME-26JUL142000ALNL`, the All-Star game)
returns **0 before and 0 after** -- the fallback never overrides an ESPN label.

The 10 still unresolved, all failing **closed**, never guessed:

| ticker(s) | why |
|---|---|
| `26JUL071415MILSTLG1`, `26JUL071945MILSTLG2` | doubleheader; games.parquet has 2 rows for (2026-07-07, MIL, STL) and no start_time to order G1/G2 |
| `26JUL101840MILPIT`, `26JUL111605MILPIT` | postponement into a 2026-07-11 doubleheader, same reason |
| `26JUN221910CHCNYM`, `26JUN241910CHCNYM` | the 06-22 ticker has no game on its own date and 06-24 carries a doubleheader pair |
| `26JUN251945AZSTL` | no ARI@STL row on the ticker's own date |
| `26JUL182207DETLAA`, `26JUL191607DETLAA`, `26JUL271435SEATEX` | after `games_current.parquet`'s last date, **2026-07-12** |

---

## VERIFICATION -- 220 independent labels agree, 0 disagree

The live joined store's `outcome` column was written in July from the **then-full ESPN box
parquet**. Re-deriving those same 220 games from games.parquet is a genuine cross-source check
(different provenance, different ingest, different team-code space).

| check | result |
|---|---|
| overlapping ticker files | 220 |
| rows in them | 77,062 |
| length mismatches | **0** |
| non-player-column value mismatches (all 12 columns incl. `outcome`) | **0** |

Every one of the 220 games' home-win label derived from games.parquet is identical to the label
the July ESPN parquet produced. Not a self-fit (B8): the two label sets come from different files
written months apart by different ingests.

---

## DRY REBUILD of the S83 joined store (scratch only -- the live store was NOT touched)

`backfill_sport("mlb", grade_dir=<scratch copy of data/cache/ingame_grade>,
joined_dir=<scratch>/joined)`. The grade dir was copied first because `join_ticker_file` also
settle-stamps the SOURCE file; the live `data/cache/ingame_grade/mlb` newest mtime is still
2026-09-01 04:44 and the live joined store's is still 2026-09-02 14:16 (S83's own write), i.e.
nothing under `data/` was written by this run.

| | before (S83 memo) | after |
|---|---|---|
| `n_files` | 235 | 235 |
| `n_joined` | **1** | **221** |
| `join_rate` | 0.0043 | **0.9404** |

221 rather than 225 because 4 of the resolvable tickers have `no_valid_ticks` in the source file.

Compared against the live store (227 files / 78,986 rows):

| | value |
|---|---|
| dry files / rows | 221 / 77,144 |
| live files reproduced **byte-identically** on every non-player column | **220 of 227** (96.9 pct) |
| live files NOT reproducible | 7 (1,924 rows) -- the doubleheader / postponement / off-date set above |
| files in dry but not live | 1 (`KXMLBGAME-26JUL142000ALNL`) |

**Answer to the row's question:** the store is now **96.9 pct rebuildable from raw** and was
0.4 pct before, but a rebuild is still **lossy** (7 files, 1,924 rows), so the live store must
NOT be overwritten. S83's positional backfill remains the right artifact for the rows on disk.

---

## RESIDUAL -- what Neel would have to decide

The 10 unresolved tickers need one of two acquisitions, both his call:

1. **Re-fetch ESPN MLB boxscores for 2026-06-19..2026-07-27** via
   `domains.mlb.ingest_espn_box.ingest_range` (about 39 dates). This is the S62 decision --
   NOT taken here, no network call was made in this row. It is the only source that restores
   `start_time`, which is what unblocks the 7 doubleheader/postponement files as well.
2. **Extend `games_current.parquet` past 2026-07-12** -- closes only the 3 late tickers, still
   no clock, so the 7 doubleheader files stay unresolvable.

Also fixing the leak permanently would mean hardening
`domains/mlb/ingest_espn_box.py:242-250` so a failed read of the existing parquet aborts instead
of overwriting. `domains/` is out of this row's scope; filed as a follow-up gap below.

---

## Follow-up gaps this row uncovered (not fixed here)

1. **The truncation path is still live.** `domains/mlb/ingest_espn_box.py:249` overwrites the
   parquet with just the current batch whenever the existing file fails to read. Every
   `label_finals_refresh` spec that reuses an `ingest_range`-shaped writer has the same shape.
2. **Provenance label drift.** `ticker_settlement_join._CLOSE_SOURCE_LABEL["mlb"]` still reads
   `ingame_outcome_label:espn_boxscores_parquet`; after this change most re-joined rows would
   take their outcome from games.parquet. Left byte-identical on purpose so the comparison above
   stays honest (changing it would have made all 220 files differ) -- it needs its own row.
3. **Sibling resolver untouched.** `hist_mlb_outcome_resolver.MlbTickerOutcomeResolver` (read by
   `hist_mlb_forward_gate.py` over `data/cache/inplay_history/mlb`) has the identical dependency
   on the truncated parquet. It already accepts `boxscore_df=`, so `load_games_box_frame()` can
   be handed to it -- but that changes a *scored* gate's inputs, which needs its own measured row.

---

## Self-check against the contract

- **B1** no metric excludes rows to pass: the denominator is all 235 tickers, and the 10 failures
  are named individually.
- **B2** additive only -- no key, column or status value renamed or removed; `games_fallback=False`
  reproduces master exactly; all 12 joined non-player columns byte-identical on 220 files.
- **B3** missing evidence passes through as `None`, never a quarantine or a guess.
- **B6** no module moved or retired; no orphaned import or `-m` reference.
- **B7** the comparison is the WHOLE corpus (235 tickers / 227 live files), not a head slice.
- **B8** the 220-file agreement is against labels written months earlier from a different file.
- **B10** no bar moved: the row's bar is 95 pct and the measured result is 95.74 pct.
- **Q1/Q2** no scored comparison and no prereg or FWER charge -- this is a data-source row.
  The ledger stays at 18 rows; `_charge_ledger` was not called.
- **Q3** no threshold lowered; the +1-day hop that would have reached 229 was rejected on
  correctness, not traded for coverage.
- **Q6** calibration/label space only; no dollar, ROI, profit or edge language; none of the
  retracted figures appears.
- **Q7** n = 235 is an exhaustive CONSTRUCT enumeration; reproduction (A2) replaces eye-check.
- **Q8** premise re-measured first and CONFIRMED, with the mechanism traced to the writer.
- **A7** every path named above was confirmed present at write time.

## Artifacts

- `scripts/platformkit/ingame/mlb_games_outcome_fallback.py` (new)
- `scripts/platformkit/ingame/test_mlb_games_outcome_fallback.py` (new, 5 passed)
- `scripts/platformkit/ingame/ingame_outcome_label.py` (changed, 300 lines)
- scratch-only, not committed: the dry rebuild under
  `.../scratchpad/s91/joined/mlb` and `.../scratchpad/s91/dry_summary.json`
