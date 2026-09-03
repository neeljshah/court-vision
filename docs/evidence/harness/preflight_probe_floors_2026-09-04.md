# S189 Preflight Probe Floors

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q.

## Premise and scope

Reproduced before the change: the live MLB corpus reported 27,983 rows and 10
columns. The seven functional probes were enumerated exhaustively in their
existing order. The pre-change assert census was 3 of 7 probes with an explicit
existence-shaped floor: `factory_sources`, `boot_packages`, and
`supervisor_lock_env`. The per-probe assert counts were 0, 0, 0, 1, 1, 0, and 2
in probe order.

`pod_bootstrap.sh` lines 64-65 report functional failures and continue booting.
This change therefore corrects functional-probe reporting only; it does not
change any boot decision.

## Assert census after the change

| Probe | Explicit existence-shaped floor | Counted toward 6 of 7 |
| --- | --- | --- |
| parquet_mlb_games | `len(df) > 0` | yes |
| mlb_predictor_init | `p.n_games > 0 and len(p.teams) > 0` | yes |
| produce_mlb_dry | `e.status == 'ok' and len(e.predictions) > 0` | yes |
| espn_live_state_mlb | type-only list assertion; fail-open BY DESIGN | no |
| factory_sources | required sources present | yes |
| boot_packages | required imports | yes |
| supervisor_lock_env | supervisor pid and required environment | yes |

The post-change construct census is 6 of 7. The named and only exclusion is
`espn_live_state_mlb`, because an empty live slate remains fail-open BY DESIGN.
The live corpus values above are reported observations, not thresholds.

## Degraded-input reproduction

The premise matrix was reproduced with the original real bodies through the
real `run_probe`; the corpus lookup was redirected in the child. For
`produce_mlb_dry`, the production warmup resolves through its refreshed-rating
path, so the corpus redirection does not alter that probe. Its unavailable
branch was instead forced in the child, as specified.

| Probe | Plant | Pre-change ok | Pre-change cause |
| --- | --- | --- | --- |
| parquet_mlb_games | zero-row schema-correct parquet | true | `rows=0 cols=10` |
| parquet_mlb_games | zero-row one-column parquet | true | `rows=0 cols=1` |
| parquet_mlb_games | absent parquet | false | FileNotFoundError |
| mlb_predictor_init | zero-row schema-correct parquet | false | IndexError |
| mlb_predictor_init | zero-row one-column parquet | false | KeyError |
| mlb_predictor_init | absent parquet | false | FileNotFoundError |
| produce_mlb_dry | zero-row schema-correct parquet | true | `status=ok` |
| produce_mlb_dry | zero-row one-column parquet | true | `status=ok` |
| produce_mlb_dry | forced unavailable branch | true | `status=unavailable predictions=0 markets=0` |

The new per-file construct test runs the post-change real bodies through
`run_probe`. Every post-change outcome below is `ok=false`; the JSON companion
stores both matrices in machine-readable form.

| Probe | Plant | ok | Cause class |
| --- | --- | --- | --- |
| parquet_mlb_games | zero-row schema-correct parquet | false | AssertionError |
| parquet_mlb_games | zero-row one-column parquet | false | AssertionError |
| parquet_mlb_games | absent parquet | false | FileNotFoundError |
| mlb_predictor_init | zero-row schema-correct parquet | false | IndexError |
| mlb_predictor_init | zero-row one-column parquet | false | KeyError |
| mlb_predictor_init | absent parquet | false | FileNotFoundError |
| produce_mlb_dry | forced unavailable branch | false | AssertionError |

## Not verified

- No pod, remote host, deployment, or boot action was run.
- The boot gate remains deliberately unchanged; this lane does not validate a
  changed boot outcome.
- The live corpus is not used as a threshold or as scored evidence.

ATTEMPT 2: Extracted the three existence-floored MLB probe bodies to `scripts/platformkit/ops/preflight_floors.py`; probe names, order, asserts, output, and reported-not-blocking boot behavior remain unchanged.
