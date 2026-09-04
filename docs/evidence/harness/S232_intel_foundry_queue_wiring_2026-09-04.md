# S232 Intelligence Foundry Queue Wiring

## Scope and premise

This is an additive, local queue-wiring construct. It creates no evaluation result, opens no FWER ledger, writes no data store, changes no shared foundry module, and does not enable any flag.

The declared-source classification is in `docs/evidence/harness/S232_intel_foundry_queue_manifest_2026-09-04.json`. It normalizes every feature-store source selected by S224-S231. S223's atlas pool remains excluded from candidate enumeration because S223 declares it snapshot-only pending its required census; the four atlas sources specifically proposed by S229 are individually retained in the manifest as NOT-ENUMERABLE. Base corpora, labels, market inputs, and S223's census targets are not feature candidates and are not silently treated as grammar columns.

Premise confirmation:

- `scripts/platformkit/foundry/catalogue.py` declares exactly `data/cache/pit/opp_allowed_asof_*.parquet` and `data/cache/ingame/*states*.parquet` in `GLOBS`.
- `scripts/platformkit/foundry/seed_queue.py` obtains each selected parquet's columns and delegates its declared grid to `grammar.enumerate_family`.
- The focused test appends an in-memory valid `### fam:` block to the current FWER family text and calls `_parse_families_spec`; the frozen on-disk file is not edited.

## Three-way classification

| Classification | Stores | Count | Reason |
|---|---|---:|---|
| GLOB-REACHABLE | S226 possession state parquets for 2024-25 and 2025-26 | 2 | Both exact paths match `data/cache/ingame/*states*.parquet`. |
| NEEDS-ONE-NAMED-LINE | S226 foul state; S224/S227 garbage-time state; S225/S228 momentum; S228 calibration, form, and schedule stores; S229 sidecars and null; S230 matchup grid; S231 confidence store | 11 | Each is a declared dated parquet source outside both GLOBS. The `data/intelligence/` directory is absent in this worktree, so none is substituted or enqueued. |
| NOT-ENUMERABLE | S225 hot-night and scheme-fit unresolved row parquets; S228 JSON closes; S226 foul-tendency and rotation-pattern snapshot atlas sources; four S229 snapshot atlas sources; two S230 undated interaction grids | 11 | Each lacks a declared dated parquet path, is JSON-only, is snapshot-only, or is explicitly undated. |

Total normalized declared candidate sources: 24. The manifest gives every source its classification and individual reason; it does not omit unavailable or blocked sources from the denominator.

## Dry-run count table

The only stores opened were the two GLOB-reachable state parquets, one at a time. Both are below the 300 MB rail.

| Input path | Bytes | Resolution | Role |
|---|---:|---|---|
| `C:/Users/neelj/nba-track-a13/data/cache/ingame/possession_states_2024_25.parquet` | 249491 | tabular parquet; no raster resolution | declared GLOB candidate |
| `C:/Users/neelj/nba-track-a13/data/cache/ingame/possession_states_2025_26.parquet` | 247926 | tabular parquet; no raster resolution | declared GLOB candidate |

| Check | Hypotheses | Result |
|---|---:|---|
| Default helper dry run to `C:/Users/neelj/AppData/Local/Temp/cx_s232_dry_run.sqlite` | 3510 | No SQLite path was created or opened. |
| Independent direct `grammar.enumerate_family` count over the same two entries and seed-queue closed alphabet | 3510 | Matches exactly. |

The protected canonical path `data/cache/eval_gate/hypotheses.sqlite` is absent in this worktree rather than the stated 0-byte file. This corrects the before-condition without creating it; the helper rejects that canonical path as a scratch target and it remains untouched.

## Integrity and verification

The four required shared files remain byte-identical to their pre-work values:

| Path | MD5 |
|---|---|
| `scripts/platformkit/foundry/catalogue.py` | `8DD2F449A6B865899A2162D79128A93B` |
| `scripts/platformkit/foundry/seed_queue.py` | `ADA8D48EA0539D6E6A90371F3B3570F5` |
| `scripts/platformkit/foundry_runner.py` | `1A37B664686ED813C1D5517578E144D1` |
| `scripts/platformkit/foundry/tiers.py` | `07117389497E6E3C26C2ACC377882585` |

Focused verification only:

```text
python -m pytest tests/platformkit/test_intel_foundry_queue.py -q
2 passed in 1.66s
```

Verifier-contract self-check: B1-B10 do not apply a rejected metric or a schema/gate change; this is a complete declared-list construct with unavailable sources named. Q1-Q5 and Q9 are not engaged because nothing is scored or charged. Q6 holds: this memo reports queue wiring and calibration inputs only. Q7 permits the exhaustive construct denominator. Q8 corrected the absent canonical queue baseline before reporting.

## NOT VERIFIED

No queue application, scoring, charge, or deployment was verified.
