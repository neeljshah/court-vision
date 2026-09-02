# S75 -- every hypothesis is screened on its OWN sport's states

Date 2026-09-03 | area signals/harness | register row S75 (docs/evidence/HARNESS_GAPS_2026-09-03.md)
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B and Q. Calibration language only.

## STEP 0 -- PREMISE (re-measured at HEAD 277bfa90b, NOT falsified)

The four lines the row rests on, read on disk before any edit:

- `scripts/platformkit/foundry_runner.py:124` `def screen_queue(sport: str, *, db, ...)` -- ONE sport
  per queue.
- `scripts/platformkit/foundry_runner.py:133` `states, table, incumbent = screen_predictor.corpus_states(sport)`
  and `:135` `gate_corpus_states(sport, ...)` -- the states are that one sport's.
- `scripts/platformkit/foundry_runner.py:144` `queue.binder = screen_predictor.ScreenBinder(sport, screen, table, rows, incumbent)`
  -- ONE binder, built for that one sport, used for every claimed hypothesis
  (`_screen_one` :178 `states, predict_fn = queue.binder(hypothesis)`).
- `scripts/platformkit/foundry_runner.py:239` `hypotheses = queue.db.claim(batch, tier="T0")` -- the exact
  claim call. No sport argument.
- `scripts/platformkit/foundry/results_db.py:263-264`
  `def claim(self, n: int, tier: Optional[str] = None, lease_seconds: float = LEASE_SECONDS) -> list:`
  -- the signature. The SELECT filtered on `claimed_at IS NULL` and optionally `tier`, nothing else.
- `scripts/platformkit/foundry/tiers.py:205` `digest, sport = semantic_hash(hypothesis), hypothesis.sport`
  and `:207` `corpus=sport` -- `result.corpus` is the HYPOTHESIS's sport while `states` are the bound
  sport's. That is the mislabel: a row can never disagree with itself, so nothing detected it.

PREMISE HOLDS -- `claim` did not filter by sport. The row is NOT falsified.

## CHANGE (2 source files, additive)

1. `scripts/platformkit/foundry/results_db.py` -- `claim(n, tier=None, lease_seconds=..., sport=None)`.
   The SELECT joins `hypothesis` and adds `AND h.sport=?` when `sport` is given. `sport=None` is the
   pre-S75 behaviour, byte-for-byte the same rows. 300 LOC (was 296).
2. `scripts/platformkit/foundry_runner.py` -- `run_pass(number, queue, batch)` accepts a
   `{sport: ScreenQueue}` map as well as a single `ScreenQueue`. With a map it claims per sport
   (`claim(batch // len(queues), tier="T0", sport=sport)`) and screens each claim through THAT sport's
   queue -- its own states, its own partition, its own binder, its own `corpus_sha`. A single
   `ScreenQueue` still claims across every sport (pre-S75), so no existing caller changes. `main()`
   accepts `--sport a,b,c` and builds one queue per sport (default `soccer`, unchanged; the m50
   ProcSpec argv is untouched). 300 LOC (was 300; three legacy blocks reflowed to stay inside the cap,
   no behaviour change -- the `build_minutes_matrix` spec loop became the equivalent comprehension and
   two `print(...)` calls were joined onto one line).

Not changed, deliberately: no bar, threshold, tier rule, partition seed or spec value moves (B10/Q3);
`_charge_ledger` is never called; `--allow-charge` still defaults OFF; `data/registry/` untouched;
`data/cache/eval_gate/backtest_fwer.jsonl` never opened by this lane (the proof run wrote its ledger
path into a scratch directory and no file was created there).

## TESTS (per-file only)

New cases:

- `tests/platformkit/foundry/test_foundry_runner_s16.py`
  - `test_two_sport_queue_screens_every_hypothesis_on_its_own_sports_states` -- a two-sport queue
    (6 nba + 4 soccer hypotheses, two corpora of 40 and 60 states). Each queue's `corpus_sha` NAMES its
    states, so the DB shows whether a row was screened on foreign states. Result rows group to exactly
    `{(nba, sha_nba, 6), (soccer, sha_soccer, 4)}`.
  - `test_a_bound_queue_never_claims_another_sports_hypothesis` -- an nba-bound queue over a
    soccer-only backlog idles; the 5 soccer rows are still claimable afterwards.
  - `test_real_predictor_binds_one_screen_binder_per_sport` -- `--predictor real` over four sports
    builds four distinct `ScreenBinder`s, each over its own sport's states; none refused.
- `tests/platformkit/foundry/test_results_db.py`
  - `test_claim_with_a_sport_never_returns_another_sports_row`
  - `test_an_unfiltered_claim_is_unchanged_by_the_sport_argument`

Output (MASTER, this box):

```
python -m pytest tests/platformkit/foundry/test_foundry_runner_s16.py -q   ->  7 passed in 5.54s
python -m pytest tests/platformkit/foundry/test_results_db.py -q           -> 15 passed in 2.22s
python -m pytest tests/platformkit/foundry/test_tiers.py -q                -> 12 passed in 3.47s
python -m pytest tests/platformkit/foundry/test_screen_predictor.py -q     ->  3 passed in 1.64s
python -m pytest scripts/platformkit/test_foundry_runner.py -q             ->  1 passed in 1.69s
python -m pytest tests/supervisor/test_stack_specs.py -q                   -> 19 passed in 1.23s
```

## LOCAL PROOF -- `--predictor real`, four sports, one scratch DB

Scratch DB, ledger and trials all under the session scratchpad
(`.../scratchpad/s75/`), never under `data/cache/eval_gate/`. Seeded with the frozen grammar,
100 per sport (`seed_queue --frozen --limit 100 --sport <s>`), 400 queued: mlb 100 / nba 100 /
soccer 100 / tennis 100.

```
python -m scripts.platformkit.foundry_runner --db <scratch>/h.sqlite --ledger <scratch>/fwer.jsonl \
  --trials-dir <scratch>/trials --sport mlb,nba,soccer,tennis --predictor real --batch 40 \
  --minutes 3 --idle-exit
```

Ran 11 passes to queue exhaustion (`idle=True`), 400 claims, exit 0.

Binder refusals at bind time, by sport (`--predictor real`): **0 sports refused**. All four
`ScreenBinder`s built. 179 of 400 individual hypotheses were refused by the real predictor on their
OWN merits (153 `ScreenRefused: leaky <col> is a same-game column`, 26
`ScreenRefused: unavailable`) -- mlb 100, soccer 66, nba 7, tennis 6. That is a per-feature refusal,
not a per-sport one; under the old single binder those 400 rows were screened on one sport's columns.

Screened corpus sport vs hypothesis sport (partition sha -> sport recomputed independently after the
run: mlb `ad743c924c7c4547`, nba `1a32541d44aa7fcb`, soccer `5c8d63970b08ce97`, tennis `c8dde4f3a44c8e58`):

| tier | corpus (hypothesis sport) | states sport (from corpus_sha) | verdict | rows | match |
|------|---------------------------|--------------------------------|---------|------|-------|
| T0 | nba | nba | COVERED | 93 | yes |
| T0 | soccer | soccer | COVERED | 34 | yes |
| T0 | tennis | tennis | UNCOVERED | 94 | yes |
| T1 | nba | nba | SCREEN | 93 | yes |
| T1 | soccer | soccer | SCREEN | 34 | yes |

| sport | T1 rows | matched | pct |
|-------|---------|---------|-----|
| nba | 93 | 93 | 100.0 |
| soccer | 34 | 34 | 100.0 |
| **TOTAL** | **127** | **127** | **100.0** |

Bar (100 pct of T1 rows screened on their own sport's states) MET locally, n = 127 scored rows over a
400-hypothesis denominator. Charges 0 over all 11 passes; the scratch ledger file was never created
(`fwer.jsonl` absent); 348 trial JSONs written to the scratch trials dir; `data/registry/` untouched;
`data/cache/eval_gate/backtest_fwer.jsonl` not opened.

The tennis T0 `UNCOVERED` 94 is the honest per-sport coverage measurement the single-binder run could
not produce: on the pod every T0 read COVERED because coverage was measured on the fully-populated
soccer states (S16b NOT VERIFIED). All 127 T1 rows are SCREENs -- **non-findings**. Nothing was scored
against a bar, no K was read, no prereg was sealed, no charged tier ran.

## POD -- NOT DONE

Deliberately skipped. Section B5 of the verifier contract makes any file copied to the pod BEFORE the
ACCEPT verdict an automatic reject; the pod step was optional in this lane's brief, so the contract
wins. The pod remains as S16b left it:

- pid 231346 is still running the pre-S75 code with a single soccer binder, so it keeps writing
  mislabelled T1 rows until the verifier lands the deploy. The register row's pod bar is UNMET.
- Verifier recipe (after ACCEPT): `git -c core.autocrlf=false archive HEAD --
  scripts/platformkit/foundry_runner.py scripts/platformkit/foundry/results_db.py |
  ssh -F ~/.ssh/config.pod pod 'tar -x --no-same-owner -C /workspace/nba-ai-system'`, md5-parity the
  two files, confirm `/proc/231346/cmdline` is the foundry runner before killing it (never touch pids
  19236, 4035, 21620-21622), relaunch the same command line plus
  `--sport mlb,nba,soccer,tennis --predictor real` with `FOUNDRY_PORTABLE_CORPUS=1` in the
  environment and `--allow-charge` ABSENT, log to `/workspace/foundry_runner_s75.log`, then re-read
  per-sport T1 counts and the corpus/states-sport match share after 10 minutes.

## NOT VERIFIED

- No pod measurement. The register bar ("pod T1 rows with corpus == the states' sport 100 pct on a
  15-min re-read, `--predictor real` runs 4/4 sports") is proven LOCALLY only; the pod half is unmet.
- The 1,804-of-2,168 mislabelled pod rows from S16b were NOT re-scored, relabelled or deleted. They
  remain in the pod DB and stay non-findings.
- `screen_predictor.corpus_states` still calls `load_gate_corpus(sport)` WITHOUT the S68 portable
  flag that `tiers.run_tier` passes at `tiers.py:216`. All four sports bind on this box because the
  domain sources are present here; on a host without them (the pod) `--predictor real` may still
  refuse at bind time for that separate reason. Not fixed by this lane -- it is a different defect and
  belongs in its own row.
- `test_real_predictor_binds_one_screen_binder_per_sport` monkeypatches `corpus_states` with synthetic
  per-sport states, so it proves the ROUTING (four distinct binders, each over its own states), not
  that the four real corpora load. The local proof run above is what exercises the real corpora.
- `test_two_sport_queue_...` monkeypatches `tiers.SPORTS` to `()` so no real gate corpus is opened; it
  is a routing construct (n = 10 hypotheses, 2 sports), not a sampled metric (Q7).
- Screens remain non-findings under both predictors. Nothing here is a signal, a verdict or a bar.
- The `--sport` default is still `soccer`; a caller that does not pass the comma list keeps screening
  one sport (correctly labelled, but a single sport). The m50 ProcSpec argv was left untouched.
- The three legacy reflows inside `foundry_runner.py` (kept under the 300-LOC cap) were exercised only
  by `test_legacy_path_keeps_the_matrix_and_the_sleep_default` and
  `scripts/platformkit/test_foundry_runner.py`, both of which stub `build_minutes_matrix`; the real
  minutes matrix was not rebuilt.
