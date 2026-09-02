# S83 -- the MLB close-join drops player identity: carry the five mlb_* columns through

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S83 (signals-ingame), successor of S80.
Verdict: **ACCEPT WITH CORRECTIONS** -- premise CONFIRMED, join fixed, live store backfilled,
S80 re-run from the joined store reproduces the verdict and the shape but NOT the exact
headline n; the 5-tick difference is measured and explained below (it is a defect of S80's
own re-join, not of this change). Calibration language only (Q6). No charge, K never read.

Files
- `scripts/platformkit/ingame/ticker_settlement_join.py` (the join; 292 -> 300 LOC)
- `scripts/platformkit/ingame/s83_join_identity_backfill.py` (NEW, 135 LOC, one-off backfill)
- `scripts/platformkit/ingame/test_ticker_settlement_join.py` (+1 test; 7 passed)
- `scripts/platformkit/eval_gate/s80_player_grain_screen.py` (additive `--no-rejoin`)

---

## STEP 0 -- premise (Q8), re-measured first at HEAD 277bfa90b

**CONFIRMED, not falsified.**

The writer is `scripts/platformkit/ingame/ticker_settlement_join.py`. The drop is not a
filter or a rename -- it is the fixed dict literal in `join_ticker_file`, which enumerates
eleven keys and silently discards every other key of the source tick `r`:

```
185	    out_lines = []
186	    for r in ticks:
187	        row = {
188	            "sport": sport, "game_id": ticker, "ts": r.get("ts"),
189	            "model_prob": r["model_prob"], "market_prob": r["market_prob"],
190	            "side": r.get("side", _lg.PAIR_SIDE), "state_summary": r.get("state_summary", ""),
191	            "outcome": outcome, "close_source": close_source,
192	            "close_prob": close["close_prob"] if close else None,
193	            "close_ts": close["close_ts"] if close else None,
194	            "edge_claimed": False,
195	        }
196	        out_lines.append(json.dumps(row, ensure_ascii=True))
```

The five columns are the ones `inplay_capture_loop.py:975-979` resolves onto the grade row:
`mlb_batter_id`, `mlb_pitcher_id`, `mlb_pitcher_pitch_count`, `mlb_ondeck_id`,
`mlb_bullpen_used`.

On disk, both stores read line by line (no memory, no S80 quotation):

| store | files | rows | rows with each mlb_* key PRESENT | rows with a NON-NULL value |
|---|---|---|---|---|
| `data/cache/ingame_grade/mlb` (raw) | 405 | 79,566 | 11,251 (14.14 pct) | 8,384 (10.53 pct); pitch_count 8,378 |
| `data/cache/ingame_grade_joined/mlb` (scored) | 227 | 78,986 | **0** | **0** |

Matches the S83 row exactly: 0 of 78,986 joined rows, 10.53 pct of raw ticks.

## CHANGE 1 -- the join carries them through (8 lines)

```python
_CARRY_KEYS: Tuple[str, ...] = ("mlb_batter_id", "mlb_pitcher_id",
                                "mlb_pitcher_pitch_count", "mlb_ondeck_id",
                                "mlb_bullpen_used")
...
        row.update({k: r[k] for k in _CARRY_KEYS if k in r})
```

Additive (B2): no key renamed or removed, the eleven existing keys keep their order and
values, an absent source key stays absent rather than becoming a fabricated null. Every
FUTURE join now keeps player grain.

## CHANGE 2 -- why the live store needed a BACKFILL and not a re-run

A re-run would have destroyed the store. `MlbOutcomeResolver` reads
`data/domains/mlb/espn_boxscores.parquet`, which today holds **2 rows** (2026-07-14 ..
2026-07-16). A scratch `backfill_sport("mlb")` into `.../scratchpad/joined_after` returned
`n_files 235, n_joined 1, join_rate 0.0043` -- 1 ticker resolvable out of 235. The outcome
corpus that produced the 227-file store in July no longer exists locally, so the join is not
reproducible today and the store's `outcome` / `close_prob` / `close_ts` cannot be re-derived.

`s83_join_identity_backfill.py` therefore only ADDS the identity fields to the rows already
on disk. It matches **positionally, not on `(game_id, ts)`**: `join_ticker_file` emits
exactly one joined row per VALID source tick in file order, so joined row *i* is
`_load_ticks(source)[i]`. Verified over the live store before use -- 227/227 files, 78,986
rows, **0 length mismatches, 0 ts mismatches**. A file whose lengths or ts sequence disagree
is skipped whole; a row that gains no identity is re-emitted as its ORIGINAL line, verbatim.

This matters because the joined store contains **1,659 duplicate `(game_id, ts)` rows**, so
a key-based re-join is not well defined there (see the reproduction section).

## Before / after on the real store

Old store copied to `data/cache/ingame_grade_joined_pre_s83/mlb` (227 files, kept, never
deleted) BEFORE any write. The rebuild was written to `.../scratchpad/joined_s83b` and
compared against that copy first; the live store was written only after the comparison came
back clean.

| check | result |
|---|---|
| file set | identical, 227 == 227 |
| rows | 78,986 -> **78,986** |
| lines byte-identical to the pre-S83 line | 67,915 (every row that gains no identity) |
| non-player key set / key ORDER mismatches | **0** of 78,986 |
| non-player VALUE mismatches (any of the 11 original keys) | **0** of 78,986 |
| rows now carrying the five keys | 0 -> 11,071 |
| rows with a NON-NULL identity | 0 -> **8,287**, over **53 games** |
| files touched | 53 of 227 |
| misaligned files | 0 |

Live store re-read after the write: 78,986 rows / 227 games; each of the five keys present on
exactly 11,071 rows; 8,287 rows with non-null identity over 53 games.

## Per-file tests

```
python -m pytest scripts/platformkit/ingame/test_ticker_settlement_join.py -q   -> 7 passed in 1.55s
python -m pytest tests/platformkit/ingame/test_s80_player_grain_screen.py -q    -> 5 passed in 4.39s
python -m scripts.platformkit.ingame.s83_join_identity_backfill                 -> demo OK
```

New test `test_player_identity_carried_through_and_other_fields_unchanged`: a synthetic raw
store with all five columns on one tick and none on a second; asserts each value is carried
through unchanged, that the second row does not gain a fabricated key, that the non-player
key set and key ORDER are identical between the two rows, and that the eleven non-player
fields equal the pre-S83 schema exactly. The backfill's own `demo()` asserts positional
placement on two ticks that SHARE a ts (a dict would collapse them), byte-identical
passthrough, and refusal on a length mismatch.

## S80 reproduction from the joined store (`--no-rejoin`)

`load_player_ticks(rejoin=False)` reads `mlb_pitcher_id` / `mlb_batter_id` straight off the
joined row; `rejoin=True` (the default, unchanged) keeps S80's `(game_id, ts)` dict.

| run | n ticks | n games | Brier e4 | e4+player | improvement | DM p | CI95 | verdict |
|---|---|---|---|---|---|---|---|---|
| S80 memo (quoted) | 2,267 | 13 | 0.248462 | 0.244703 | +0.003759 | 0.7937 | [-0.026879, +0.034398] | SCREEN_NULL |
| re-join, re-run now | 2,267 | 13 | 0.248462 | 0.244703 | **+0.003759** | 0.7937 | [-0.026879, +0.034398] | SCREEN_NULL |
| **joined store, `--no-rejoin`** | **2,262** | 13 | 0.248435 | 0.244812 | **+0.003623** | 0.8008 | [-0.026976, +0.034222] | SCREEN_NULL |
| re-join, embargo 0 | 3,717 | 23 | 0.223746 | 0.229515 | -0.005770 | 0.1114 | [-0.012984, +0.001445] | SCREEN_NULL |
| joined store, embargo 0 | 3,707 | 23 | 0.223702 | 0.229411 | -0.005709 | 0.1158 | [-0.012940, +0.001522] | SCREEN_NULL |

The S80 headline reproduces EXACTLY on the re-join path (+0.003759, n 2,267), so nothing in
this row moved that measurement. Reading identity from the joined store gives 2,262 ticks and
+0.003623 -- **5 ticks fewer**, and the reason is measured, not assumed:

- 8,287 joined rows own a non-null identity positionally; the `(game_id, ts)` dict assigns
  identity to **8,309** -- S80's own number.
- The 22-row difference is exactly the rows where the two disagree on `mlb_pitcher_id`
  (measured: 22). The dict is built last-wins over 1,659 duplicate-key joined rows, so on a
  duplicated timestamp it hands a row the OTHER tick's pitcher.
- 5 of those 22 fall in the embargo-1 SCREEN partition and 10 in the embargo-0 one --
  precisely the 2,267 -> 2,262 and 3,717 -> 3,707 gaps.

So the joined-store read is the correct one and the re-join was mildly contaminated. Both
runs land on the same verdict (SCREEN_NULL, below the +0.004 bar), the same 13 / 23 clusters,
the same fold betas, the same sign, and improvements 0.000136 apart. Bar unchanged (+0.004,
B10/Q3); nothing lowered.

## NOT VERIFIED

- The S80 headline does **not** reproduce to the digit off the joined store: n 2,262 vs
  2,267 and +0.003623 vs +0.003759. The verdict, cluster counts, fold betas and sign
  reproduce; the exact n and improvement do not, for the measured duplicate-timestamp reason
  above. The register row and this memo say so rather than quoting +0.003759 as reproduced.
- The backfill is a ONE-OFF over what is on disk. It is **not** a re-run of the join and it
  does not re-derive `outcome`, `close_prob` or `close_ts` -- those cannot be re-derived at
  all today (espn_boxscores.parquet is down to 2 rows). If that corpus is ever restored, the
  fixed join alone produces the identity and this module becomes dead; it is not wired into
  any loop and has zero callers.
- Positional correspondence was verified on the CURRENT 227 files only. It is a property of
  `join_ticker_file` (one output row per valid input tick, in order), asserted per file at
  backfill time, not proven for any other store.
- The 1,659 duplicate `(game_id, ts)` joined rows are REPORTED, not fixed. Whatever writes
  two ticks at one timestamp still does; this row only stops the scored store from having to
  guess between them.
- Only MLB carries these fields at all (S80: NBA / soccer / tennis / WNBA are 0.00 pct), so
  `_CARRY_KEYS` is exercised on one sport. Other sports' joins are unchanged and gain nothing.
- The joined store now has an OPTIONAL schema: 11,071 of 78,986 rows carry the five keys and
  67,915 do not. Readers that enumerate keys per row (the pattern every consumer here uses)
  are unaffected; a reader that assumes a fixed key set per file would see two shapes.
- Nothing was scored beyond re-running S80's existing screen. No prereg sealed,
  `_charge_ledger` never called, `backtest_fwer.jsonl` never opened (still 18 rows), K never
  read, `data/registry/` untouched, no flag flipped on, no pod contact, no push.
- `soccer_intl` and `mlb_clean` joined stores were not touched or re-read.
