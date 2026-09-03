# S78 -- the pod factory's DATA sources are enumerated, checked and shippable

Date 2026-09-03 | area ops | register row S78 (docs/evidence/HARNESS_GAPS_2026-09-03.md)
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B and Q (self-checked).
Calibration language only. A SCREEN is a NON-FINDING; nothing here is a $ or edge claim.

## STEP 0 -- PREMISE (re-measured at HEAD a4e42133b, NOT falsified) + the enumeration

The row rests on one fact: `pod_bootstrap.sh` ships the TRACKED TREE (`git archive HEAD
scripts/platformkit supervisor predict_service domains config`), while every source the real
screen predictor reads lives under `data/`, which is gitignored. Read on disk before any edit:

- `scripts/platformkit/ops/pod_bootstrap.sh:15-18` -- the deploy is `git archive` piped into
  `tar -x`; `:53` "tree: shipped by the caller". No data path anywhere in the file.
- `scripts/platformkit/ops/pod_bootstrap_check.py:68-116` -- six functional probes, none of which
  looks at a factory source (`parquet_mlb_games` reads the MLB predictor's own corpus only).
- `.gitignore` -- `data/` is untracked in full, so `git archive` can never carry any of it.

PREMISE HOLDS. The hand-shipped set of 2026-09-03 (S75 memo, "Verifier pod step": 127 top-level
parquet, 76 MB, + the 4 S68 corpora and sidecars) was undocumented beyond that memo.

### Every source the pod factory reads today

Enumerated by `factory_source_manifest.required()` -- **386 paths, 227.1 MB local**, all under
`data/` and therefore ALL GITIGNORED except three tracked `scripts/platformkit/eval_gate/s58_*.py`
trial modules the FWER families spec names as sources. Derived from the registries, not typed out:

| origin group | paths | what it is |
|---|---:|---|
| `corpus` | 12 | `gate_corpus_{mlb,nba,soccer,tennis}.{parquet,sources.json}` + `gate_corpus_{nba,mlb}_close.*` |
| `sidecar` | 22 | every source those 6 sidecars RECORDED, resolved through `corpus_cache._resolve_source` |
| `asof_supply` | 22 | `REGISTRY[*].source` (comma lists + globs expanded) + `season_table` |
| `catalogue` | 37 | `foundry.catalogue.NAMED` |
| `catalogue-glob` | 42 | `catalogue.GLOBS` members (`data/cache/pit/opp_allowed_asof_*`, `data/cache/ingame/*states*`) |
| `families` | 74 | `family_bars.load_families().families[*].sources` (31 of them pregame-horizon) |
| `close_join` | 5 | soccer `odds`+`matches`; tennis `odds`+`matches`+`wta_matches` (from `_SPECS`) |
| `close_join_close` | 5 | `close_join_nba_mlb.SOURCES` -- the close-corpus BUILDERS' inputs |
| `screen_predictor._teams` | 3 | `basketball_nba/games`, `mlb/games`, `mlb/games_current` -- **the only hardcode** |
| `ingame` | 280 | `ingame_screen_nba.S86_CSV`, `ingame_supply_mlb.SERIES`/`JOINED/*.jsonl`, `ingame_screen_soccer.STORE/*.jsonl` |

Groups overlap (a path is listed under every origin that names it), so the group counts sum above
386. One named path is absent on this box and on the pod: `data/domains/soccer/
asof_discipline_features.parquet` (`catalogue` only -- `catalogue.absent()` already names it, and
no family or bridge entry reads it).

## CHANGE (additive, 1 new module + 1 probe + 1 runbook line)

`scripts/platformkit/ops/factory_source_manifest.py`, 298 LOC (rail 300), stdlib + the repo's own
registries. Nothing under `src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/` was read for
writing; `data/registry/` untouched; no flag flipped ON; no `--force` anywhere.

- `required(ingame=True)` -- the manifest above, `{path: [origins]}`, IMPORTED from
  `corpus_cache`, `asof_supply`, `catalogue`, `family_bars`, `close_join*` and the three in-game
  modules' own path constants. The single hardcode is `_TEAMS_GAMES`, because
  `screen_predictor._teams` builds its three paths inline inside the function; it is named as
  HARDCODED in the docstring and in the origin label itself.
- `on_pod_path(origins)` / `required(ingame=False)` -- the 61-path, 96.6 MB subset the pod's boot
  gate asserts, which is S78's bar verbatim ("every source the sidecars + screen_predictor name").
  Enumerated but NOT gated, with the reason recorded in the function's docstring: `ingame:*` and
  non-pregame families' tick stores (no pod pass reads them -- `foundry_runner` screens T0/T1
  through `screen_predictor.corpus_states`, the pregame path only), `catalogue`/`catalogue-glob`
  (`catalogue.absent()` explicitly permits a NAMED path to be absent, and everything a screen
  actually reads also arrives via `asof_supply` / `families` / the sidecars).
- Digest is **SHA-256 over the whole file** (not mtime -- 227 MB hashes in about a second), with
  size beside it.
- `--check-pod` -- ONE read-only `ssh ... 'cd /workspace/nba-ai-system && xargs -d "\n" -r
  sha256sum'` batch, path list on stdin; prints OK / DIFFERS / MISSING.
- `--ship` -- PRINTS (never runs) the exact `printf | tar -czf - -T - | ssh ... tar -xzf -`
  command for the non-OK set.
- `--verify-local` -- exits nonzero when a required source is absent on THIS host; this is what
  the pod-side probe uses.

`pod_bootstrap_check.py` gains a seventh `--functional` probe, `factory_sources`, which calls
`missing_local(required(ingame=False))` and asserts it empty, so `--functional` exits nonzero when
a required source is missing on the pod (`run_functional` counts the FAIL, `main` returns 1).
It is deliberately wired to the NON-BLOCKING functional call in `pod_bootstrap.sh` step 3, not to
the blocking import gate -- a restart still boots and reports, rather than refusing to boot.

`docs/operations/runpod-runbook.md` -- one new step 7 in "After a CONTAINER RESTART".

### One landmine found while building it (fail-open, fixed)

The first real `--check-pod` reported **60 of 61 MISSING** -- and it was wrong. `subprocess.run(...,
text=True)` newline-translates the stdin write on Windows, so the pod received every path but the
last with a trailing CR and `sha256sum` found nothing. A broken transport read EXACTLY like the
real finding. Fixed by sending bytes, and `pod_digests` now RAISES on empty stdout rather than
reporting phantom MISSINGs (`sha256sum` exits nonzero on any absent file, so the return code alone
cannot separate the two). Test `test_pod_digests_refuses_an_empty_transport` pins it.

## MEASURED -- `--check-pod` run for real (2026-09-03, read-only, no write on the pod)

Boot-gate set, `--pod-path-only --check-pod`:

| verdict | n | paths |
|---|---:|---|
| OK | 58 | -- |
| DIFFERS | 0 | -- |
| MISSING | 3 | `data/cache/inplay_odds/mlb_price_series.parquet`, `data/cache/inplay_odds/nba_checkpoints_full.parquet`, `data/cache/venue_history/nba_close_corpus.parquet` |

Local side: 61 present, 0 absent, 96.6 MB. The three MISSING are named ONLY by
`sidecar:{nba,mlb}_close` and `close_join_close:*` -- they are the inputs the CLOSE-corpus
builders read, and the pod runs with `FOUNDRY_PORTABLE_CORPUS=1`, which verifies a corpus against
its sidecar's `corpus_sha256` instead of reading its sources. So the pod does not read them today;
the gate names them because the sidecars do, and the bar is NOT lowered to hide them (Q3). They
are ~50 MB and this lane is read-only on the pod, so they were NOT shipped -- the printed ship
command is in the memo's own record below and the runbook step tells the next operator to run it.

Full 386-path set, `--check-pod`: **OK 287 / DIFFERS 56 / MISSING 42**. Read honestly:

- 38 of the 42 MISSING are `data/cache/ingame/*states*.parquet`, one more is
  `data/cache/eval_gate/s82_ingame_screen_series_2026-09-03.csv`, and the last 3 are the close
  builders' inputs above. The 39 in-game stores are read by no pod pass -- not a defect, not
  gated. (`s86_nba_every_tick_2026-09-03.csv` IS on the pod, byte-identical: the S126 re-run
  shipped it.)
- 53 of the 56 DIFFERS are `data/cache/ingame_grade_joined/**.jsonl`, which the POD WRITES (it is
  the paper node). DIFFERS there means the LOCAL copy is behind, never a pod defect, and is never
  a reason to ship. Recorded in `_ingame`'s docstring so it cannot be misread later.
- The other 3 DIFFERS are the tracked `scripts/platformkit/eval_gate/s58_*_trial.py` modules: the
  pod's deployed tree is behind master on files no pod pass executes.

Ship command as printed (NOT run by this lane):

```
printf '%s\n' \
  data/cache/inplay_odds/mlb_price_series.parquet \
  data/cache/inplay_odds/nba_checkpoints_full.parquet \
  data/cache/venue_history/nba_close_corpus.parquet \
  | tar -czf - -T - \
  | ssh -o BatchMode=yes -F ~/.ssh/config.pod pod 'tar -xzf - -C /workspace/nba-ai-system'
```

## TESTS (per-file only)

- `tests/platformkit/ops/test_factory_source_manifest.py` -- **5 passed** (new). The manifest is
  asserted to CONTAIN every `asof_supply.REGISTRY` source, every `catalogue.NAMED` path, all four
  corpora + sidecars + a `_close` corpus, the close_join spines and the three `_teams` tables, so
  a hardcoded list could not pass it; plus the MISSING / DIFFERS / OK classification on a
  synthetic listing, the pod-path subset rule, the ship command, and the empty-transport raise.
- `tests/platformkit/ops/test_pod_bootstrap_check.py` -- **4 passed** (A5 reader: its probe-set
  assertion pinned six names and now pins seven; no other reader of `_FUNCTIONAL_PROBES` exists
  in the repo).
- The new probe run locally through `run_probe`: `True  factory sources present: 61/61`.

## Rails self-check (section Q)

Uncharged: no ledger touched -- `data/cache/eval_gate/backtest_fwer.jsonl` was never opened and is
not read by any code path added here (18 rows; it must never exist on the pod, and `--check-pod`
never lists it). No screen run, no metric scored, so Q1/Q2/Q4/Q5 do not bind. Q3: no bar moved --
the gate set IS the row's stated bar, and the three MISSING are reported rather than excluded.
Q6: calibration language only, no retracted figure appears. `data/registry/` untouched, no flag
flipped ON, no `--force`, no `git add -A`, no push. Pod contact was READ-ONLY (one `sha256sum`
batch and one two-path debug read); nothing was killed, restarted or written there.

## NOT VERIFIED

- Lane's own report; no independent verifier has re-run it.
- The probe has not been executed ON the pod (that needs a deploy of the new module, which is a
  pod write and out of this lane's scope). It was run locally, where it reports 61/61 present.
- The `--pod-path-only` boundary is a judgement about what `foundry_runner` reads, argued from
  `screen_queue`/`corpus_states` and recorded in `on_pod_path`; it is not a measurement of a pass.
- Whether the pod copies are the same VINTAGE the local screens used is answered only for the 58
  OK paths (byte-identical by SHA-256); the S75 memo's open question about vintage is closed for
  those and stays open for anything shipped later.
