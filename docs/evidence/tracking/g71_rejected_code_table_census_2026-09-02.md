# G71 rejected-code table census

## Result

**No current pod tennis tracking table or tennis harness report was written in
the rejected-code window.** The required durable marking record is
[`g71_rejected_code_tables.json`](g71_rejected_code_tables.json). It has empty
affected-table and affected-report lists deliberately: there is nothing to
mark, delete, or re-track.

The two required denominators are **13 tennis tracking tables on the pod** and
**0 written inside the window**. For completeness, the same read-only snapshot
has 184 tracking tables across sports, 15 tennis harness reports, and 0 tennis
harness reports in the window.

## Independent event window

The window was established before inspecting any table/report time. It is
inclusive from **2026-09-02T02:23:00Z** through
**2026-09-02T18:27:55Z**.

- **DEPLOY start:** the G59 `RESULTS_LEDGER.md` row and the tracking register
  state that the rejected selector and adapter change were deployed at 02:23
  UTC. Read-only `stat` on the preserved pod evidence independently places the
  rejected `adapter.py`, `player_select.py`, and `test_player_select.py` at
  02:23:12Z, 02:23:13Z, and 02:23:14Z respectively.
- **REMEDIATION end:** the G59 remediation register record was committed as
  `4de9a81288e645effbf2b53a398f421d2c0abea5` at
  2026-09-02T13:27:55-05:00 = **18:27:55Z**. That record says master
  `adapter.py` was deployed with the recorded matching md5, and
  `player_select.py` plus its test were removed. The independent G52 memo
  records the immediate control arm with the selector absent. This endpoint is
  the remediation event record; it is not inferred from any table time.

The live pod now has no `player_select.py` or `test_player_select.py`. Its
current `adapter.py` mtime is 19:24:16Z and its md5 matches current master, but
that is a later G45-era deployment and was **not** used to set the G71 window.

## Read-only census

Commands only read the pod: `stat`, `find`, `wc -l`, `md5sum`, and shell
existence checks. No SCP, deployment, daemon action, process inspection, pod
Git command, table modification, or tracking run occurred.

### Tennis tracking tables (13 total; 0 in window)

| write time UTC | table | window result |
|---|---|---|
| 2026-09-01T06:04:44Z | `tennis_01/tracking_data.csv` | before |
| 2026-09-01T06:48:34Z | `tennis_02/tracking_data.csv` | before |
| 2026-09-01T07:30:24Z | `tennis_03/tracking_data.csv` | before |
| 2026-09-01T07:31:13Z | `tennis_04/tracking_data.csv` | before |
| 2026-09-01T07:39:12Z | `tennis_05/tracking_data.csv` | before |
| 2026-09-01T17:14:58Z | `tennis_3x3eEWCZmWQ/tracking_data.csv` | before |
| 2026-09-01T17:18:36Z | `tennis_nyYk2nPZAwY/tracking_data.csv` | before |
| 2026-09-01T18:58:05Z | `tennis_07/tracking_data.csv` | before |
| 2026-09-01T18:58:22Z | `tennis_08/tracking_data.csv` | before |
| 2026-09-01T21:15:47Z | `tennis_06/tracking_data.csv` | before |
| 2026-09-01T21:20:21Z | `tennis_459iho5_AFs/tracking_data.csv` | before |
| 2026-09-01T21:20:36Z | `tennis_09/tracking_data.csv` | before |
| 2026-09-01T21:22:22Z | `tennis_10/tracking_data.csv` | before |

### Tennis harness reports (15 total; 0 in window)

| write time UTC | report | window result |
|---|---|---|
| 2026-08-31T17:49:47Z | `tennis_uso25_zhang_bencic.json` | before |
| 2026-08-31T20:23:38Z | `tennis_uso25_thompson_moutet.json` | before |
| 2026-09-01T06:04:45Z | `tennis_01.json` | before |
| 2026-09-01T06:48:35Z | `tennis_02.json` | before |
| 2026-09-01T07:30:26Z | `tennis_03.json` | before |
| 2026-09-01T07:31:15Z | `tennis_04.json` | before |
| 2026-09-01T07:39:13Z | `tennis_05.json` | before |
| 2026-09-01T17:14:58Z | `tennis_3x3eEWCZmWQ.json` | before |
| 2026-09-01T17:18:38Z | `tennis_nyYk2nPZAwY.json` | before |
| 2026-09-01T18:58:05Z | `tennis_07.json` | before |
| 2026-09-01T18:58:22Z | `tennis_08.json` | before |
| 2026-09-01T21:15:48Z | `tennis_06.json` | before |
| 2026-09-01T21:20:21Z | `tennis_459iho5_AFs.json` | before |
| 2026-09-01T21:20:36Z | `tennis_09.json` | before |
| 2026-09-01T21:22:22Z | `tennis_10.json` | before |

## Landed claims that quote an affected table

**None.** The affected tracking-table set is empty, so its intersection with
every landed memo/register table citation is empty. This is a positive census
result, not an assumption that later claims are clean.

## Contract self-check

- **A7:** every local path named by this memo and the marking JSON exists at
  verification time: the memo, JSON, G59 preserved-code directory, register,
  ledger, G52 memo, and verifier contract.
- **B1:** clear. DEPLOY and REMEDIATION records define the window; table/report
  mtimes only classify objects after that independent window exists.
- **B2-B4:** clear. This is an additive evidence/marking record; no production
  schema, status, reader, gate, claim behavior, or retry behavior changed.
- **B5:** clear for this lane. The pod was read only; no file was copied or
  deployed and no daemon action occurred.
- **B6:** clear. No module, test, or import moved or retired.
- **B7-B9:** not applicable to this provenance census; no sampled visual
  evidence, fitted metric, or recycled denominator is claimed.
- **B10:** clear. No harness threshold or gate value changed.

## NOT VERIFIED

- This census proves only the currently retained pod files and their mtimes.
  It cannot recover a table/report that was written in the window and later
  deleted or overwritten without a retained filesystem/audit record.
- The 18:27:55Z endpoint is the immutable remediation register-event record.
  The current adapter's later 19:24:16Z mtime is deliberately excluded as an
  endpoint because it belongs to a subsequent deployment.
- The rejected selector's stipulated behavior remains historical rejected-code
  provenance, not a claim that it changed any retained table: G52's control
  arm did not find a solver-coverage movement.
