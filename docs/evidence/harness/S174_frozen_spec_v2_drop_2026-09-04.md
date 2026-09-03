# S174 Frozen Family Spec v2 Drop

## Construct result

Verdict: ACCEPT. This is an additive frozen-spec construct, not a scored
comparison. It writes no charge, reads no corpus, and does not read or write the
18-row FWER ledger.

## Premise remeasurement

The frozen-family data loader is
`scripts/platformkit/eval_gate/family_bars.py:load_families`. Its normal current
path reads `FWER_FAMILIES_SPEC_2026-09-03.md` as ASCII and computes its pin with
`git hash-object`; it does not consult a corpus or ledger. Before this change the
current default was, and after this change remains, `s144-families-v4`, 41
families, pin `9e05a449ed313feb08dd54559d1e9328ed1dbbb7`.
The S174 construct test loads `master`'s pre-change `family_bars.py` side by
side and compares a canonical ASCII serialization of its default result with
the changed module's default result; the two byte strings are identical.

The sealed historical S14 v1 blob is
`62702554f6e57ec9f3182e8edc1e4d6a109a3b41`. Its raw SHA-256 is
`906501a6be7373a5223205ebc7252d2c48a8ed126f20b1f7e65b018789c5ee40`.
Parsing that exact blob gives N1 = 37 families and M1 = 396 members. The two
definitions are:

```text
fam: mlb_inning
sport: mlb
horizon: period
market: total
features: 6
members: home_early_rate_asof, away_early_rate_asof, early_rate_diff_asof, home_late_rate_asof, away_late_rate_asof, late_rate_diff_asof

fam: nba_quarter_shape
sport: nba
horizon: period
market: spread
features: 15
members: home_q1_margin_asof, away_q1_margin_asof, diff_q1_margin_asof, home_first_half_margin_asof, away_first_half_margin_asof, diff_first_half_margin_asof, home_second_half_margin_asof, away_second_half_margin_asof, diff_second_half_margin_asof, home_q4_margin_asof, away_q4_margin_asof, diff_q4_margin_asof, home_quarter_volatility_asof, away_quarter_volatility_asof, diff_quarter_volatility_asof
```

This confirms the S171 premise needed for the construct: the two records are
period-market families and contain 6 + 15 = 21 members.

## Additive versioned payload

`scripts/platformkit/eval_gate/frozen_family_versions.py` holds the historical
v1 pin, the raw-blob SHA-256 check, and the sole v2 overlay. The default
`load_families()` code path is unchanged in behavior. Explicit
`version="s14-families-v1"` loads the exact historical blob. Explicit
`version="s14-families-v2"` returns 35 active records. Adding `dropped=True`
returns all 37 historical records, including exactly these two additions:

```text
mlb_inning: status DROPPED; reason no period market in any local store (S171 2026-09-04)
nba_quarter_shape: status DROPPED; reason no period market in any local store (S171 2026-09-04)
```

No v1 record is deleted or rewritten. The canonical v2 payload contains all 37
v1 records in their original order and adds `status` and `reason` only to these
two records. Its SHA-256 pin is
`df461f2744a8d6754f7ef643e79abf2ecefeee0614599f64b7c7f42714114ae1`.

Measured acceptance values: v1 pin unchanged; v2 dropped families = 2; v2
dropped members = 21; v2 active families = N1 - 2 = 35.

## Reader sweep

Direct production importers of `load_families` are
`promotion_report.py`, `run_ingame_screen.py`, `screen_predictor_supply.py`,
`seed_queue.py`, and `factory_source_manifest.py`. Each retains its no-argument
call site. `tiers.py` and `charge_path_followups.py` consume the default through
`families_spec_sha`; `backtest_runner.py` has no `load_families` importer. The
default-owning module retains no-argument internal calls in `dual_bar_verdict`,
`frozen_family`, `families_spec_sha`, and `charged_bars`.

`git diff master --` over every production reader above, plus `tiers.py` and
`backtest_runner.py`, is empty. The only direct-import additions are the new
S174 construct test and the additive version data module. No reader, runner,
tier, family-bar, or frozen seed-queue call site opts in; no flag changes state.

## Verification

Per-file commands only:

```text
python -m pytest tests/platformkit/foundry/test_s174_frozen_spec_v2.py -q
2 passed

python -m pytest scripts/platformkit/eval_gate/test_family_bars.py -q
19 passed, 3 skipped

python -m pytest tests/platformkit/foundry/test_tiers.py -q
12 passed
```

The existing `test_ingame_grammar_nba_pairs.py` was also run alone. Its two
frozen-spec tests passed; its corpus-dependent causality test failed before
S174 code because this worktree lacks
`data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv`. No data was created,
copied, or modified to bypass that absence.

Q1, Q2, Q4, Q5, and Q9 do not apply: no comparison was scored, no ledger charge
was made, and no corpus or differential exists. Q3/B10 hold: no bar, threshold,
or ledger field changed. Q6 holds: calibration language only. Q7 applies as an
exhaustive construct: all 37 v1 records were enumerated. Q8 holds because the
historical blob and both target definitions were remeasured before the change.

NOT VERIFIED: no production reader has opted into v2, and no local period market
has become available. That is intentional; the default remains pinned to its
pre-existing current behavior until a later explicitly authorized reader change.
