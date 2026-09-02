# S03 tennis close join -- CLOSED AT LIMIT (code lands; both bars unmeetable)

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Attempt 2 (attempt 1 stopped at the premise before writing code).
Calibration evidence only -- no dollar, ROI, profit or edge claim anywhere here.

S34 label: every artifact this pass writes carries `vintage: SYNTHETIC`.
`coverage_report("tennis")` returns `"vintage": "SYNTHETIC"` at top level and
every state from `gate_corpus_states` carries the same key, because no real odds
timestamp exists yet -- `state_ts` is constructed as `<game_date>T12:00:00`.

## Verdict

CLOSED AT LIMIT. The bar (`ATP >= 84.4 pct AND WTA >= 71.2 pct`) was derived
from a raw `event_id` merge whose numerator double-counts. It is not reachable
by any one-to-one join, so it is reported unmeetable and NOT lowered (Q3).
The module, the tennis `JoinSpec`, the leak guard, the S34 label and the S35
denominator fix all land as the honest measurement instrument.

## Step 0 -- premise (Q8), reproduced exactly

```text
python -c "<raw event_id merge, printed per tour>"
ODDS_ROWS 33952
ROW0 b365w=2.62 b365l=1.44 b365_p1=1.44 b365_p2=2.62 ps_p1=1.53 ps_p2=2.67 psw=2.67 psl=1.53
ORIENTATION b365w == b365_p2 -> True ; b365l == b365_p1 -> True
ATP SPINE 30616 MERGE_ROWS 25898
WTA SPINE 11270 MERGE_ROWS 8054
```

Both stated premise counts reproduce to the row: ATP 25,898 / 30,616 and WTA
8,054 / 11,270. The row-0 winner/loser orientation reproduces exactly as stated,
confirming that `b365w`/`b365l` are outcome-oriented and LEAKY beside the
de-leaked `b365_p1`/`b365_p2`.

## Step 1 -- the limit, and why 25,898 is not a numerator

`data/domains/tennis/odds.parquet` holds 33,952 rows but only 33,859 distinct
`event_id`s: 93 ids appear twice (186 rows). The pairs are DIFFERENT real
matches -- e.g. `20150104-atp-2015-339-105449-105453-20` appears as Brisbane
International 2nd Round on 2015-01-07 and as Australian Open 3rd Round on
2015-01-24 -- collapsed onto one id by the id construction. Each spine holds one
row for such an id, so the raw merge emits two output rows for one spine row.
25,898 and 8,054 are merge-row counts, not counts of joined spine rows.

| numerator rule | ATP joined / 30,616 | ATP pct | WTA joined / 11,270 | WTA pct |
|---|---:|---:|---:|---:|
| raw merge rows (the stated premise) | 25,898 | 84.5898 | 8,054 | 71.4641 |
| distinct spine rows, odds kept-first | 25,831 | 84.3709 | 8,028 | 71.2334 |
| distinct spine rows, ambiguous ids dropped (SHIPPED) | 25,764 | 84.1521 | 8,002 | 71.0027 |

The shipped rule drops both sides of an ambiguous id and counts them
(`ambiguous_event_id_drop_count: 186`). Keeping one arbitrarily would attach the
wrong match's prices to a scored spine row, i.e. mislabel it; dropping is the
honest choice. Under the shipped rule ATP is 84.1521 pct (bar 84.4) and WTA is
71.0027 pct (bar 71.2): BOTH bars are missed, so this is CLOSED AT LIMIT.
Even the most generous one-to-one rule (kept-first) misses the ATP bar.
`>= 95 pct` is not a bar here and does not appear as one.

## Step 2 -- what landed in `scripts/platformkit/eval_gate/close_join.py`

Additive only. S02's soccer `JoinSpec`, its measured rate, `close_column`'s
existing signature and every landed name are unchanged; `JoinSpec` gained two
optional fields with empty defaults (`price_suffixes`, `spine_files`).

- Tennis `JoinSpec`: `ps_p1`/`ps_p2` with fallback `b365_p1`/`b365_p2`.
- HARD RULE in `close_column` (`_check_orientation`): a column ending `_w`/`_l`
  raises `ValueError` for every sport; where a spec declares `price_suffixes`
  the bare bookmaker winner/loser form (`psw`, `b365l`) raises the same leak
  error, and any other column that does not end `_p1`/`_p2` also raises.
- Spine-first join for tennis: the FULL 41,886-row gate corpus is the spine and
  odds are joined ONTO it, so unjoined rows and price drops stay in the
  denominator. ATP and WTA remain two `corpus_unit`s and are never pooled into
  one rate, one Brier or one denominator.
- S35 fix: `by_corpus_unit` now groups the FULL joined frame, not
  `joined.loc[matched]`. It additionally raises if any per-unit `join_rate` is
  exactly 1.0 while `unjoined > 0`. Soccer is unaffected (soccer `unjoined` = 0,
  so its per-unit denominators and 1.0 rates are unchanged and honest).
- S34 fix: `vintage: SYNTHETIC` on the coverage report and on every state.

## `coverage_report("tennis")` -- headline

```text
denominator 41886 | joined 33766 | unjoined 8120 | join_rate 0.806140476531538
vintage SYNTHETIC
bad_price_drop_count 6 | null_close_count 75 | valid_close_count 33685
ambiguous_event_id_drop_count 186 | scored 33685
brier_devig_close 0.19736835157376564 | brier_p_base 0.21620174524743463
```

## Per `corpus_unit` (never pooled; denominator = the full spine)

| unit | denominator | joined | join_rate pct | bar | scored | Brier devig close | Brier p_base (corpus baseline) |
|---|---:|---:|---:|---:|---:|---:|---:|
| ATP | 30,616 | 25,764 | 84.1521 | 84.4 MISSED | 25,693 | 0.198557 | 0.216358 |
| WTA | 11,270 | 8,002 | 71.0027 | 71.2 MISSED | 7,992 | 0.193546 | 0.215699 |

The devigged close beats the corpus baseline column `p_base` on BOTH units
(ATP 0.198557 < 0.216358; WTA 0.193546 < 0.215699), so the self-REJECT on the
Brier condition does not fire. This is a calibration comparison only.

## Per year (both units pooled by year only; unit rates above are never pooled)

| year | denominator | joined | join_rate pct | scored | Brier devig close | Brier p_base |
|---|---:|---:|---:|---:|---:|---:|
| 2015 | 3893 | 3164 | 81.2741 | 3157 | 0.183581 | 0.217036 |
| 2016 | 3849 | 2946 | 76.5394 | 2943 | 0.188440 | 0.209714 |
| 2017 | 4062 | 3155 | 77.6711 | 3148 | 0.200036 | 0.216386 |
| 2018 | 4175 | 3358 | 80.4311 | 3347 | 0.203350 | 0.221628 |
| 2019 | 3811 | 3123 | 81.9470 | 3114 | 0.200542 | 0.216900 |
| 2020 | 2033 | 1533 | 75.4058 | 1527 | 0.193361 | 0.216018 |
| 2021 | 3434 | 2872 | 83.6342 | 2866 | 0.199619 | 0.215065 |
| 2022 | 3665 | 2960 | 80.7640 | 2951 | 0.197267 | 0.212659 |
| 2023 | 4235 | 3433 | 81.0626 | 3430 | 0.199433 | 0.218929 |
| 2024 | 4464 | 3638 | 81.4964 | 3631 | 0.198121 | 0.217105 |
| 2025 | 4265 | 3584 | 84.0328 | 3571 | 0.203432 | 0.215334 |

Year denominators sum to 41,886 and unit denominators sum to 41,886 (asserted in
the test). 2020 is short because the tour calendar was short that year.

## Drop accounting (nothing removed from a denominator)

41,886 spine rows = 33,766 joined + 8,120 with no odds row. Of the joined,
33,685 carry a usable devigged close; 75 have both `ps_*` and `b365_*` null and
6 carry a price <= 1.0 (dropped BEFORE `devig2`, which fails open to (0.5, 0.5)).
186 odds rows across 93 ambiguous ids never enter the join at all and are
counted separately. Every one of these rows remains in the 41,886 denominator.

## Commands

```text
python -m pytest scripts/platformkit/eval_gate/test_close_join_tennis.py -q
5 passed in 2.43s
python -m pytest scripts/platformkit/eval_gate/test_close_join_soccer.py -q
4 passed in 1.97s
python -c "from scripts.platformkit.eval_gate.close_join import coverage_report; import json; print(json.dumps(coverage_report('tennis'), indent=2, sort_keys=True))"
```

Soccer regression check: `coverage_report("soccer")` still reports denominator
16,322, joined 16,322, join_rate 1.0, brier_devig_close 0.23946005675766663,
brier_p_base 0.2627028248079339 -- byte-identical to the S02 landing. The only
change to the soccer output is ADDED keys (`vintage`, per-block `scored` and the
two per-block Brier values); no key was renamed or removed (B2).

## NOT VERIFIED

- The two Brier columns are unweighted in-sample calibration comparisons on the
  joined rows. They are NOT walk-forward, NOT purged/embargoed, and no CPCV ran
  (Q4). No AHEAD is claimed and no prereg was sealed (Q1), no ledger row was
  charged (Q2) -- this is corpus infrastructure, not a scored trial.
- `vintage: SYNTHETIC` means the close carries no real timestamp; the states are
  NOT proven pre-match-vintage and must not be used for a timing claim (S34).
- The 8,120 unjoined spine rows were not characterised beyond their year and
  unit; whether they are missing-at-random is unmeasured.
- The 93 ambiguous `event_id`s are a defect in the tennis id construction
  upstream of this module; it was diagnosed, not fixed.
- `gate_corpus_states("tennis", ...)` was exercised on 2015 only (3,157 states);
  no walk-forward was run over tennis states.
- No pod deploy, no `data/registry/` write, no FWER ledger write, no flag flip.

## Contract self-check

- B1 no row excluded from a reported metric -- unjoined, bad-price, null-close
  and ambiguous-id rows are all named and counted inside the 41,886 denominator.
- B2 additive only: two defaulted `JoinSpec` fields, added report keys, no
  rename or removal; the only importers are the two test files (grepped).
- B3 a missing odds row falls through as unjoined, never quarantined.
- B4/B5 no failure path and no deploy. B6 no module moved.
- B7 the metric is the full corpus, not a head slice. B8 no self-fit.
- B9 denominators are the two full spines, 30,616 and 11,270, not recycled units.
- B10 no threshold moved; the missed bars are reported at their spec values.
- Q1/Q2 no prereg, no scored trial, no ledger charge. Q3 bars not lowered.
- Q4/Q5 no OOS or AHEAD claim. Q6 calibration language only; none of the
  retracted figures appears. Q7 reproduction, not sampling. Q8 premise
  re-measured first and reproduced exactly.
