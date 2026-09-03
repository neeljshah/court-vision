# S143 -- LATENT ARCHIVE-READ TRUNCATION IN THE REQUOTE READERS (fixed)

Date 2026-09-03 | lane: harness fix | parent row S137 section 6 | no charge, no seal, no bar

## VERDICT

**DONE -- premise CONFIRMED on two of the three named readers and FALSIFIED on the third.**
`pd.read_csv(..., comment="#")` truncated every archived row at the first `#`; the in-game
cluster convention is `mlb:<TICKER>#<real_game_seq>`, so the loss column came back **all-NaN on
9,669 of 9,669 MLB rows** of `data/cache/eval_gate/s116_pooled_ingame_2026-09-03.csv` -- silently,
not as an exception. The three call sites that carried the argument now route through one helper
that skips only LEADING `#` seal lines. **The change is a measured no-op on every archive these
modules read today**: the S106 and S87 requote outputs are identical field-for-field between the
old read path and the new one.

## 0. PREMISE, RE-MEASURED FIRST (Q8)

| claim in the row | measured now | status |
|---|---|---|
| `s106_requote.py` reads with `comment="#"` | yes, 2 call sites (lines 90 and 114: `S82_SERIES`, `S58A_SERIES`) | CONFIRMED |
| `tick_informative.requote` reads with `comment="#"` | yes, 1 call site (line 249) | CONFIRMED |
| `s121_requote.py` reads with `comment="#"` | **no** -- both of its `pd.read_csv` calls (lines 154, 195) already pass no `comment` | **FALSIFIED** |
| loss column NaN on 9,669 of 9,669 MLB rows | `loss_line` NaN 9669/9669, `d_partial_vs_line` NaN 9669/9669; clusters collapse 63 -> 27 | CONFIRMED |
| the published headline reproduces without `comment="#"` | mean `d_partial_vs_line` over the 9,669 MLB rows = **+0.012837467659961**, Brier line 0.215528 / partial 0.202690 -- the S116 memo's `+0.012837` | CONFIRMED |

Reproduction (read-only, from the main data tree):

```
with comment=#   : mlb rows 9669 loss_line NaN 9669 d_partial_vs_line NaN 9669 | clusters 27
without comment  : mlb rows 9669 loss_line NaN 0                              | clusters 63
headline improvement (mean d_partial_vs_line, mlb): 0.012837467659961
```

## 1. THE HEADER-COMMENT CONVENTION IS REAL, SO THE ARGUMENT IS CONDITIONED, NOT DELETED

Of the 58 CSV archives under `data/cache/eval_gate/`, **2 begin with a `#` line** and both are a
prereg seal, not a data comment:

- `s58_t2_first_soccer_gate_2026-09-03_perevent.csv` -> `# prereg_sha256=7125552f... k_launch=18`
- `s58_trialB_nba_halftime_asof_pergame_2026-09-03.csv` -> `# prereg_sha256=5dbdff42... k_at_launch=17`

The second of those is **read by `tick_informative._ARTIFACTS["s58_trialB_nba_halftime"]`**, so a
flat deletion of `comment="#"` would have broken a live reader: a plain `pd.read_csv` on it returns
one column named `# prereg_sha256=5dbdff42... k_at_launch=17`. Each file carries exactly one such
line, and it is always the first. Hence the fix skips LEADING `#` lines instead of treating `#` as
a comment character anywhere in the file, which keeps a `#` inside a cell intact.

## 2. THE CHANGE

New `scripts/platformkit/eval_gate/archive_read.py` (25 lines), one function `read_series(path)`:
it counts the leading lines that start with `#`, then reads with `skiprows=<that count>` and no
`comment` argument.

Call sites changed (3, all `pd.read_csv(..., comment="#")` -> `read_series(...)`):
`s106_requote.py:91`, `s106_requote.py:115`, `tick_informative.py:250` (inside `requote`).
`s121_requote.py` is NOT edited -- its premise is falsified above and neither of its reads
touches a sealed archive. The helper lives in its own module because `tick_informative.py` was at
exactly the 300-LOC rail and this lane owns only `requote` inside it.

## 3. A/B: THE READ CHANGE MOVES NOTHING (in-process, same session)

Both modules were re-run with `read_series` monkeypatched back to
`lambda p: pd.read_csv(p, comment="#")` and then with the shipped helper:

| module | old read vs new read, all leaf fields except `generated_at` | result |
|---|---|---|
| `s106_requote` | 157 leaves compared | **identical** |
| `tick_informative` (S87) | 123 leaves compared | **identical** |

## 4. RE-RUN AGAINST THE PUBLISHED ARCHIVES

| re-run | compared against | differing leaves | note |
|---|---|---|---|
| `s106_requote` | `s106_requote_s131corrected_2026-09-03.json` | **0 of 157** | exact |
| `s106_requote` | `s106_requote_2026-09-03.json` (pre-S131) | 39 of 159 | expected and already documented: the S131 real-game split (392 -> 360 real games, 122 -> 112 multi, 22,768 -> 21,318 ticks reassigned) -- S137 table row S106. NOT from this change (section 3) |
| `s121_requote` | `s121_requote_s131corrected_2026-09-03.json` | **0 of 2,827** | exact; module unedited |
| `s121_requote` | `s121_requote_2026-09-03.json` (pre-S131) | 787 of 2,828 | same S131 split, same as above |
| `tick_informative` (S87) | `s87_requote_2026-09-03.json` | 20 of 123, **max relative deviation 9.9e-16** | last-ULP float noise only; every printed digit, CI, verdict and count identical. Not from this change (section 3 shows the two read paths agree exactly), so it is environment float noise between the publishing run and this one |

Every verdict re-printed unchanged: S82 three features SCREEN_NULL, S87 trial A NULL,
s58_trialB_nba_halftime BEHIND, s80_player_grain SCREEN_NULL, S121 14 of 14 SCREEN_NULL with
0 clearing the unmoved +0.004 bar.

## 5. TEST

`tests/platformkit/eval_gate/test_s143_archive_read.py` -- **3 passed**
(`python -m pytest tests/platformkit/eval_gate/test_s143_archive_read.py -q`):

1. a cluster id `mlb:KXMLBGAME-26JUL051230NYMATL#1` survives the read, no NaN in the loss column,
   2 distinct clusters -- and the same fixture read with `comment="#"` is asserted all-NaN, so the
   defect itself is pinned in the test;
2. a leading `# prereg_sha256=... k_launch=...` line is still skipped and the 2 data rows survive;
3. none of the three readers named by S143 contains `comment="#"` any more.

## 6. A5 -- READER SWEEP

`tick_informative` is imported by 16 other modules; every one of them takes
`attach_informative_summary`, `flag_ticks` or `_quote`, none of which this lane touched -- only
`requote`'s own read line changed. Regression in master:
`scripts/platformkit/eval_gate/test_tick_informative.py` 17 passed,
`tests/platformkit/eval_gate/test_s121_requote.py` 4 passed,
`tests/platformkit/eval_gate/test_s137_rebaseline.py` 3 passed.

## 7. STILL OPEN (new gap, not this lane's to fix)

`scripts/platformkit/eval_gate/s86_nba_every_tick.py:208` reads a reference CSV with
`pd.read_csv(csv_path, comment="#")` and is the **fourth** instance of the same defect; it is
outside this lane's ownership. Its current corpus is NBA `game_id`-keyed (no `#`), so nothing is
wrong today, but the identical silent failure waits there. Register row text in section 9.

## 8. CONTRACT SELF-CHECK (A, B, Q)

| rule | status |
|---|---|
| A2 recompute the headline | done -- +0.012837 reproduced from the CSV before any edit |
| A5 grep every reader of a touched field | done, section 6 (16 importers, none affected) |
| A7 every evidence path exists | this memo, the test file, the 3 archives named -- all present |
| B1 circular metric | n/a, no metric scored here |
| B2 non-additive schema | none: no column, status or field renamed; the helper is additive |
| B6 orphans | none: no module moved or retired |
| B10 moved bar | no bar read or written; +0.004 untouched |
| Q1/Q2 prereg + ledger | n/a -- nothing scored, `_charge_ledger` never called, `backtest_fwer.jsonl` 18 rows and never opened |
| Q3 no threshold moved | held |
| Q6 calibration language only | held; no dollar/ROI/edge language, no retracted figure |
| Q7 sampling rail | n/a -- CONSTRUCT: 3 named readers enumerated, all 58 eval_gate CSV archives enumerated for a leading `#` |
| Q8 premise first | done, section 0 -- one third of the row FALSIFIED and reported as such |

## 9. REGISTER ROW TEXT (HARNESS_GAPS not edited by this lane)

S143 -> DONE; and one new row for the fourth call site. Both texts are in the lane report.

## 10. UNCHARGED / NOT DONE

No charge, no seal, no bar moved, no refit, no archived artifact rewritten (all re-runs went to a
scratch directory; `s121_requote.OUT_JSON` was redirected in-process so the published file was not
overwritten). `data/registry` untouched, no flag flipped, no pod contact, no push, nothing read or
written under `src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/`. NOT VERIFIED: this is
the lane's own report; no independent verifier has re-run it.
