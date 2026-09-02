# S16b -- the pod factory brought to HEAD (2026-09-03)

Calibration bookkeeping only. A SCREEN is a NON-FINDING; T0/T1 can never consume K.
This memo measures DEPLOY PARITY, CORPUS PORTABILITY and THROUGHPUT -- nothing about
any hypothesis. Nothing was scored, no K was read, no charge was appended.

VERDICT: **ACCEPT**. 32/32 files at md5 parity with the deployed tree, 20/20 imports OK
on the pod, 4/4 gate corpora loadable (was 1/4), the S16 runner replaced, and in the
first 15 minutes the new runner produced **2,168 T1 SCREEN rows across all four sports
with 0 StaleCorpusError and 0 charges** (the S16 pod hour had 2,220 StaleCorpusError and
screened one sport only).

## 1. THE ONE CODE CHANGE -- T0's corpus load is portable-aware, default OFF

`scripts/platformkit/foundry/tiers.py:run_tier`, T0 branch, one line:

    load_gate_corpus(sport, portable=os.environ.get("FOUNDRY_PORTABLE_CORPUS") == "1")

Additive: absent the env flag the call is byte-for-byte the old refusal (S68's `portable`
defaults to False). No bar, threshold or verdict rule was touched (Q3). The file stays at
300 lines. One new construct test asserts all three cases -- `"1"` -> portable True, `"0"`
and unset -> False, `n = 3 (CONSTRUCT)`, the enumeration being exhaustive over the flag's
domain (Q7).

Tests re-run in MASTER, per-file only (A1):

    python -m pytest tests/platformkit/foundry/test_tiers.py -q              -> 12 passed
    python -m pytest tests/platformkit/foundry/test_foundry_runner_s16.py -q ->  4 passed
    python -m pytest scripts/platformkit/test_foundry_runner.py -q           ->  1 passed

## 2. DEPLOY -- 32 files, md5 parity 32/32

Deployed with `git -c core.autocrlf=false -c core.eol=lf archive <tree> -- <32 explicit
paths> | ssh ... 'tar -x --no-same-owner -C /workspace/nba-ai-system'`. The
`core.autocrlf=false` is load-bearing (S16 measured a 0/15 mismatch without it).

`<tree>` is `f672ae4a5d3b35b9843e0825e2e66432ebf865aa`, the index tree with ONLY
`tiers.py` and `test_tiers.py` staged: every other file is the HEAD blob, so the other
lanes' uncommitted edits (`s58_clamp_family_trial.py`, `sentinel.py`,
`resolver_registry.py`, `compose_matchup.py`, `artifact_tools.py`, `tools.py`,
`clv_daily_readout.py`) were NOT shipped. Parity was checked as
`git cat-file blob <tree>:<path> | md5sum` against `md5sum <path>` on the pod: **32/32
identical, 0 mismatches**.

The set = the S16 hour's 15 files, plus every file the S58c / S66 / S68 landings touched
(`git diff --name-only 1763598f1..HEAD -- scripts/platformkit/foundry
scripts/platformkit/foundry_runner.py scripts/platformkit/combo
scripts/platformkit/eval_gate`), plus `foundry/promotion.py`:

| file | md5 (tree blob == pod) |
|---|---|
| scripts/platformkit/foundry_runner.py | 97e1979561e374f2cebfc7d3ec7f2f1f |
| scripts/platformkit/foundry/__init__.py | bfa22a385d22ea8719be3db3148602cc |
| scripts/platformkit/foundry/catalogue.py | 8acb0c6d37c3b977676b5a5df294e118 |
| scripts/platformkit/foundry/grammar.py | bfa076904ada153f5e10511a21897150 |
| scripts/platformkit/foundry/promotion.py | f493a73ced9ba18e440b4b573b6e9554 |
| scripts/platformkit/foundry/promotion_report.py | 323006ba9b968b90d644d9c9bd5600cf |
| scripts/platformkit/foundry/results_db.py | 5858e26fc528fa90fe966227d31bf042 |
| scripts/platformkit/foundry/screen_predictor.py | 8494b62efd39d6deb295b156137c571b |
| scripts/platformkit/foundry/seed_queue.py | e0f06d8b8365bc683ef5d6540f4a8469 |
| scripts/platformkit/foundry/tiers.py | 5ec187782f239161fa2af13c1c39f44b |
| scripts/platformkit/eval_gate/backtest_runner.py | 8b7b8e3cb10096b2f9f073d9d90bd9b4 |
| scripts/platformkit/eval_gate/catalog_rescreen.py | 26562ddc1f7cd85850fc9376bffa6f3d |
| scripts/platformkit/eval_gate/close_join.py | 03465226357fb0ae7ddff1f614fcc91d |
| scripts/platformkit/eval_gate/close_join_mlb.py | 627fac1b67bdee05161ecde3f53ae6a0 |
| scripts/platformkit/eval_gate/family_bars.py | 9a3fe928271871a466f897e956009565 |
| scripts/platformkit/eval_gate/pbo.py | 130b35a5ced4056459f8028401fa63c7 |
| scripts/platformkit/eval_gate/replication_gate.py | 9a62fe48601d43b38ffaf8a5504af4a7 |
| scripts/platformkit/eval_gate/retro_correction.py | 87a84acaa35c1df7b21aca85ac6a297b |
| scripts/platformkit/eval_gate/s58_clamp_family_trial.py | 60be6db345cb7046d11e85247b58a24f |
| scripts/platformkit/eval_gate/s58_nba_halftime_asof_trial.py | 556bf5e455ac2c82c46288de458779c1 |
| scripts/platformkit/combo/corpus_cache.py | 90f22b510aa624c82fd2a6ad8ab34ec2 |
| scripts/platformkit/combo/fwer_budget.py | 8eaba5b1983241194058ab67a753a44c |
| scripts/platformkit/combo/nested_cv.py | 860a1857fcedf310b217cf75b14a2dd9 |
| docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md | 6ebb01c419a0a4bc6b26a64b3916274a |
| docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md | ae3d55cfab6d8eec9e5aa1c8b346d1bf |
| scripts/platformkit/combo/test_corpus_cache_freshness.py | 8f654f941dc9fd8d121cede429d1db99 |
| scripts/platformkit/combo/test_nested_cv.py | 6db4429a7e9d74141eeaa57c2d4810b2 |
| scripts/platformkit/eval_gate/test_backtest_runner.py | 604748aa314b89e2b5d5fa3ca5cd745c |
| scripts/platformkit/eval_gate/test_catalog_rescreen.py | 2cc6ed4a72b456848b4335d3456a1280 |
| scripts/platformkit/eval_gate/test_close_join_tennis.py | 64c9a23f8c5c244f196db85508e43ce7 |
| scripts/platformkit/eval_gate/test_pbo.py | 32f1a9ae0052596f4a2ef9ac9d64d73d |
| scripts/platformkit/eval_gate/test_retro_correction.py | d7f5bed34252f57656ffb12c7de84dc1 |

Import check under `/usr/local/bin/python` (Python 3.12.3): **IMPORT_OK 20/20** over every
deployed non-test module.

## 3. CORPORA -- 1/4 -> 4/4, and the flag is what does it

Measured on the pod after the deploy, both modes, same process:

| sport | portable=False | portable=True (rows) |
|---|---|---|
| nba | StaleCorpusError | 1,814 |
| mlb | StaleCorpusError | 39,162 |
| soccer | 25,834 rows | 25,834 |
| tennis | StaleCorpusError | 41,886 |

Row counts match S68's local figures exactly. Default mode still refuses 3/4 -- the flag is
a real opt-in, not a silenced check.

## 4. THE RUNNER SWAP

- `/proc/165812/cmdline` re-read first and confirmed to contain `foundry_runner`;
  `kill 165812`; polled `/proc/165812` to **EXITED**. Nothing else was signalled: 19236
  (supervisor), 4035 (track daemon), 21620 / 21622 (mlb capture) were ALIVE before and
  after.
- DB archived, never deleted: `data/cache/eval_gate/hypotheses.sqlite` **moved** to
  `data/cache/eval_gate/hypotheses_s16hour_2026-09-03.sqlite` (6,471,680 bytes -- the S16
  hour's 6,000 catalogue claims, `lease_until` NULL, `family` = soccer). `trials/` was left
  untouched.
- Fresh DB re-seeded from the FROZEN grammar, all four sports, no `--sport` filter:

      /usr/local/bin/python -m scripts.platformkit.foundry.seed_queue \
          --db data/cache/eval_gate/hypotheses.sqlite --limit 6000 --frozen

  `seeded=3564` enumerated -> **3,240 distinct hypotheses** in 124.5 s, reproducing S58c's
  local `3,564 enumerated -> 3,240 distinct` exactly. Per-sport: mlb 333, nba 1,332,
  soccer 531, tennis 1,044. Seeding charges nothing.
- Relaunched 2026-09-02T17:26:06Z, `--allow-charge` **ABSENT**:

      cd /workspace/nba-ai-system && FOUNDRY_PORTABLE_CORPUS=1 nohup setsid nice -n 10 \
        /usr/local/bin/python -u -m scripts.platformkit.foundry_runner \
        --db data/cache/eval_gate/hypotheses.sqlite \
        --sport soccer --batch 50 --screen-rows 800 --poll-seconds 30 \
        </dev/null >/workspace/foundry_runner_s16b.log 2>&1 &

  **pid 231346** (read from `/proc`, self-excluded). `FOUNDRY_PORTABLE_CORPUS=1` confirmed
  present in `/proc/231346/environ`.

`--predictor real` was NOT used, and the reason is a defect, not a preference: `screen_queue`
builds ONE `ScreenBinder` over ONE sport's gate-corpus table, `results_db.claim` has no sport
filter, and a cross-sport hypothesis therefore raises `ScreenRefused` at bind time -- BEFORE
T0's `load_gate_corpus` runs. Running `real` here would have driven StaleCorpusError to 0 by
excluding the very rows that produce it (B1, a circular metric). `p_base` is also the exact
comparable to the S16 pod hour. Filed as a new gap below.

## 5. THE FIRST 15 MINUTES -- 17:26:06Z -> 17:41:06Z

Counted from `result.run_at` in the fresh DB:

| corpus (= hypothesis sport) | T0 COVERED | T1 SCREEN |
|---|---|---|
| mlb | 214 | 214 |
| nba | 910 | 910 |
| soccer | 364 | 364 |
| tennis | 681 | 680 |
| **total** | **2,169** | **2,168** |

    result rows in window   4,337     (2,169 T0 + 2,168 T1; the 1 gap is the window boundary)
    T0 UNCOVERED                0
    StaleCorpusError            0     (S16 pod hour: 2,220)
    screen_failed lines         0
    charges                     0     (charges=0 on all 44 passes; 0 lines match charges=[1-9])
    promotions held         1,033     reason=allow_charge_off
    rows with k_global          0
    rows at tier T2/T3          0
    queue                   3,240 total, 1,040 still unclaimed at the window end

Rate: 2,168 screens / 900 s = **8,672 screens per hour**, against the S16 hour's 9,331.5/h
working rate. The denominator is every claim in the window, failures included -- there were
no failures to include.

## 6. MUST NOT MOVE -- verified after the window

- `data/cache/eval_gate/backtest_fwer.jsonl`: **still does not exist** on the pod.
- `data/registry/`: **does not exist** on the pod.
- No T2/T3 row, no `k_global`, no prereg sealed, no CPCV run, no AHEAD reachable.
- No pod Spec added; the supervisor was not touched.
- Every threshold under `scripts/platformkit/eval_gate/` deployed at its tree md5, unedited.

## NOT VERIFIED

- **4/4 corpora LOAD is proven; 4/4 corpora SCREEN is not.** With the `p_base` fixture the
  states served to every hypothesis are the SOCCER screen states; only `load_gate_corpus` is
  called per hypothesis sport. So `corpus = nba/mlb/tennis` on 1,804 of the 2,168 T1 rows
  labels the hypothesis's sport, not the rows it was screened on -- the same mislabelling
  the S16 memo flagged, now visible on three sports instead of zero.
- **Every T0 was COVERED because coverage was measured on the soccer states**, which are
  fully populated. 0 UNCOVERED is not a per-sport coverage measurement (S58c measured 673
  UNCOVERED locally with the real binder).
- **No hypothesis here is a finding.** The screen predictor is `p_base` passed straight
  through; 2,168 SCREENs are 2,168 non-findings.
- The 15 minutes are not queue-bound (1,040 claims remained), but they are also not a
  measured hour; 8,672/h is a 900-second rate.
- The lease / reap path (S66) was exercised only implicitly -- no claimer died during the
  window, so no expired lease was reclaimed on the pod.
- The archived `hypotheses_s16hour_2026-09-03.sqlite` was not re-read or re-scored; it is
  retained as-is.
- The soccer `close_join` states still carry `vintage: SYNTHETIC` (S34).
- Two S71 hook lines already sitting uncommitted in `RESULTS_LEDGER_SYSTEM.md` are carried
  into this lane's commit; they are hook-written ledger lines, not this lane's work.

## NEW GAPS

- NEW GAP: `screen_queue` binds ONE sport's `ScreenBinder` while `results_db.claim` has no
  sport filter, so `--predictor real` on a mixed queue refuses 3 of 4 sports at bind time and
  consumes their claims; the factory needs either a sport-filtered claim or one runner per
  sport over disjoint queues before any real-predictor pod run.
- NEW GAP: with the `p_base` fixture `result.corpus` records the hypothesis's sport while the
  rows screened are the queue sport's states; the row should carry the states' sport (or
  refuse the cross-sport pairing) so a mislabelled row cannot be written at all.
