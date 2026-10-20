# Tests: where they live and how to run one

Counts below are as of 2026-10-20, on the full tree (master), from the command shown.

## Run ONE file, never the whole suite

A full run freezes the dev box, so the project rule is one file at a time.

```bash
# python
python -m pytest tests/path/to/test_one.py -q
python -m pytest scripts/platformkit/eval_gate/test_claim_consistency.py -q

# webapp (vitest), from webapp/
cd webapp && npx vitest run path/to/file.test.tsx
```

Never run bare `pytest`, `python -m pytest tests/`, or `npm test` (which is `vitest run` over everything) as a routine check.

## Python tests

`git ls-files | grep -E "test_.*\.py$" | wc -l` printed 4274.
They sit under `tests/` and next to the code they cover. Top-level folders, from
`git ls-files | grep -E "test_.*\.py$" | cut -d/ -f1 | sort | uniq -c`:

| Folder | Files |
|---|---|
| tests | 2585 |
| scripts | 1207 |
| domains | 410 |
| predict_service | 49 |
| predmarkets | 9 |
| supervisor | 7 |
| ops | 3 |
| frontend | 2 |
| apps | 1 |
| governance | 1 |

Within those, the largest groups are `tests/platformkit` (1397), `scripts/platformkit` (1095),
`tests/platform` (306), and `domains/basketball_nba` (121), `domains/mlb` (98),
`domains/tennis` (54), `domains/soccer` (52).

The public repository carries only an allowlisted subset (see CONTRIBUTING.md), so the public
`tests/` folder looks small. The engine tests live in the private tree.

## Webapp tests (vitest)

`git ls-files | grep -E "\.test\.(ts|tsx)$" | wc -l` printed 419: `webapp/components` 187,
`webapp/lib` 142, `webapp/app` 63, `apps/live_board_ui` 27.

## Eval gate

`scripts/platformkit/eval_gate/` holds the claim-consistency check and its test:

```bash
python -m scripts.platformkit.eval_gate.claim_consistency --repo-root .   # must print 0 findings
python -m pytest scripts/platformkit/eval_gate/test_claim_consistency.py -q
```

## Analytics showcase proof

```bash
python scripts/platformkit/analytics_showcase/check_all.py   # 0 FAIL is the bar
```

It re-verifies each showcase artifact and rewrites
`scripts/platformkit/analytics_showcase/out/check_all_report.json`. See [REPRODUCE.md](../REPRODUCE.md).

## Webapp QA workflow

`.github/workflows/webapp-qa.yml` runs typecheck, lint, vitest (non-blocking), a build, and the honesty grep (fails if a retracted figure appears
in shipped HTML outside its retraction framing). Run the same steps locally from `webapp/`.
