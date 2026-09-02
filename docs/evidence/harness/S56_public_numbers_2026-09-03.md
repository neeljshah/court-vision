# S56 -- public counts corrected to reproducible figures (2026-09-03)

Docs lane. Input: [SIGNAL_INVENTORY_REDTEAM_2026-09-03.md](SIGNAL_INVENTORY_REDTEAM_2026-09-03.md),
section "Numbers quoted in documents that no artifact reproduces". Every replacement
figure below was re-derived from disk IN THIS LANE, not copied from the memo.
Calibration language only; no claim here is a claim about any market.

## Reproduction (this lane, on disk 2026-09-03)

| figure | how it was reproduced | result |
|---|---|---|
| 60 catalog signal classes | `scripts/platformkit/eval_gate/spa_catalog_report.txt` trailer `catalog_signals_on_disk=60`, `documented_retro_survivors=0`; per-sport count by prefix on the 60 verdict rows | 60 = NBA 16 + soccer 15 + tennis 15 + MLB 14; 0 survivors |
| 85 is not a signal count | `scripts/platformkit/eval_gate/retro_correction_report.txt` prints `n_trials` = 85 on EVERY one of the 60 rows | 85 = a per-row multiplicity constant, not a denominator |
| 86 registry signals | `pandas.read_parquet('data/registry/signal_registry.parquet')` (read-only) | shape (86, 11); `status` folded 72 / deferred 14; `coverage_pct` null 86/86 |
| 151 intelligence artifacts | `os.walk('data/intelligence')` file count + mtime histogram; `git ls-files data/intelligence` = 0 (gitignored) | 151 files, all 151 mtime 2026-06-02 |
| the 80-subset | no artifact, manifest or script enumerates it; `INTELLIGENCE.md` itself says later additions are "not yet individually catalogued" | NOT REPRODUCIBLE -- replaced with the honest 151 phrasing, not a new round number |

## Before / after, per file

| file | line | before | after | source named in-line |
|---|---|---|---|---|
| `README.md` | 28 | "0/85 candidate signals survive" | "0 of 60 candidate signal classes survive" | `eval_gate/spa_catalog_report.txt` (`catalog_signals_on_disk=60`, `documented_retro_survivors=0`) |
| `CLAUDE.md` | 3 | "85 trained signals + 80-artifact intelligence layer" | "60 candidate signal classes (0 shipped) + 86 registry signals (untested) + a 151-file intelligence layer" | `eval_gate/spa_catalog_report.txt`, `data/registry/signal_registry.parquet`, `data/intelligence/` |
| `CLAUDE.md` | 18 | "80-artifact intelligence-layer manifest" | "151-file intelligence-layer manifest" | (link target carries the source) |
| `docs/PUBLIC_EVIDENCE.md` | 45 | "80-artifact intelligence layer" | "151-file intelligence layer" | `data/intelligence/` |
| `docs/PUBLIC_EVIDENCE.md` | 73 | "**80-artifact intelligence layer**" | "**151-file intelligence layer** (the full artifact set on disk: 151 files, `data/intelligence/`, dated 2026-06-02; no market-relative test)" | `data/intelligence/` |
| `docs/PUBLIC_EVIDENCE.md` | 188 | "The 80-artifact intelligence layer" | "The 151-file intelligence layer" | (index row) |
| `docs/INTELLIGENCE.md` | 10 | "the original 80-artifact core plus later additions" | "the full artifact set on disk: 151 files, `data/intelligence/`, dated 2026-06-02 ... that earlier subset is **not enumerable from disk**, so 151 is the only count this page states" | `data/intelligence/` |
| `docs/INTELLIGENCE.md` | 19 | "documents the original 80-artifact core in full" | "documents the earliest-catalogued artifacts in full ... no script reproduces the boundary between the two" | (honest phrasing, no number) |
| `docs/INTELLIGENCE.md` | 29 | "151 artifact files populated (80-artifact core + growth)" | "151 artifact files populated (counted on disk 2026-09-03; all 151 mtime 2026-06-02)" | `data/intelligence/` |
| `docs/INTELLIGENCE.md` | 103 | "The 80 artifacts cluster into..." | "The catalogued artifacts cluster into..." | (honest phrasing, no number) |
| `docs/INTELLIGENCE.md` | 305 | "on top of the 80 artifacts above" | "on top of the artifacts above" | (honest phrasing, no number) |
| `docs/INTELLIGENCE.md` | 415 | "the full 80-artifact pass" | "the full artifact pass" | (honest phrasing, no number) |
| `docs/JOB_EVIDENCE_PACKET.md` | 114 | "merge ~80 derived artifacts" | "merge derived intelligence artifacts" | (honest phrasing -- the ~80 fold input is not reproducible either) |
| `docs/JOB_EVIDENCE_PACKET.md` | 115 | "populated from 80-artifact intelligence layer" | "populated from the 151-file intelligence layer (`data/intelligence/`, counted on disk)" | `data/intelligence/` |
| `docs/JOB_EVIDENCE_PACKET.md` | 271 (new) | -- | one do-not-claim row recording the 2026-09-03 (S56) correction and citing the memo | `SIGNAL_INVENTORY_REDTEAM_2026-09-03.md` |

## Checks run

- Residual grep `85 signals|85 trained|80-artifact|0/85` over the five edited files:
  **1 hit, and it is the correction row itself** (`JOB_EVIDENCE_PACKET.md:271`).
  0 hits outside an explicit correction note.
- Banned-token grep over the 20 ADDED diff lines
  (`roi|profit|bankroll|pnl|\bedge\b` + all six retracted figures): **0 hits**.
- No retraction context was touched: the six retracted-figure rows in section 4
  of `JOB_EVIDENCE_PACKET.md` are byte-identical.

## NOT VERIFIED

- No honesty linter with a file-path CLI exists under `scripts/platformkit`
  (`grep -rl honesty` returns `analytics_showcase/honesty_exhibit.py`,
  `econ/greenlight_trust_honesty.py`, `gamebrief/honesty.py` -- all ledger/verdict
  readers, none lints markdown). The banned-token grep above stands in for it and
  is weaker than a linter would be.
- The 60 REJECT verdicts were read from the two reports; they were NOT re-derived
  (the reports state the historical per-signal DM vectors are not archived).
- The 86 registry rows were read for shape and two columns only; row contents were
  not inspected.
- `data/intelligence/` file CONTENTS were not opened -- only the count (151) and
  the mtime histogram were measured.
- The memo's mechanism discrepancy (87 parsed vs 130 ledger-confirmed) was NOT
  reproduced in this lane and appears in none of the five public files, so no
  public occurrence needed correcting.
- No test file was executed; no gate was run; no ledger row was charged.
