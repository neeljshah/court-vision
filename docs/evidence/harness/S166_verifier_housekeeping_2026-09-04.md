# S166 verifier housekeeping (2026-09-04)

Spec: `docs/evidence/tracking/specs/S166_spec.md`. Contract self-check: sections
B and Q. This is a four-item CONSTRUCT fix (`n = 4`); reproduction replaces an
eye check. The register, FWER ledger, thresholds, and `data/` were not changed.

## Premise re-check

All four findings were present before the edit:

- S36 repro stale assertion path: `E4 tick_date: AssertionError raised as expected`.
- S36 section 2 lists historical default values 0.207032929516776 and
  0.252261297271879.
- S90 source default: `OUT_DIR = REPO / "data" / "cache" / "eval_gate"`.
- Baseline-lock fallback: `{"n_games": 0, "n_eff": 0.0}`.

## Before / after

| item | before quote | after quote | status |
|---|---|---|---|
| (a) S36 tick-date repro | `except AssertionError as exc:` | `assert tick_leak_pct == 52.86` | FIXED |
| (b) S36 current defaults | `e4_blend ... 0.207032929516776` and `e2_regime ... 0.252261297271879` | `current tick_date results are e4 0.206629024102877 and e2 0.251859443230625` | FIXED |
| (c) S90 scratch output | `python -m scripts.platformkit.ingame.s90_microstructure_screen` | `python -m scripts.platformkit.ingame.s90_microstructure_screen --out-dir <scratch>` | FIXED |
| (d) empty-pair ESS shape | `{"n_games": 0, "n_eff": 0.0}` | `{"n_games": 0, "n_eff": 0.0, "n_eff_bound_ok": True}` | FIXED |

## Reproduction

S36 is run with `PYTHONPATH` set to the repository and stdout/stderr directed to
a caller-created system-temp scratch directory. It must print e4
0.206785778212713, e2 0.254350980569173, and e4 `self_leak_pct=52.86`.
Observed scratch output:

```
E4 game_first_date: n_ticks=47104 n_games=158 brier=0.206785778212713 leak_pct=0.00 (assert enforced)
E4 tick_date: n_ticks=47292 brier=0.206629024102877 self_leak_pct=52.86 (count asserted)
E2 game_first_date: n_ticks=6579 brier=0.254350980569173 leak_pct=0.00 (assert enforced)
E2 tick_date: n_ticks=6593 brier=0.251859443230625 self_leak_pct=43.49 (count asserted)
```

Focused construct tests:

- `python -m pytest tests/platformkit/ingame/test_s166_verifier_housekeeping.py -q`
- `python -m pytest scripts/platformkit/ingame/test_ingame_baseline_lock.py -q`

Results: 1 passed and 3 passed, respectively.

## NOT VERIFIED

- No model, threshold, Brier computation, or calibration decision was changed.
- S90 was not rerun because this correction changes only its documented caller
  output path; the memo command now requires a scratch directory.
- No additional corpus or scored comparison applies to this CONSTRUCT row.

## Contract self-check

- B1-B10: no metric denominator, schema removal, gate, claim path, deployment,
  module location, render sample, independent score claim, denominator, or bar changed.
- Q1-Q6 and Q9: no charged or scored comparison was added. Calibration language only.
- Q7-Q8: all four enumerated construct items are reported; the premise was read before edits.
