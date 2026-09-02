# S104 -- soccer state capture + the shared as-of staleness rail

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S104 (raised by the S99 memo,
`docs/evidence/harness/S99_cross_market_2026-09-03.md`).
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q, self-checked below.
No prereg, no seal, no charge, no K read. `_charge_ledger` never imported;
`data/cache/eval_gate/backtest_fwer.jsonl` still 18 rows, mtime 2026-09-02 12:27 (before this
lane). No flag flipped, no bar moved, `data/registry/` untouched, nothing read or written under
`src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/`. Calibration language only; ASCII only.

## Verdict

| Part | Verdict |
|---|---|
| (a) soccer writer emits structured state | **PREMISE FALSIFIED (Q8)** -- the writer already does, and has since the 2026-06-27 cutover visible on disk. A schema test now pins it. No code change was warranted. |
| (a) the 22 legacy bare-string files | **CLOSED AT LIMIT** -- score is not recoverable; the raw capture beside them carries the same bare string. |
| (b) shared as-of helper + s99 wiring | **LANDED**, behaviour-preserving: the S99 headline reproduces byte-for-byte. |
| (b) `foundry/ingame_screen.py` loader wiring | **PREMISE FALSIFIED** -- that loader performs no as-of join at all; its ticks carry their own `state_summary`. Wiring it would have ADDED a join, not preserved behaviour. |

## STEP 0 -- premise, re-measured (Q8)

### The file census

`data/cache/ingame_grade_joined/soccer_intl/` holds **51** `.jsonl` files, not 47. 47 is the
count of games S99 could join (the 96 multi-market Kalshi keys intersected with this store,
minus the ones whose ticker did not resolve to an outcome); the store itself is 51.

Of the 51, **24** carry the bare `state_summary = "live"` sentinel on at least one tick, and
**22 carry it on every tick** -- exactly the 22 the row names. The remaining two
(`26JUN27CODUZB`, `26JUN27COLPOR`) are MIXED: they start bare and switch to the structured
string mid-capture, which is the cutover itself caught in the act.

`state_summary` is a **flat KV string**, never a dict: `"home_score=0.0 away_score=0.0 minute=1"`.
The row's phrasing ("a dict with score + minute") is a description of the content, not the type.

### Two sub-premises FALSIFIED

1. **"every capture before 2026-06-25"** is wrong. The bare-only files run up to first-capture
   **2026-06-27** (`26JUN27CROGHA`, `26JUN27PANENG`, and the four `26JUN26*` games first captured
   on 06-27). The cutover is mid-day **2026-06-27**: the two mixed files switch inside that day,
   and every file whose first capture is **2026-06-28 or later is 100 pct structured**.
2. **"captures from 2026-06-25 on carry score + minute on every tick"** is wrong on the
   `minute` half. In the structured files the score is on every tick, but `minute` is not:
   `26JUN27DZAAUT` is 109 of 156 ticks with `minute`, 47 with `home_score`/`away_score` only
   (`_soccer_minute` returns None on status shapes it cannot read honestly, e.g. some
   halftime/stoppage payloads). That is an honest absence, not a fabrication, and B3 applies:
   the tick is passed on with a null minute rather than quarantined. It is also why a
   structured file still loses ticks in S99's `dropna(subset=["cur_h", "minute"])`.

### Per file: name, first capture date, n ticks, ticks carrying score+minute, kinds

```
-- per file: name, first_capture_date, n_ticks, n_with_score+minute, kinds
KXWCGAME-26JUN22ARGAUT.jsonl     2026-06-22 n=186    score+min=0      {'bare:live': 186}
KXWCGAME-26JUN22FRAIRQ.jsonl     2026-06-22 n=75     score+min=0      {'bare:live': 75}
KXWCGAME-26JUN22JORDZA.jsonl     2026-06-23 n=182    score+min=0      {'bare:live': 182}
KXWCGAME-26JUN22NORSEN.jsonl     2026-06-23 n=141    score+min=0      {'bare:live': 141}
KXWCGAME-26JUN23ENGGHA.jsonl     2026-06-23 n=609    score+min=0      {'bare:live': 609}
KXWCGAME-26JUN23PANCRO.jsonl     2026-06-23 n=364    score+min=0      {'bare:live': 364}
KXWCGAME-26JUN23PORUZB.jsonl     2026-06-23 n=31     score+min=0      {'bare:live': 31}
KXWCGAME-26JUN24MARHTI.jsonl     2026-06-24 n=424    score+min=0      {'bare:live': 424}
KXWCGAME-26JUN24SCOBRA.jsonl     2026-06-24 n=117    score+min=0      {'bare:live': 117}
KXWCGAME-26JUN24SUICAN.jsonl     2026-06-24 n=166    score+min=0      {'bare:live': 166}
KXWCGAME-26JUN25ECUGER.jsonl     2026-06-25 n=208    score+min=0      {'bare:live': 208}
KXWCGAME-26JUN25JPNSWE.jsonl     2026-06-25 n=237    score+min=0      {'bare:live': 237}
KXWCGAME-26JUN25TUNNED.jsonl     2026-06-25 n=12     score+min=0      {'bare:live': 12}
KXWCGAME-26JUN25PARAUS.jsonl     2026-06-26 n=238    score+min=0      {'bare:live': 238}
KXWCGAME-26JUN26NORFRA.jsonl     2026-06-26 n=156    score+min=0      {'bare:live': 156}
KXWCGAME-26JUN26SENIRQ.jsonl     2026-06-26 n=105    score+min=0      {'bare:live': 105}
KXWCGAME-26JUN26CPVKSA.jsonl     2026-06-27 n=215    score+min=0      {'bare:live': 215}
KXWCGAME-26JUN26EGYIRI.jsonl     2026-06-27 n=223    score+min=0      {'bare:live': 223}
KXWCGAME-26JUN26NZLBEL.jsonl     2026-06-27 n=143    score+min=0      {'bare:live': 143}
KXWCGAME-26JUN26URUESP.jsonl     2026-06-27 n=210    score+min=0      {'bare:live': 210}
KXWCGAME-26JUN27CODUZB.jsonl     2026-06-27 n=187    score+min=60     {'bare:live': 116, 'kv': 71}
KXWCGAME-26JUN27COLPOR.jsonl     2026-06-27 n=212    score+min=84     {'bare:live': 117, 'kv': 95}
KXWCGAME-26JUN27CROGHA.jsonl     2026-06-27 n=207    score+min=0      {'bare:live': 207}
KXWCGAME-26JUN27PANENG.jsonl     2026-06-27 n=167    score+min=0      {'bare:live': 167}
KXWCGAME-26JUN27DZAAUT.jsonl     2026-06-28 n=156    score+min=109    {'kv': 156}
KXWCGAME-26JUN27JORARG.jsonl     2026-06-28 n=33     score+min=33     {'kv': 33}
KXWCGAME-26JUN28RSACAN.jsonl     2026-06-28 n=197    score+min=166    {'kv': 197}
KXWCGAME-26JUN29BRAJPN.jsonl     2026-06-29 n=224    score+min=171    {'kv': 224}
KXWCGAME-26JUN29GERPAR.jsonl     2026-06-29 n=89     score+min=89     {'kv': 89}
KXWCGAME-26JUN30CIVNOR.jsonl     2026-06-30 n=209    score+min=170    {'kv': 209}
KXWCGAME-26JUN30FRASWE.jsonl     2026-06-30 n=151    score+min=109    {'kv': 151}
KXWCGAME-26JUL01BELSEN.jsonl     2026-07-01 n=252    score+min=184    {'kv': 252}
KXWCGAME-26JUL01ENGCOD.jsonl     2026-07-01 n=255    score+min=201    {'kv': 255}
KXWCGAME-26JUN30MEXECU.jsonl     2026-07-01 n=176    score+min=128    {'kv': 176}
KXWCGAME-26JUL02ESPAUT.jsonl     2026-07-02 n=199    score+min=146    {'kv': 199}
KXWCGAME-26JUL02PORCRO.jsonl     2026-07-02 n=268    score+min=211    {'kv': 268}
KXWCGAME-26JUL02SUIDZA.jsonl     2026-07-03 n=207    score+min=157    {'kv': 207}
KXWCGAME-26JUL03ARGCPV.jsonl     2026-07-03 n=154    score+min=137    {'kv': 154}
KXWCGAME-26JUL03AUSEGY.jsonl     2026-07-03 n=267    score+min=203    {'kv': 267}
KXWCGAME-26JUL03COLGHA.jsonl     2026-07-04 n=217    score+min=166    {'kv': 217}
KXWCGAME-26JUL04CANMAR.jsonl     2026-07-04 n=110    score+min=110    {'kv': 110}
KXWCGAME-26JUL04PARFRA.jsonl     2026-07-04 n=94     score+min=94     {'kv': 94}
KXWCGAME-26JUL05BRANOR.jsonl     2026-07-05 n=105    score+min=105    {'kv': 105}
KXWCGAME-26JUL05MEXENG.jsonl     2026-07-06 n=92     score+min=92     {'kv': 92}
KXWCGAME-26JUL06PORESP.jsonl     2026-07-06 n=99     score+min=99     {'kv': 99}
KXWCGAME-26JUL07ARGEGY.jsonl     2026-07-07 n=115    score+min=115    {'kv': 115}
KXWCGAME-26JUL07SUICOL.jsonl     2026-07-07 n=108    score+min=108    {'kv': 108}
KXWCGAME-26JUL09FRAMAR.jsonl     2026-07-09 n=108    score+min=108    {'kv': 108}
KXWCGAME-26JUL10ESPBEL.jsonl     2026-07-10 n=140    score+min=140    {'kv': 140}
KXWCGAME-26JUL11NORENG.jsonl     2026-07-11 n=85     score+min=85     {'kv': 85}
KXWCGAME-26JUL11ARGSUI.jsonl     2026-07-12 n=78     score+min=78     {'kv': 78}
```

### The writer, and the exact line that emits "live"

The joined store never composes the string: `scripts/platformkit/ingame/ticker_settlement_join.py:198`
passes `state_summary` through verbatim from the raw capture. The raw capture's single writer is
`live_grade.capture_pair_once` (`scripts/platformkit/ingame/live_grade.py:173`), which calls:

```python
# scripts/platformkit/ingame/live_grade.py:189-200
def _state_summary(state: Dict[str, Any]) -> str:
    parts: List[str] = []
    for k in ("home_score", "away_score", "elapsed", "elapsed_minutes",
              "minute", "inning", "half", "clock", "period",
              "outs", "base", "bos", "re", "count", "pitch_count", "tto"):
        if state.get(k) not in (None, ""):
            parts.append("%s=%s" % (k, state.get(k)))
    return " ".join(parts) if parts else "live"          # <-- the bare string
```

`"live"` is emitted **only when the state dict carries none of those 16 keys** -- it is already
the honest empty-state fallback, never a substitute for state that exists. The property the row
asks for ("never a bare string when structured fields exist") therefore already holds by
construction, and always did. What was missing was the state dict, and both halves have since
been supplied for soccer:

- score: `ingame_live_state.py:369-372` aliases `home_goals`/`away_goals` to
  `home_score`/`away_score`, "so the captured state_summary carries real score (margin)
  instead of 'live'".
- minute + half: `ingame_live_state._segment_fields` (`ingame_live_state.py:307-318`) sets
  `minute` from `_soccer_minute(status)` and derives `half` from the 45-minute boundary.

Both landed before this lane; the on-disk cutover date (2026-06-27) is their signature.
**No code change to the writer was warranted (Q8: a falsified premise is a valid result).**
What this lane adds is the regression guard the row actually wanted:
`tests/platformkit/eval_gate/test_asof_join.py::test_soccer_state_summary_schema_never_bare_when_structured_fields_exist`
drives a synthetic ESPN status (period 1, shortDetail 45'+2') through `_segment_fields`
and `_state_summary` and asserts the emitted string carries `home_score=`, `away_score=` and
`minute=`, is not `"live"`, and that `_state_summary({})` is still `"live"`.

### The 22 legacy files: CLOSED AT LIMIT

Not rewritten, and not recoverable. Checked both stores that sit beside them:

- `data/cache/ingame_grade/soccer_intl/` (69 raw files, 9,183 rows) carries the SAME split:
  4,477 rows with `home_score=`, **4,649 rows bare `"live"`**, 57 `"FINAL"`. The raw capture
  beside a legacy joined file holds the bare string too -- the score was never captured, so
  it cannot be un-lost.
- `data/domains/soccer_intl/fotmob_backfill/` (38 files) is an xG/momentum reconstruction at
  coarse cutoff minutes (`cutoff_min`, `xg_home`, `sot_diff`, ...) with **no score field** and
  no per-tick grain; `fotmob_live/` holds only an `_archive` entry.
- `data/domains/soccer_intl/tick_segment_backfill.json` already recovers what IS recoverable
  from a bare tick -- an H1/H2 SEGMENT label derived from each tick's own capture timestamp
  minus the ESPN kickoff (`scripts/platformkit/ingame/tick_segment_backfill.py`, sidecar only,
  ticks inside the ~10-minute halftime uncertainty band excluded rather than guessed). A
  segment label is not a score.

Score at those ticks is therefore unavailable from any store on disk. Anything else would be
fabrication, and the 4,553-tick / 8-game soccer SCREEN side in S99 stays as small as it is.

## (b) The shared as-of helper

`scripts/platformkit/eval_gate/asof_join.py` (47 LOC), one function:

```python
asof_join_state(ticks, states, key="ts", max_staleness_s=300.0) -> (merged, stale_share)
```

Backward `merge_asof` on a numeric key, with state older than `max_staleness_s` nulled. The
join is run WITHOUT `tolerance=` only so the lag stays observable; the null set is then applied
by hand as `lag.isna() | (lag > max_staleness_s)`, which is byte-identical to what
`pd.merge_asof(tolerance=)` produces -- asserted directly in the test against a real
`pd.merge_asof(..., tolerance=300)` call on an 8-stamp frame. Ticks with no usable state are
nulled and passed on to the caller's own `dropna`, never guessed and never carried forward (B3).

**Why the helper exists rather than the one-line pandas argument:** `tolerance=` nulls in
silence. It tells a caller nothing about how much of its corpus it just dropped, which is how a
2-hour-stale score survived unnoticed in S99 until the Brier came out at 0.3234. The returned
`stale_share` is that number.

Test: `python -m pytest tests/platformkit/eval_gate/test_asof_join.py -q` -- **5 passed**.
Cases: fresh state survives (including a lag-0 exact match); a stale tick (3,000 s past the last
state -- the exact S99 defect) and an absent-state tick (before every state row) are both nulled,
`stale_share == 2/3`; the boundary is inclusive (lag 300 kept, lag 301 dropped) AND matches
`pd.merge_asof(tolerance=300)` on both the null pattern and the surviving values, for a float
column and an object column; an empty tick frame does not raise; plus the (a) schema test above.

### Wiring 1: `s99_corpus.py` -- behaviour-preserving, REPRODUCED

Both `pd.merge_asof(..., tolerance=STATE_TOLERANCE_S)` call sites (the MLB leg loop and the
soccer leg loop) now call `asof_join_state(frame, state, "ts", STATE_TOLERANCE_S)`.
`STATE_TOLERANCE_S = 300` is unchanged, and it is still the constant `s99_cross_market` imports
(Q3: no bar, threshold or tolerance moved). Additive only: two new meta keys per sport,
`n_ticks_asof_joined` and `stale_state_share`, beside the existing `dropped` counter (B2 --
nothing renamed or removed; `scripts/platformkit/eval_gate/s99_cross_market.py` is the only
reader of that meta and reads `dropped`, `tie_weight`, `crps_kmax`, `n_multi_market_games`,
`n_games_joined` by name).

Re-ran `s99_cross_market.run()` end to end (to a scratch out_dir, so the landed artifacts were
not clobbered). Every headline reproduces **exactly**:

| leg | this run | S99 memo |
|---|---|---|
| mlb moneyline | n=11,124 / 52g, model **0.201034** vs market 0.160624, delta -0.040410, CI [-0.069640, -0.011180] | identical |
| mlb total | n=79,791 / 50g, model 0.160422 vs 0.139822, delta -0.020601, CI [-0.035143, -0.006058] | identical |
| soccer moneyline | n=498 / 7g, 0.283741 vs 0.159716, delta -0.124025, CI [-0.257014, +0.008964] | identical |
| soccer team_total | n=4,055 / 8g, 0.164598 vs 0.147692, delta -0.016906, CI [-0.067538, +0.033727] | identical |
| corpus | mlb 85 joined / SCREEN 90,915 ticks / 52 games; soccer 47 joined, 25 with ticks / SCREEN 4,553 / 8 | identical |

**The number `tolerance=` was hiding:** of the ticks entering the as-of join,
**75.26 pct (mlb, of 607,224) and 92.80 pct (soccer, of 468,712) carry no usable state** --
stale past 300 s, or with no earlier state row at all. Three quarters of the MLB price series
and over nine tenths of the soccer one sit outside their own state capture. That is the real
shape of these corpora, and until now no artifact printed it. It is a data-coverage statement,
not a result.

### Wiring 2: `foundry/ingame_screen.py` -- PREMISE FALSIFIED, not wired

The S82 loader performs no as-of join, so there is no tolerance to preserve. `causal_source`
(`ingame_screen.py:66-72`) reads `state_summary` **inline off each tick**
(`t.get("state_summary") or t["raw"]["state_summary"]`); the ticks come from
`hedge_trial_arms.load_corpus`, which reads the joined jsonl directly and parses each row's own
state. The NBA sibling `ingame_screen_nba.load_screen` likewise reads `score_home` /
`score_away` / `elapsed` as columns of the S86 per-tick CSV. Neither ever joins a separate state
series onto a price series.

Wiring the helper in there would have ADDED a join where none exists -- a behaviour change, not
a behaviour-preserving refactor, and it would have needed a state series the tier does not have.
Not done, and reported rather than forced. The other real backward-`merge_asof` call sites in
the tree are named here for a future lane, and were left alone as outside this lane's file
ownership: `scripts/platformkit/venue_history/nba_wallclock_join.py:122` (NO tolerance -- the
same defect S99 hit, unguarded), `nba_checkpoints_full.py`, and
`scripts/platformkit/benchmarks/crps_market/state_lag_sensitivity.py:79` (which measures the lag
rather than capping it, and is the natural consumer of `stale_share`).

## Self-check against the contract

- **B1** no rows excluded before a metric; the stale share is reported over the FULL join denominator.
- **B2** additive only: two new meta keys, no rename, no removal; `STATE_TOLERANCE_S` still exported and unchanged; every reader of the touched meta grepped (A5).
- **B3** missing state is nulled and passed on, never quarantined; `"live"` stays the honest empty-state fallback.
- **B6** no module moved or retired; no orphan import.
- **B10 / Q3** no bar moved: S99's `BAR = 0.004`, `SEED = 0`, `MIN_GAMES = 30`, `STATE_TOLERANCE_S = 300` all byte-identical to master.
- **Q1 / Q2** nothing scored against a prereg, nothing charged; the FWER ledger was never opened.
- **Q6** calibration language only; none of the banned commercial-outcome vocabulary and none of the retracted figures appears.
- **Q7** `n = 51 (CONSTRUCT)` for the file census -- every file in the store enumerated, not sampled.
- **Q8** premise re-measured first; two sub-premises and one wiring target falsified, reported as results.
- **A2** the headline was recomputed by re-running the pipeline, not quoted.

## Files

- `scripts/platformkit/eval_gate/asof_join.py` (new, 47 LOC)
- `tests/platformkit/eval_gate/test_asof_join.py` (new, 5 passed)
- `scripts/platformkit/eval_gate/s99_corpus.py` (287 LOC, was 274 -- two call sites + two meta keys)
- `docs/evidence/harness/S104_soccer_state_asof_2026-09-03.md` (this memo)
