# S313 answers round trip (2026-09-07)

Verdict: **NOT_TESTABLE**. No numeric answer is emitted. The accepted S296,
S310, and S312 receipt artifacts required to connect an S-result to the actual
answer composer are absent in this worktree.

This is an exhaustive construct over the six funnel stages, two connection
entries, every declared route, and four capability rows. Its route table is
`docs/evidence/harness/S313_answers_roundtrip_2026-09-07_route_status.md`; its
capability manifest is
`docs/evidence/harness/S313_answers_roundtrip_2026-09-07_capability_manifest.json`.
The machine-readable summary is
`docs/evidence/harness/S313_answers_roundtrip_2026-09-07_summary.json`.

## Binding premise recheck

The named S71 before-condition was re-run exactly:

```text
python -m pytest tests/platformkit/mcp_server/test_envelope_contract.py -q -p no:cacheprovider
5 failed, 46 passed in 71.92s
```

The five remaining red probes are W01, W02, W03, W04, and H01, against the
unchanged `<= 1` bar. W01-W04 each report `OK_ASOF_IS_WALL_CLOCK`; H01 reports
`OK_NO_SOURCE_ARTIFACT; OK_NO_AS_OF`. The S71 condition therefore still holds.

The S275 focused explicit-basis binding was also re-run exactly:

```text
python -m pytest scripts/platformkit/eval_gate/test_s275_key_explicit_consumers.py -q -p no:cacheprovider
1 passed in 2.17s
```

This preserves the archived eight explicit calibration-basis reads and
zero-flip construct; it does not prove that an S296/S310/S312 answer consumes
one of those verified outputs.

## Exact prerequisite census

```text
ABSENT-IN-WORKTREE docs/evidence/harness/S296_full_boxscore_oof_2026-09-04.md
ABSENT-IN-WORKTREE docs/evidence/harness/S310_tail_beta_offset_2026-09-04.md
ABSENT-IN-WORKTREE docs/evidence/harness/S312_teach_connection_2026-09-07.md
```

The corresponding named JSON outputs are also absent. No S296, S310, or S312
commit for the named Markdown paths is visible through the current repository's
`git log --all` path query. These are exact route prerequisites, so every
affected route remains `NOT_TESTABLE`; no artifact hash, basis, n, confidence
interval, measured-as-of value, verdict, or numeric claim was manufactured.

## Funnel and connection coverage

The acceptance target is 6/6 funnel stages and 2/2 connection entries carrying
real trace receipts. The observed coverage is **0/6** and **0/2**. S223 and
S232 are present as source/candidate constructs, but the former does not
establish an answer-ready receipt and the latter records only a queue dry run.
They do not make the factory outcome or answer feedback connection complete.

The current answer entrypoints were enumerated from
`scripts/platformkit/answers/resolver_registry.py` (84,098 bytes, SHA-256
`7094bd30c5848f155939df5469e47a8637dc1e4eb4fd5eba685d8d4c3eb88be1`),
`scripts/platformkit/mcp_server/tools.py` (14,712 bytes, SHA-256
`fc5ef1cc39fb47e962a7d71e1fd03733b932b71bbb7b85bf431df0a7a9225ece`), and
`scripts/platformkit/answers/contract_client.py` (6,697 bytes, SHA-256
`9ffd667c9f1873ed0b703cacf0ca37dce63527f5ec86638e5226091c59b0b854`).
None registers an S296, S310, S312, or S313 receipt source. The detailed
route-reader enumeration is in the route-status table.

## Capability manifest recount

The four raw spines were opened one at a time by selected column only. Each is
a tabular Parquet input with no raster resolution:

| input | bytes | rows | raw close finding | actual joined-output finding |
|---|---:|---:|---|---|
| `C:\Users\neelj\nba-track-a22\data\cache\combo\gate_corpus_nba_close.parquet` | 217,484 | 1,814 | p_close 563; tails 25 / 60 (n=85) | raw close archive only; no S313 answer receipt |
| `C:\Users\neelj\nba-track-a22\data\cache\combo\gate_corpus_mlb_close.parquet` | 1,656,711 | 39,162 | p_close 910; tails 1 / 1 (n=2) | raw close archive only; no S313 answer receipt |
| `C:\Users\neelj\nba-track-a22\data\cache\combo\gate_corpus_soccer.parquet` | 6,053,712 | 25,834 | no p_close | actual devig-close join: 16,322 joined, 9,512 unjoined, 16,322 valid; SYNTHETIC vintage |
| `C:\Users\neelj\nba-track-a22\data\cache\combo\gate_corpus_tennis.parquet` | 2,745,405 | 41,886 | no p_close | actual devig-close join: 33,766 joined, 8,120 unjoined, 33,685 valid; SYNTHETIC vintage |

`p_base` was never substituted for a close. The current join reader was
`scripts/platformkit/eval_gate/close_join.py` (13,657 bytes, SHA-256
`894fe37bf16303c2a3916bce5dffd5b936f7b46f49c1896cb19971a15e4234bb`). This is
a capability recount only, not a S313 scored comparison or answer value.

## Q1/Q4/Q9 and test status

No scored comparison, candidate/baseline loss, evaluator state, or archived
paired-loss series was produced. Therefore no preregistration seal was created
and Q1/Q4/Q9 are not engaged. The required real landed-loss-to-answer test was
not added or run: doing so without a landed S296/S310/S312 receipt would require
a fabricated receipt and would violate the stated refusal rule. The two binding
premise tests above were run one file at a time; no new code was added.

Pod dispatch was not launched. The required preflight could not reach the pod:
PowerShell SSH returned `off\\r\\nexit /b 1\\r\\n`, while both Git Bash entrypoints
failed before SSH with `CreateFileMapping ... Win32 error 5`. The local fallback
was limited to the four sub-7-MB selected-column inputs and two existing
close-join recounts; no answer data file was opened.

This sandbox denied `git add` because the shared worktree index lock is outside
its writable boundary. The orchestrator must commit these four evidence paths
by explicit pathspec through `lane_commit`; no broad staging command is needed.

Sign convention: no delta was computed. For any future scored comparison,
improvement = baseline loss minus candidate loss; positive = candidate better.

## NOT VERIFIED

- A real S296, S310, or S312 receipt-to-answer round trip.
- The 6/6 funnel-stage or 2/2 connection-entry receipt target.
- Field-exact propagation of artifact hash, basis, n, confidence interval,
  measured-as-of, and verdict through a composed answer.
- Refusal behavior on corrupt, stale, or denied receipt fixtures through the
  missing route.
- Live connectivity after a consumer restart.
- A pod-side rerun; no pod job was launched because its SSH preflight failed.
