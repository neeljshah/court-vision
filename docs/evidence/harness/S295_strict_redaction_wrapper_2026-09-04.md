# S295 Strict Redaction Wrapper

## Result

ACCEPT: all six fixed callback attacks were rejected before scoring, and both valid shared-evaluator replays have error at most 1e-12.

## Preregistration

- Path: `docs\evidence\harness\S295_strict_redaction_wrapper_prereg_2026-09-04.md`
- Seal SHA-256: `6e4a9b70c8425d661678c1d3620cc6d7346a511313d943e2be4ec7d7d1478e75`
- Sign convention: improvement = baseline loss minus candidate loss; positive = candidate better.

## Premise binding

Default `strict_redaction` was false. The planted closure was readable and produced Brier 0.000000000000 versus 0.562500000000 for the declared-feature fixture over 8 scored evaluator states.

## Metric table

| Metric | Result | 95 percent CI |
|---|---:|---|
| Planted leak detections | 6/6 | [0.609665712098, 1.000000000000] |
| walk_forward valid replay error | 0.000000000000 | n/a; RSS before/after 149942272/149508096 bytes |
| cpcv_evaluate valid replay error | 0.000000000000 | n/a; RSS before/after 150179840/150220800 bytes |

## Durability and reproduction

The JSON beside this memo archives the generated raw construct, declared evaluator payload basis, all rejection exceptions, every evaluator record, stable tick key, and per-record loss. Each game has two distinct state timestamps; records are keyed per tick, not per game.

- Test: `python -m pytest scripts/platformkit/eval_gate/test_s295_strict_redaction_wrapper.py -q`

## NOT VERIFIED

- No external corpus, pod execution, deployment, or live caller migration was exercised.
- No calibration-ahead claim is made; the frozen +0.004 bar was not evaluated by this security construct.
