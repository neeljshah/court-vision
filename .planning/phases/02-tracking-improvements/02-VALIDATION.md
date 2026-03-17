---
phase: 2
slug: tracking-improvements
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-15
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ (existing) |
| **Quick run command** | `conda run -n basketball_ai pytest tests/test_phase2.py -x -q` |
| **Full suite command** | `conda run -n basketball_ai pytest tests/ -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `conda run -n basketball_ai pytest tests/test_phase2.py -x -q`
- **After every plan wave:** Run `conda run -n basketball_ai pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 02-01 | 1 | REQ-04 | unit | `pytest tests/test_phase2.py::test_ocr_reader_init -x` | ❌ W0 | ⬜ pending |
| 2-01-02 | 02-01 | 1 | REQ-04 | unit | `pytest tests/test_phase2.py::test_jersey_number_extraction -x` | ❌ W0 | ⬜ pending |
| 2-01-03 | 02-01 | 1 | REQ-05 | unit | `pytest tests/test_phase2.py::test_roster_lookup -x` | ❌ W0 | ⬜ pending |
| 2-02-01 | 02-02 | 2 | REQ-06 | unit | `pytest tests/test_phase2.py::test_db_connection -x` | ❌ W0 | ⬜ pending |
| 2-02-02 | 02-02 | 2 | REQ-06 | unit | `pytest tests/test_phase2.py::test_player_identity_persist -x` | ❌ W0 | ⬜ pending |
| 2-03-01 | 02-03 | 1 | REQ-07 | unit | `pytest tests/test_phase2.py::test_kmeans_color_descriptor -x` | ❌ W0 | ⬜ pending |
| 2-03-02 | 02-03 | 1 | REQ-07 | unit | `pytest tests/test_phase2.py::test_reid_with_jersey_tiebreaker -x` | ❌ W0 | ⬜ pending |
| 2-04-01 | 02-04 | 1 | REQ-08 | unit | `pytest tests/test_phase2.py::test_referee_excluded_from_spacing -x` | ❌ W0 | ⬜ pending |
| 2-04-02 | 02-04 | 1 | REQ-08 | unit | `pytest tests/test_phase2.py::test_referee_excluded_from_pressure -x` | ❌ W0 | ⬜ pending |
| 2-05-01 | 02-05 | 3 | REQ-08b | manual | — | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Plan 02-00 creates a single consolidated test file. Wave 0 is complete when:

- [ ] `tests/pytest.ini` — testpaths config so `pytest tests/` runs without arguments
- [ ] `tests/conftest.py` — shared fixtures: `synthetic_crop_bgr`, `mock_roster_dict`, `temp_db_url`
- [ ] `tests/test_phase2.py` — all 11 stub tests for REQ-04 through REQ-08 (including `test_voting_buffer_none_breaks_streak`)

All stubs use `pytest.importorskip` or are marked `xfail` so the full suite is green before any Phase 2 implementation module exists.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 5 NBA broadcast clips acquired and processed end-to-end | REQ-08b | Requires yt-dlp + video files + NBA API game ID lookup | Run `python run_clip.py --video <clip> --game-id <id>` on 5 different games; verify shot_log_enriched is populated (requires --game-id argument — loop_processor.py must pass --game-id for enrichment to run) |
| Jersey number appears correctly in tracking CSV for known player | REQ-04 | Requires real video with visible jersey numbers | Process a clip, open data/tracking_data.csv, verify player_name column populated |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
