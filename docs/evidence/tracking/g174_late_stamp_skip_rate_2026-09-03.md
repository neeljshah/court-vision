# G174 - late stamp skip rate

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A2, A3, A5,
A7, B1-B10, Q7, and Q8. Read-only measurement: no tracking table, src file,
run_clip.py, daemon, keeper, deployment, threshold, coordinate contract,
eligibility definition, or prior verdict changed.

## Verdict

**CLOSED AT LIMIT - Q8 premise FALSIFIED.** The new pod currently has no
physical daemon-produced basketball-family tracking_data.csv table. The
eligible denominator is **0 tables**, not the row's 19-table premise. Declared
and undeclared shares are undefined (0/0); no stamp skip rate exists to report.

This is not evidence that the late stamp succeeds on every table. No eligible
table was available, so the full-success condition is unmeasured.

## Q8 premise reproduction and exhaustive denominator

A pod collector was launched with nohup nice -n 15. It read the daemon JSONL
once, then read each candidate CSV separately and refused any CSV over 300 MiB.
It wrote only /tmp/g174_collect.py and an atomic temporary report, never under
data/, and did not interact with a daemon or keeper. Collector SHA-256:
de1e512e4a9974a2eed801dffa9cb8b4a256d97dc63d4b205ffe47473cf11fe9.

Exact retrieval command and raw output:

~~~text
$ ssh -F /c/Users/neelj/.ssh/config.pod pod 'cat /tmp/g174_collect.out'
{"basketball_family_game_ids_in_ledger": 2, "kind": "premise", "ledger_lines": 30, "ledger_parse_errors": 0, "ledger_path": "/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl", "physical_daemon_tables": 0}
{"declared": 0, "declared_share": null, "eligible_denominator": 0, "kind": "summary", "not_read_over_300mb": 0, "undeclared": 0, "undeclared_share": null}
~~~

The physical-table result is independently reproduced below with a
metadata-only enumeration; it reads no CSV contents.

~~~text
$ ssh -F /c/Users/neelj/.ssh/config.pod pod 'cd /workspace/nba-ai-system && find data/tracking -mindepth 2 -maxdepth 2 -type f -name tracking_data.csv -printf "%h %s bytes\n" | sort'
data/tracking/football_Z8Ezd95NnjM 15636596 bytes
data/tracking/football_wHZt1eY3A9s 30171768 bytes
data/tracking/g172_cv2_environment_gap_20260903_a5 700720 bytes
data/tracking/kbo_01 7558478 bytes
data/tracking/kbo_02 4695692 bytes
data/tracking/kbo_03 4626624 bytes
data/tracking/kbo_04 6535789 bytes
data/tracking/kbo_05 6299816 bytes
data/tracking/mlb_2026-08-30_03d78bee 4679363 bytes
data/tracking/mlb_2026-08-30_08b16ce9 5745292 bytes
data/tracking/mlb_2026-08-30_0f36e8cc 6369006 bytes
data/tracking/mlb_2026-08-30_10893dca 3771927 bytes
data/tracking/mlb_2026-08-30_1c6706c6 4978858 bytes
data/tracking/mlb_2026-08-30_2143de43 5051948 bytes
data/tracking/mlb_2026-08-30_2b814fad 5051948 bytes
data/tracking/mlb_2026-08-30_3a02d9b3 4180743 bytes
data/tracking/mlb_2026-08-30_7e8080e5 5711229 bytes
data/tracking/mlb_2026-08-30_f8812b72 6567397 bytes
data/tracking/mlb_A5AkcaXA2fk 8165186 bytes
data/tracking/npb_01 13256987 bytes
data/tracking/npb_02 16173658 bytes
data/tracking/soccer_c1mzmBGHQr4 17149263 bytes
data/tracking/soccer_kSgNjoaqCpI 21667350 bytes
data/tracking/tennis_01 2832341 bytes
data/tracking/tennis_ref01 252850 bytes
data/tracking/tennis_smoke 198839 bytes
~~~

The ledger has two distinct basketball-family game IDs, neither a current
physical table. This is the complete pre-filter population.

| game_id | sport | ledger records | status | rows | expected current CSV | eligible? |
|---|---|---:|---|---:|---|---|
| wnba_01 | wnba | 4 | thin | 0 each | data/tracking/wnba_01/tracking_data.csv absent | no |
| ncaa_basketball_IB-_u4gW3ds | ncaa_basketball | 3 | thin | 0 each | data/tracking/ncaa_basketball_IB-_u4gW3ds/tracking_data.csv absent | no |
| **Eligible physical tables** | | **0** | | | | **0** |

Exact one-store ledger reproduction and raw output:

~~~text
$ ssh -F /c/Users/neelj/.ssh/config.pod pod 'cd /workspace/nba-ai-system && python -c <read-only JSONL filter for wnba,basketball,ncaa_basketball,nba>'
[{"coordinate_space": null, "finished_at": 1788448121, "game_id": "wnba_01", "rows": 0, "sport": "wnba", "status": "thin"}, {"coordinate_space": null, "finished_at": 1788452256, "game_id": "ncaa_basketball_IB-_u4gW3ds", "rows": 0, "sport": "ncaa_basketball", "status": "thin"}, {"coordinate_space": null, "finished_at": 1788452811, "game_id": "wnba_01", "rows": 0, "sport": "wnba", "status": "thin"}, {"coordinate_space": null, "finished_at": 1788457306, "game_id": "ncaa_basketball_IB-_u4gW3ds", "rows": 0, "sport": "ncaa_basketball", "status": "thin"}, {"coordinate_space": null, "finished_at": 1788457307, "game_id": "wnba_01", "rows": 0, "sport": "wnba", "status": "thin"}, {"coordinate_space": null, "finished_at": 1788459255, "game_id": "wnba_01", "rows": 0, "sport": "wnba", "status": "thin"}, {"coordinate_space": null, "finished_at": 1788459466, "game_id": "ncaa_basketball_IB-_u4gW3ds", "rows": 0, "sport": "ncaa_basketball", "status": "thin"}]
~~~

### Per-table result

The construct is empty, exhaustively rather than by excluded failures.

| game_id | CSV size | declaration columns | coordinate values | classification |
|---|---:|---|---|---|
| none: eligible denominator = 0 | | | | no physical daemon-produced basketball-family table |

| Metric over eligible physical tables | Count | Share |
|---|---:|---:|
| Declared | 0 | undefined (0/0) |
| Undeclared | 0 | undefined (0/0) |
| Refused for size over 300 MiB | 0 | undefined (0/0) |
| **Eligible denominator** | **0** | **undefined** |

## Late-stamp exception handling

The exact source handling is at [scripts/run_clip.py](../../../scripts/run_clip.py#L586):

~~~python
try:
    import pandas as _pd
    from scripts.platformkit.coordinate_provenance import (
        PROVENANCE_COLUMNS, stamp_image_space_rows)
    _rows = _pd.read_csv(tracking_csv, encoding="utf-8")
    if not set(PROVENANCE_COLUMNS) <= set(_rows.columns):
        stamp_image_space_rows(_rows).to_csv(tracking_csv, index=False,
                                             encoding="utf-8")
        print("  [provenance] tracking_data.csv declared image_px/observed/none")
except Exception as _e:
    print(f"  [provenance] stamp skipped: {_e}")
~~~

It catches Exception and every ordinary subclass of Exception; it does not
catch direct BaseException subclasses such as KeyboardInterrupt, SystemExit,
or GeneratorExit. After an ordinary failure it prints stamp skipped and
continues to the output summary. A caller can distinguish success from skip
only by retained stdout or the persisted CSV; normal continuation or exit
carries no dedicated provenance-success result.

There is no undeclared eligible table, so part (b) has no matching job-log
lookup or stamp-skipped quote. The two thin ledger jobs are not tables and have
no CSV to classify. Current daemon source removes its per-job log after
_finish at [track_daemon.py](../../../scripts/platformkit/track_daemon.py#L330);
an absent completed-job log would not prove success in a future measurement.

## Eligibility consequence

G154 checks the declaration before evaluating rows:

~~~python
if "coordinate_space" not in fields or not CANONICAL_COLUMNS <= fields:
    return _record(path, sport, "nonempty", "", "", None,
                   "missing_required_coordinate_or_schema")
~~~

At [g154_local_table_census.py:43](../../../scripts/platformkit/g154_local_table_census.py#L43),
missing_required_coordinate_or_schema maps to rollup bucket other. Its later
row-level check repeats the same blocker when the declaration is absent or
empty. Thus an unstamped, nonempty basketball table lands in other and is
invisible to the reaches_gate jump-gate bucket. The late stamp can decide
whether such a table is considered at all. This was not exercised by a current
pod table.

## A5 reader inventory

The required declaration-reader grep was:

~~~text
$ git grep -n 'coordinate_space' -- '*.py' ':!**/test*.py'
~~~

Every production reader with an explicit declaration-presence branch was
inspected:

| Reader | Presence branch / consequence |
|---|---|
| scripts/platformkit/g154_local_table_census.py:107,137 | Missing header is missing_required_coordinate_or_schema, then other. |
| scripts/platformkit/tracking_schema.py:144-147 | Missing column raises unless the explicit legacy switch is enabled. |
| scripts/platformkit/tracking_harness.py:223-233 | Absence is non-metric_local after normalization; ordinary non-legacy input has already failed the coordinate contract. |
| scripts/platformkit/track_daemon_done.py:68-80 | Missing column reports undeclared and rung UNDECLARED. |
| scripts/platformkit/tracking/basketball_imagepx_features.py:100-101 | If present, only image_px is accepted; absence does not trigger this check. |
| scripts/platformkit/teacher_feature_gate.py:25-32 | Missing use-column is caught and skipped; image_px enables the image feature rung. |

The remaining grep hits are producers, tests, value-only validators, metadata
propagation, rendering fallback, or report consumers; none branches on whether
a table has a coordinate declaration. No reader changed.

## Verifier-contract self-check

### A

- **A2:** Reproduced the raw pod report and independently enumerated every
  immediate data/tracking/*/tracking_data.csv path. Two distinct basketball
  family IDs exist in the ledger; neither has a physical CSV.
- **A3 / Q7:** Exhaustive construct, denominator zero. No render sample applies;
  raw commands and output above are the reproduction record.
- **A4:** One physical per-game CSV would be one unit. The actual unique unit
  count is zero; retry rows are shown separately and not recycled as tables.
- **A5:** The declaration-presence reader inventory is above; no reader or field
  changed.
- **A7:** Before commit, this memo, the cited verifier contract, source files,
  and census script exist locally. The collector and report existed when their
  SHA-256 values were read. Absent CSVs are negative inputs, not artifacts.

### B

- **B1:** Clear. The zero denominator remains undefined, not favorable; both
  ledger candidates are named.
- **B2:** Clear. No schema, field, reader, or status changed.
- **B3:** Clear. Missing CSVs are named missing physical inputs, not undeclared
  tables or silently scored.
- **B4:** Clear. No queue, claim, retry, or ownership changed.
- **B5:** Clear. Read-only nohup collection only; no repository file deployed.
- **B6:** Clear. No module, import, command, or test moved or retired.
- **B7:** Clear. Exhaustive construct; no sample substituted for the empty set.
- **B8:** Clear. No fitted or predictive metric is claimed.
- **B9:** Clear. The intended unit is physical per-game CSV; none exists.
- **B10:** Clear. No bar, threshold, contract, eligibility definition, or verdict changed.

## NOT VERIFIED

- Late-stamp declared/undeclared and stamp-skipped rates for a physical
  daemon-produced basketball-family table on this pod.
- A stamp-skipped line for an undeclared eligible table: none exists. An absent
  completed-job log is not success evidence.
- Whether the historical 19-table premise referred to another pod state or time.
- Whether either thin, zero-row ledger job reached the late-stamp block.
