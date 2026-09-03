# S76 charge-path follow-ups -- deterministic DRY evidence

## Verdict: ACCEPT

This is instrument-only evidence. It uses the real `tiers.run_tier("T2")` path,
`RealScreenPredictor`, CPCV, and a synthetic two-`corpus_unit` fixture. The trial
opens only a temporary `backtest_fwer.jsonl`; the real ledger is not opened for write.
The fixture freezes its temporary row timestamp at `2026-09-04T00:00:00+00:00` solely
so its two committed evidence files reproduce byte-for-byte.

Prerequisite re-measurement confirmed all four S76 premises before the change:

- `RealScreenPredictor` used a length bucket only.
- The charge writer carried the tiers-spec pin but no per-trial seal field.
- Soccer's charged result used division clustering only.
- A charged `TierResult` had no archive.

The DRY fixture has two corpus units with 48 events each. The frozen partition sends
one 48-event unit to T2. Its 28 CPCV train paths are recorded by the real predictor;
each archive fit carries a stable `train_sha256`. The temporary ledger row has K=1.

| Construct | Result |
|---|---|
| a. CPCV cache identity | PASS. All 28 train-set SHA values are distinct and all 28 real fits are archived; no external reset adapter is used. |
| b. Per-trial seal | PASS. `prereg_sha256` remains the tiers-spec pin `b2b2ea5a0fe2bd4adaf327aa38e546b49ca0eec3`; additive `trial_prereg_sha256` is the sealed S58 trial value `7125552f4c772e15c05057a5beaf460b1dc152496007cd20ea14c521f893cc30`. |
| c. Parallel clustering | PASS. `cluster_key` remains `div` (G=3). Archive `cluster_metrics` also carries home-team n_eff and DM (G=6). |
| d. Charged archive | PASS. The non-null archive has the real predictor fit state and 48 per-event paired losses, timestamp, and primary cluster id. |

`n = 4 (CONSTRUCT)`: the four named S76 sub-items are exhaustive. Eye check is not
applicable. Reproduction is the single test below: it regenerates the DRY fixture and
byte-compares its temporary row and archive to the committed copies.

```text
python -m pytest tests/platformkit/foundry/test_s76_charge_path_followups.py -q
2 passed
```

Evidence copies:

- `S76_charge_path_followups_2026-09-04_ledger.json` SHA-256 `23671238b68662f96480abf5605ef9f77bde2ca7744dbab35107bf1b97ce7d23`
- `S76_charge_path_followups_2026-09-04_archive.json` SHA-256 `be2d83041d555313d7d56e8f776dce03f9066a873cdc167a7668dbeb3a18fd9a`

Verifier-contract self-check: B1-B10 hold (no rows excluded, additive field only,
no fall-through or claim loop, no pod use, no orphaned import, no sampled metric,
no self-fit evidence, non-degenerate event units, and no changed bar). Q1 is the
pre-existing S58 seal named above; Q2 writes and reads K before scoring; Q3 leaves
the tiers spec untouched; Q4 uses the existing purged symmetric-embargo CPCV path;
Q5 has no AHEAD claim; Q6 uses calibration language only; Q7's exhaustive construct
count applies; Q8 premise was re-measured; and Q9 is the committed paired-loss archive.

## NOT VERIFIED

- No real-corpus result was recalculated.
- No T3 replication statement was made.
- No production ledger row was appended, no pod was contacted, and no feature flag changed.

## ATTEMPT 2

This additive repair pass preserves the accepted four S76 constructs while fixing the
two focused-suite compatibility regressions and the ledger row terminator.

| Change | Result |
|---|---|
| Cluster counts | Derive both primary and home `n_clusters` from their cluster ids; no DM-double attribute is read. |
| Predictor cache | Give both single and k=1 combo paths the same CPCV key, including `len(train) // refit_every`. |
| Ledger append | Retain an existing LF or CRLF JSONL terminator; the construct test covers both. |
| Unscored result | Reuse `tiers._UNSCORED` through a deferred import, avoiding a circular module import. |
| Orchestrator docs | Restored `HARNESS_GAPS_2026-09-03.md` and `RESULTS_LEDGER_SYSTEM.md` from `master`. |

| Test | Result |
|---|---|
| `test_tiers.py` | PASS: 12 passed. |
| `test_family_combo_screen.py` | PASS: 3 passed. |
| `test_s76_charge_path_followups.py` | PASS: 2 passed, including the LF/CRLF construct. |
| `test_screen_predictor.py` | PASS: 5 passed. |
| `test_results_db.py` | PASS: 22 passed. |
| `test_results_db_archive.py` | NOT AVAILABLE: this worktree has no such path; its requested invocation reported file not found. |
| `test_foundry_runner_s150.py` | PASS: 5 passed. |
| `test_foundry_runner_s16.py` | PASS: 7 passed. |
| DRY charged trial | PASS: temporary ledger only; n=48, K=1, cluster views `div,home`. |

### NOT VERIFIED

- Attempt 2 has not yet been independently verified against a real corpus or production ledger.
- The absent `test_results_db_archive.py` was not substituted with another test file.
