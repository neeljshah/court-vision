# Reproduce audit, fresh public clone, 2026-10-20

Scope: every command or script path that [REPRODUCE.md](../../REPRODUCE.md) (repo root; there is
no `docs/REPRODUCE.md`), [EVIDENCE.md](../../EVIDENCE.md) (its Reproduce column) and
[JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md) tell a reader to run, executed from the repo
root of a fresh clone of `master` (head `e4367dc`) in a new virtualenv (Python 3.13.16, CI uses
3.11). Calibration language only; no figure was changed to match an output. Mismatches are flagged.

## Packages a reader needs

| Package | Named in | Resolved version | Needed by |
|---|---|---|---|
| `numpy>=1.24` | REPRODUCE.md | 2.5.4 | check_all.py |
| `pandas>=2.0` | REPRODUCE.md | 3.0.6 | check_all.py |
| `matplotlib>=3.8` | REPRODUCE.md | 3.11.2 | check_all.py |
| `pytest` | not named by any of the three docs (added by this audit) | 9.1.1 | the four `python -m pytest` rows in EVIDENCE.md |

Node 22 (pre-installed, no `npm ci`) was enough for `webapp/scripts/verify-public-json.mjs`.

## Commands

Result key: MATCH = ran, figure matched; DIFF = ran, different figure; FAIL = first error line;
PRIVATE = cannot run here, names the missing path. "before/after" refers to the fixes in this PR.

| Command (source) | Result | Figure quoted | Figure obtained | Note |
|---|---|---|---|---|
| `pip install "numpy>=1.24" "pandas>=2.0" "matplotlib>=3.8"` (REPRODUCE) | MATCH | three packages | numpy 2.5.4, pandas 3.0.6, matplotlib 3.11.2 | `scripts/platformkit/analytics_showcase/requirements.txt` names the same three. |
| `python scripts/platformkit/analytics_showcase/check_all.py` (REPRODUCE, EVIDENCE E) | MATCH | `total 110 pass 96 fail 0 no_check 14` | `total 110 pass 96 fail 0 no_check 14`, exit 0, 23s | Committed `out/check_all_report.json` has 111 entries (97 PASS) and lists `agent_fleet_history.py`, which is not in the public tree; its `as_of` is 2026-10-20, REPRODUCE.md says 2026-09-17. The write guard works: a dirty tracked artifact (see claims row) makes it exit 1. |
| `python -m scripts.platformkit.eval_gate.dm_recompute_pregame` (EVIDENCE A) | PRIVATE | Brier 0.1735 model vs 0.1666 close, n=372 scored | none; prints `CORPUS MISSING` for every corpus, exit 0 | Needs `data/domains/{mlb,soccer,basketball_nba}/*.parquet`. The doc labels it "(private corpora)". |
| `python -m pytest scripts/platformkit/eval_gate/test_dm_recompute_pregame.py -q` (EVIDENCE A) | MATCH after `pip install pytest` | test passes | FAIL without pytest: `No module named pytest`; then `4 passed` | pytest is not in the REPRODUCE.md install line. |
| `python -m pytest tests/platform/test_no_leak_paths_staged.py -q` (EVIDENCE C) | MATCH after pytest | tests pass | `2 passed` | same. |
| `python -m pytest scripts/platformkit/eval_gate/test_leak_contract.py -q` (EVIDENCE F) | MATCH after pytest | tests pass | `6 passed` | same. |
| `python -m scripts.platformkit.analytics_showcase.claims_corpus_meta --check` (EVIDENCE D) | MATCH after fix | 103,048 generated; 101,864 recompute | before: `OK` with no figure (the check only asserted the file was non-empty, so it would pass on a `no_data` stub); after: `generated=103048 verified=101864` | Fixed: `--check` now asserts `status == ok` and prints the recorded totals. |
| `python -m scripts.platformkit.analytics_showcase.claims_corpus_meta` (PACKET row "regenerate with") | FAIL before fix, MATCH after | regenerates the tally | before: overwrote the tracked `out/claims_corpus_meta.json` (1,696 lines) with a 4-line `status=no_data` stub; restored with `git checkout`; after: `kept recorded artifact ... (not overwritten without data/)` | Fixed: on a clone without `data/` the recorded artifact is kept. Contradicted the REPRODUCE.md promise that degraded paths fall back to the recorded table. |
| `python -m scripts.platformkit.reject_ledger show` (PACKET, "513 ... counted directly from") | PRIVATE | 513 REJECT/DEFER verdicts | `(graveyard empty)`, 0 rows | Reads `data/frontend/reject_ledger.jsonl`, which is private. The 513 is not re-derivable from the public tree. |
| `python -m scripts.platformkit.answers.contract_client "does b2b_rest_penalty hold up" --sport nba` (PACKET) | PRIVATE | `CONFIRMED_LOCAL effect=-1.73 n=4732 p=0.0056` | FAIL: `No module named 'scripts.platformkit.answers'` | Module and `domains/basketball_nba/knowledge/validation_ledger.jsonl` are private. |
| `scripts/verify_production_mae.py` (PACKET section 3, "the public, re-runnable lead number") | PRIVATE | MAE PTS 4.83, REB 1.92, AST 1.39, FG3M 0.89 | none | Script absent from the public tree (engine). "Public, re-runnable" holds only in the private repo; the packet's layout note covers this. |
| `scripts/platformkit/edge_hunt_scoreboard.py` (PACKET, "reproduced by") | PRIVATE | MARKET_EFFICIENCY_PROOF tables | none | Absent from the public tree. |
| `scripts/platformkit/proof_nba/ml_accuracy.py` (PACKET section 3) | PRIVATE | 0.1735 vs 0.1666, n=743 | none | Script and `data/cache/kalshi_complete/own_lines_backtest_nba.json` absent. |
| `scripts/run_walk_forward.py --gate` (PACKET) | PRIVATE | exits 1 on overfit | none | Absent (engine). |
| `scripts/platformkit/tracking/public_figures_check.py` (PACKET) | PRIVATE | framing rule | none | Absent; the packet already says "(private tree)". |
| `python -m scripts.platformkit.eval_gate.claim_consistency` (PACKET, public-tree framing gate) | MATCH | clean | `0 finding(s)`, exit 0; its test file: `19 passed` | Not spelled out as a command in the packet; CLI form taken from the module docstring. |
| `node scripts/verify-public-json.mjs` from `webapp/` (EVIDENCE E, "runs in deploy-demo.yml") | MATCH | every file passes | `389 files, 0 failures` | Ran without `npm ci`. |
| `python -m pytest scripts/platformkit/test_clv_ledger_io.py -q` (EVIDENCE G, "readable here; runs in the full private tree") | FAIL before fix, MATCH after | test passes | before: `No module named 'scripts.platformkit.odds_shop'` at collection; after: `3 passed` (two real OS processes raced) | Fixed: `clv_ledger.py` imported the private devig helper at module top for one function; the import is now lazy. EVIDENCE.md cell updated to the runnable command. |
| `scripts/platformkit/check_ingame_join_integrity.py` (EVIDENCE G, "exit 1 on the original corpus") | PRIVATE | exit 1 | `NO_DATA: .../data/cache/ingame_grade_joined is not a directory`, exit 2 | Needs the private joined tick corpus. |
| `check_all.py` "passes 52/52" (PACKET section 4, dated 2026-07-23) | DIFF (dated) | 52/52 | 110 modules, 96 pass, 14 no_check today | Historical count, left as is; REPRODUCE.md carries the current line. |
| `total 27 pass 27` in docs/evidence/README.md (as_of 2026-07-22, linked from REPRODUCE.md) | DIFF (dated) | 27/27 | 110/96/14 today | Historical, labelled with its date; left as is. |

Rows read "recorded" in EVIDENCE.md point at committed artifacts, not commands; every artifact
they cite exists (see links below). The execution modules in EVIDENCE.md section G are "read the
module" rows; all five files exist.

## Links

Relative markdown links checked with a script over the two files (http, mailto and anchors
skipped): EVIDENCE.md 70 and JOB_EVIDENCE_PACKET.md 5, 75 in total, 0 unresolved. REPRODUCE.md:
7 checked, 0 unresolved. Nothing to list.

Backticked paths (not links) cited in the packet and absent from the public tree: 79, of which
32 under `scripts/`, 20 `src/`, 17 `data/`, 4 `tests/`, 3 `docs/`, 2 `api/`, 1 `database/`. The
packet's layout note says these resolve in the private repository at tag
`pre-minimize-2026-09-17`; the three `docs/` ones (`docs/_audits/`, `docs/operations/`,
`docs/research/`) are local-only trees per CLAUDE.md.

## Fixes in this PR

- `scripts/platformkit/analytics_showcase/claims_corpus_meta.py`: keep the committed tally when
  `data/` is absent; `--check` asserts the artifact is `status=ok` and prints its totals.
- `scripts/platformkit/clv_ledger.py`: lazy import of the private `odds_shop.devig_twoway` so
  `clv_ledger_io` and its race test import on the public clone.
- `EVIDENCE.md`: the CLV ledger row's Reproduce cell is now the runnable pytest command.
- `REPRODUCE.md`: names `pytest` for the EVIDENCE.md test rows and links this audit.

## Flagged, not changed

- The committed `check_all_report.json` was generated in the private tree (111 entries, one module
  the public tree does not ship); REPRODUCE.md's "as of 2026-09-17" is older than its `as_of`.
- The packet's "513" reject count and the "public, re-runnable" MAE script need the private tree.
- The REPRODUCE.md "three commands" leave pytest out, so four EVIDENCE.md rows fail as written.
