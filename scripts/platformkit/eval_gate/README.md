# eval_gate

The validation gate that decides whether a candidate signal or calibration
ships or gets rejected. It is built to refute: every module here exists to
find the reason a result is wrong (a leak, an underpowered sample, a stat
that ignores game-clustering) before that result is ever called a win.

## Start here

| Module | What it does | Covered by |
|---|---|---|
| `walkforward.py` | Leak-free walk-forward splitter: expanding window, purge, embargo, vintage check | `test_walkforward.py` |
| `dm_test.py` | Game-clustered Diebold-Mariano test, model loss vs the devigged close | `test_eval_core.py` |
| `shin.py` | Shin (1992) devig solver -- fair probabilities that sum to 1 | `test_shin.py` |
| `scoring.py` | Proper scoring: Brier, BSS, log-loss, ECE, resolution, sharpness | `test_eval_core.py` |
| `schema.py` | Golden-state schema + leak-guard validator (feature must predate prediction time) | `test_leak_contract.py` |
| `false_discovery.py` | Nightly Bonferroni/FDR survivor accounting across screens | `test_false_discovery.py` |
| `romano_wolf.py` | Game-clustered Romano-Wolf stepdown, multiple-testing control | `test_romano_wolf.py` |
| `ledger.py` | Append-only prediction ledger + calibration-drift monitor | `test_ledger.py` |
| `run_gate.py` | End-to-end CLI: golden fixture -> walk-forward -> score -> SHIP/REJECT scoreboard | `test_gate.py` |

## Running the tests

Per-file only -- never run pytest on the whole directory (see repo-root rules).

```
python -m pytest scripts/platformkit/eval_gate/test_eval_core.py -q      # 17 passed
python -m pytest scripts/platformkit/eval_gate/test_walkforward.py -q    # 8 passed
python -m pytest scripts/platformkit/eval_gate/test_shin.py -q           # 7 passed
```

## The `s###_*.py` files

Files named `s100_*.py`, `s205_*.py`, etc. are dated harness rows -- one file
per numbered signal/spec investigation, run once and kept as the record of
what was tried and what it found. They are not a library to import from; the
narrative for each one (what was tested, the verdict, why) lives in
`docs/evidence/harness/*.md`. Treat them as an audit trail, not an API.

## Rails

This folder reports calibration quality only: Brier/BSS/ECE/log-loss against
the devigged market close. No edge, ROI, or dollar-profit claims are made or
implied anywhere in this directory. A handful of historical figures were
retracted as measurement artifacts (leak-inflated or single-fold); they never
appear here as current results, only inside explicit retraction framing. See
the ground rules at the top of `EVIDENCE.md`. Anything importing from `src/` or reading
`data/` needs the private tree (`court-vision-private`) -- it will not run
from this public clone alone.
