# REPRODUCE.md

Three commands, no private data, under 5 minutes on a fresh clone.

## Scope (read this first)

A fresh clone ships with **no `data/`** -- the private corpora, ledgers, and
model artifacts are local-only and gitignored. Any data-backed path that would
otherwise need them prints `VALIDATION_PENDING` or fails closed to `no_data`
and falls back to the recorded canonical table -- it never fabricates a
number. What you *can* verify on a bare clone: the code, the unit tests, the
committed `out/*.json` artifacts, and that every degraded path reports
pending instead of inventing a result. That is ACM-taxonomy **Artifacts
Evaluated -- Functional**, self-serve. It is not third-party **Results
Reproduced** -- file the attestation issue template below to make it that.

## The three commands

```bash
git clone https://github.com/neeljshah/court-vision.git
cd court-vision
pip install "numpy>=1.24" "pandas>=2.0" "matplotlib>=3.8"
python scripts/platformkit/analytics_showcase/check_all.py
```

Expected output (final two lines; last recorded run as of 2026-09-17,
`scripts/platformkit/analytics_showcase/out/check_all_report.json`):

```
total <N>  pass <N>  fail 0  no_check <N>  runtime <N>s
wrote scripts/platformkit/analytics_showcase/out/check_all_report.json
```

The module count grows as more showcase modules are authored; for the current counts
see docs/evidence/CANONICAL_FIGURES.json (titled_findings_count / module counts). Treat "0 FAIL" as the bar. `no_check` modules have no self-check yet and are listed by name in the
report. The run also fails if any `--check` writes to a tracked file, so running it never alters your clone. `check_all.py` runs each module
sequentially as `python -m <module> --check`; a module's `--check` re-verifies
its own committed `out/*.json` (or a synthetic self-check with a known
answer) and asserts the result matches -- no network, no `data/`.

## What "green" does and does not mean

- Does mean: every committed showcase artifact still matches what its
  generator would produce today; no drift between a page's prose and its
  backing JSON.
- Does not mean: any prediction claim is a betting edge, ROI, or dollar
  result. This repo claims calibration/sharpness only -- see
  [docs/evidence/README.md](docs/evidence/README.md) and
  [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md).

## Known failure modes (read before filing "it failed")

1. **`VALIDATION_PENDING` / `no_data` on a data-backed script** -- expected
   without `data/`; not a bug. Only `check_all.py`'s showcase `--check` paths
   are guaranteed data-free.
2. **Windows path separators** -- checks compare JSON content, never raw file
   paths or PNG bytes, so this should not surface; if it does, it is a real
   bug, please report it.
3. **matplotlib backend variance** -- some modules render PNGs during a full
   (non-`--check`) run; `--check` paths never byte-compare images, only the
   JSON artifacts, precisely to avoid this.
4. **`No module named pytest`** -- the `python -m pytest ...` rows in
   [EVIDENCE.md](EVIDENCE.md) need one more package than the three above:
   `pip install pytest`.

## Reporting a result

File a [reproduction attestation](.github/ISSUE_TEMPLATE/reproduction-attestation.md)
either way -- pass or fail. The last end-to-end run of every command in this file, EVIDENCE.md
and the evidence packet is [docs/evidence/REPRODUCE_AUDIT_2026-10-20.md](docs/evidence/REPRODUCE_AUDIT_2026-10-20.md).
 A FAIL report gets fixed and thanked publicly,
same discipline as the disclosed `check_all` fix trail in
[docs/evidence/README.md](docs/evidence/README.md).

---

**Navigate:** [Home](README.md) - [Evidence pages](docs/evidence/) - [Evidence packet](docs/JOB_EVIDENCE_PACKET.md)
