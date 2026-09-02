# S89 -- an in-game ARM family in the frozen FWER partition

Gap: `docs/evidence/HARNESS_GAPS_2026-09-03.md` row S89, from
`docs/evidence/harness/INGAME_GAP_PREMISES_2026-09-03.md` section L11.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections A, B, Q (Q1-Q9).
Calibration bookkeeping only. No dollar, ROI, profit or edge language; nothing is scored
here, so no prereg seal and no charge (Q1/Q2 not engaged -- this lane appends no ledger row).

## 0. Premise (Q8) -- CONFIRMED, not falsified

`load_families()` on the frozen spec at `spec_version: s14-families-v1`, pin
`62702554f6e57ec9f3182e8edc1e4d6a109a3b41`, returned **37** families:

```
mlb_atbat_states, mlb_bullpen_relief_chains, mlb_catcher_framing_index, mlb_gate,
mlb_inning, mlb_pitch_states, mlb_states, nba_boxdetail, nba_carryover,
nba_defender_rollup, nba_gate, nba_opp_allowed, nba_pbp_foul_states, nba_pbp_states,
nba_player_adv, nba_player_value_features, nba_possession_states, nba_quarter_shape,
nba_team_adv, soccer_cardstates, soccer_gate, soccer_referee_card_foul_profiles,
soccer_shotstates, soccer_shotxgstates, soccer_states, soccer_style_fingerprints,
soccer_xg_proxy, tennis_features, tennis_gate, tennis_hold, tennis_meta, tennis_return,
tennis_schedule_density, tennis_serve_return_profiles, tennis_setdetail, tennis_states,
tennis_travel_scouting
```

Eleven carry `(live_tick, inplay)` -- `mlb_atbat_states`, `mlb_pitch_states`, `mlb_states`,
`nba_pbp_foul_states`, `nba_pbp_states`, `nba_possession_states`, `soccer_cardstates`,
`soccer_shotstates`, `soccer_shotxgstates`, `soccer_states`, `tennis_states` -- and all
eleven are feature-column grids.

`data/cache/eval_gate/backtest_fwer.jsonl`, rows 14-18, read-only, `family` field:

| k_cumulative | family | k_family | predictor |
|---|---|---|---|
| 14 | (absent) | (absent) | `eval_gate.stacker:mlb_stack_v1` |
| 15 | `ingame_mlb_arms` | 1 | `eval_gate.s58_e2_slice_trial:mlb_e2_slice_v1` |
| 16 | `ingame_mlb_clamp` | 1 | `eval_gate.s58_clamp_family_trial:mlb_clamp_family_v1` |
| 17 | `ingame_nba_halftime_asof` | 1 | `eval_gate.s58_nba_halftime_asof_trial:nba_halftime_asof_v1` |
| 18 | `soccer_gate` | 1 | `foundry:d65df2a95aeb0f49` |

**None of `ingame_mlb_arms`, `ingame_mlb_clamp`, `ingame_nba_halftime_asof` is in the 37.**
Row 18's `soccer_gate` IS, which is the control showing the field is populated correctly.
Premise CONFIRMED; the row proceeds.

## 1. The two new frozen families

`ingame_arms_mlb` (mlb, live_tick, inplay, `kind: arm`, 10 members): `e2_gd`, `e4_gd`, and
the eight non-incumbent clamp configs `e4_w0.5_d0.10`, `e4_w1.0_d0.10`, `e4_w2.0_d0.10`,
`e4_w0.5_d0.15`, `e4_w2.0_d0.15`, `e4_w0.5_d0.25`, `e4_w1.0_d0.25`, `e4_w2.0_d0.25`.
`e4_gd` IS `CONFIGS[0] = (1.0, 0.15)`, the clamp incumbent, so it is listed once.

`ingame_arms_nba` (nba, live_tick, inplay, `kind: arm`, 1 member): `nba_halftime_asof`.

**No soccer arm family.** No soccer in-game arm exists: `scripts/platformkit/ingame/`
defines no soccer arm spec, `arm_registry.py` names no sport-specific soccer arm, and no
soccer in-game arm has ever been charged. A family frozen for a sport with no arm would be
a family invented after the fact, which is the thing the frozen partition exists to prevent.

An ARM is a whole scored predictor, so the 9-transform grammar does not apply to it:
`hypotheses = features` for an arm family, one hypothesis per arm. This is written into the
spec as a new construction rule and carried in code by an OPTIONAL `kind:` field
(`grid` by default), so all 37 original blocks stay byte-identical.

## 2. The pin (a deliberate frozen-list change)

| | old | new |
|---|---|---|
| `spec_version` | `s14-families-v1` | `s89-families-v2` |
| `git hash-object` pin | `62702554f6e57ec9f3182e8edc1e4d6a109a3b41` | `9d6cb98c43c74d04b7f995fe380e33705ffb7c0b` |
| families | 37 | 39 (37 grids + 2 arms) |
| features | 396 | 407 (396 grid + 11 arm) |
| hypotheses | 3564 | 3575 (3564 grid + 11 arm) |

Nothing was removed and **no bar moved** (Q3/B10): `q_within_family` is still 0.05,
`alpha_global` still 0.05, `deflated_p` / `eps_eff` / `min_corpora_eff` / cumulative K
untouched, every trial's `BAR = 0.004` untouched. The pin CHANGING is the tamper-evidence
mechanism working as designed -- a verdict stamped `s14-families-v1` @ `62702554f` remains
self-evidently priced against the old partition.

Condition (iii), no re-scoring, still holds by construction: `dual_bar_verdict` takes
p-values as arguments and opens no ledger and no stored verdict (asserted by
`test_verdict_reads_no_ledger_and_no_stored_result`). The three charged in-game verdicts
keep their `(NOT frozen; family of one)` labels in their own artifacts. They are NOT
re-scored under the new partition.

## 3. The mapping

`scripts/platformkit/eval_gate/family_bars.py`:

```
FAMILY_ALIASES = {"ingame_mlb_arms": "ingame_arms_mlb",
                  "ingame_mlb_clamp": "ingame_arms_mlb",
                  "ingame_nba_halftime_asof": "ingame_arms_nba"}
resolve_family(name)          # historical string -> frozen family
k_family(family, ledger_path) # READ-ONLY count over the charge ledger, aliases resolved
```

`FamiliesSpec.get` and `frozen_family` resolve through it, so a trial still declaring
`ingame_mlb_clamp` now prices inside a real frozen family instead of raising
`KeyError: family invented after the fact` / returning `NOT_IN_FROZEN_FAMILIES`.

**The ledger file is not modified.** `k_family` opens
`data/cache/eval_gate/backtest_fwer.jsonl` for reading only; the test asserts the file's
bytes are identical before and after the call. `_charge_ledger` was not called by this lane
and the file still has 18 rows.

## 4. Reader sweep (A5) and the one fall-through it caught

Every reader of the fields this diff touches: `foundry/tiers.py` (`frozen_family`,
`families_spec_sha`, `charged_bars`), `foundry/promotion_report.py`,
`foundry/screen_predictor.py`, `foundry/seed_queue.py`, and the three S58 trials. The
`families_of` filters in promotion_report and screen_predictor match on
`hypothesis.feature in f.members`, and an arm name is never a hypothesis feature, so they
are unaffected.

`seed_queue.frozen_hypotheses` was the fall-through (B2-shaped): it walks EVERY family's
members as columns x 9 transforms, so the two arm families would have leaked 99 spurious
feature hypotheses into the seed queue. Fixed at the source with the intrinsic `kind`
field rather than a name list: `if family.kind != "grid": continue`. Measured after the
fix: `sum(1 for _ in frozen_hypotheses()) == 3564`, unchanged.

## 5. Held: the ledger WRITE path

`ledger.next_k_family` (called only by `_charge_ledger`) still matches the family string
exactly, so a FUTURE charge naming `ingame_arms_mlb` would be written `k_family: 1` beside
an aliased history of 2. Both `eval_gate/ledger.py` and `eval_gate/backtest_runner.py` are
SHARED TOKEN modules (`docs/evidence/SHARED_MODULE_TOKEN.md`) and taking the token requires
a push, which this lane may not do. The patch is written out instead, count-not-max and
alias-resolving, at `docs/research/organization-sprint/PROPOSED-S89-next-k-family-alias.md`.
This does not block the S89 bar: the bar is that the family is frozen and the past charges
map into it for K accounting, and that accounting is a read, which landed.

## 6. Tests (per-file only)

`python -m pytest scripts/platformkit/eval_gate/test_family_bars.py -q` -> **12 passed**

- `test_frozen_spec_loads_and_pins_itself_into_every_verdict` -- UPDATED with the new
  numbers and a docstring recording the old pin. 39 families; the 37 grids still sum to
  396 features / 3564 hypotheses with `hypotheses == features * 9`; the 2 arms sum to 11
  features with `hypotheses == features`; `spec.prereg_sha256 == git_blob_id(SPEC_PATH)`,
  so an UNDECLARED spec edit still fails here.
- `test_historical_ingame_family_strings_resolve_into_the_frozen_arm_families` -- all three
  historical strings resolve; `spec.get` returns the arm family for each;
  `dual_bar_verdict(family="ingame_mlb_clamp")` prices without raising.
- `test_frozen_grammar_still_enumerates_only_the_37_grids` -- no arm member appears in
  `frozen_hypotheses()`.
- `test_k_family_counts_the_two_historical_mlb_arm_charges` -- **`k_family("ingame_arms_mlb")
  == 2`** (rows 15 and 16), `k_family("ingame_mlb_arms") == 2` through the alias,
  `k_family("ingame_arms_nba") == 1`, `k_family("nba_gate") == 0`, ledger bytes unchanged.
- `test_unknown_family_name_is_refused` unchanged and still passing: an alias resolves a
  KNOWN historical string, it does not make every string valid.

Regression, unchanged and re-run in master:
`tests/platformkit/foundry/test_tiers.py -q` -> 12 passed;
`tests/platformkit/combo/test_fwer_families_bh.py -q` -> 8 passed;
`tests/platformkit/foundry/test_grammar.py -q` -> 5 passed.

## 7. Files

- `docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md` (amended; new pin `9d6cb98c4`)
- `scripts/platformkit/eval_gate/family_bars.py` (300 LOC)
- `scripts/platformkit/eval_gate/test_family_bars.py`
- `scripts/platformkit/foundry/seed_queue.py`
- `docs/research/organization-sprint/PROPOSED-S89-next-k-family-alias.md`

## 8. Verdict

**ACCEPT.** Premise confirmed, two arm families frozen, three historical charges mapped,
ledger unmodified, no bar moved, no verdict re-scored. Q5 not engaged (no AHEAD claimed);
Q4/Q9 not engaged (nothing scored). S82/S86 preregs may now name a frozen in-game arm
family; a future in-game charge should read `k_family` for its K and, once the token is
free, land the held `next_k_family` patch.
