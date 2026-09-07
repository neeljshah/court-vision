# G312 -- the ledger coverage denominator ignores the route's own max_frames (2026-09-07)

VERDICT: PREMISE HOLDS, ADDITIVE FIX LANDED, 13/13 AGREE. Verified codex-sol: ACCEPT WITH
CORRECTIONS (`G312_VERIFY_2026-09-07.md`); its one correction is applied below. Prereg sealed
BEFORE any number: `g312_prereg_2026-09-07.md`, SHA-256 `e04867c94d7e8b30cdec89acd809be71937536b86538446fa53dbaa1acaa9213`.

PREMISE (binding, `den_phx_2025`, pod read-only 2026-09-07). Raw inputs for replay, under
`/workspace/nba-ai-system/data/`: `tracking/den_phx_2025/tracking_data.csv` (1,178,187 B, mtime
2026-09-07 21:48 UTC), its `evaluated_frame_count.json` (516 B), that game's last adjudicated
`tracking/track_daemon_ledger.jsonl` line, `videos/full_games_h264/nba__den_phx_2025.mp4`
(242,142,473 B, height 720); decoded 35,227, stride 6, `max_frames` 3,000, emitted 494.
- **LEDGER**: `evaluated_frames` **5,872**, `coverage_pct` **0.014000**.
- **CAPPED**: `attempted_frames_capped` **500**, `coverage_attempted_capped_pct` **0.988000**.
The denominators differ by **11.7x** and the coverages by **70.6x**. HOLDS.

CHANGE (additive only): `scripts/platformkit/track_daemon_done.py::adjudicate` emits three new keys
and **no existing key moved** -- `route_max_frames` (the cap READ from the game's own
`evaluated_frame_count.json`, never hardcoded), `attempted_frames_capped` and
`coverage_attempted_capped_pct` (unrounded). The three are ONE contract: an absent, unreadable,
non-positive, boolean or string cap -- **or one that cannot be applied because the stride is
unknown** -- yields three `null`s; no default cap is invented.
FORMULA (sealed): `attempted = min(ceil(decoded/stride), ceil(max_frames/stride))`;
`share = frames_emitted / attempted`, `frames_emitted` = distinct `frame` values (G309 convention).

RE-ADJUDICATION of all 13 ledger-backed G309 census rows, `g312_coverage_denominator_readjudication_2026-09-07.csv`:
- **13/13 rows agree within 1e-9** on the three sealed checks: (a) `frames_attempted` equals
  `ceil(decoded/stride)` exactly as integers; (b) `coverage_attempted_frames_pct` equals
  `frames_emitted/frames_attempted`; (c) `coverage_decoded_pct` equals
  `frames_emitted/decoded_frames`. Zero disagreements, so nothing was patched.
- Capped attempted share **median 0.9790, min 0.7210 @ `ncaa_basketball_sRtHQbywiTE`,
  max 1.0000, n = 13** -- reproducing the G309 memo headline exactly at 4 dp.
- Ledger `coverage_pct` median 0.0346: **understated 28.3x at the medians**, per row **18.0x
  (`ncaa_basketball_IB-_u4gW3ds_1080p`) to 70.9x (`den_phx_2025`)**. The spread is the stride.
- Three games (`g220c_jh3fnwMi7dM`, `ncaa_basketball_zqBCKovJCQU`, `wnba_02`) emitted exactly 1,000
  frames = `ceil(3000/3)` -- the direct evidence that `max_frames` bounds SOURCE frame reads.
- Cap RE-VERIFIED, not assumed: all 30 pod `evaluated_frame_count.json` sidecars carry 3,000.

TESTS (one file per command, no full pytest): `tests/platformkit/test_g312_coverage_denominator.py`
**8 passed** -- capped arithmetic, five unusable-cap variants, valid-cap-with-unknown-stride, and
byte-identity of the eleven pre-existing keys against a frozen JSON string and across the
cap-present/absent paths; `scripts/platformkit/test_track_daemon_done.py` **7 passed**.

**THIS IS A SCHEDULING NUMBER, NOT A QUALITY ONE.** A game can attempt 100% of its capped frames
and track the wrong objects. Not recall, precision, accuracy or registration; image space only; all 13 rows stay `passed = false`; no threshold or verdict moved.

## NOT VERIFIED

- **The cap semantics are INFERRED, not read from the adapter loop.** `_evaluated_denominator`
  comments the opposite -- `max_frames` caps evaluated samples, not source reads -- which would give shares of 0.10-0.16, not 0.72-1.00. The three games landing exactly on `ceil(3000/stride)` favour the source-read reading; **the loop was NOT traced to a line.**
- **The ledger JSONL line does not carry the new keys.** They reach `harness_verdict.json` only;
  `track_daemon.py:319-323` selects which verdict keys become ledger columns and was NOT edited
  (a token-gated shared module, and the prereg scoped this row to `adjudicate`).
- **Nothing on the pod was re-adjudicated.** No completed run has written the fields; every number is arithmetic on COMMITTED census columns, and the live ledger (grown 21 -> 26 lines since the
  census) is a different population, deliberately not used.
- `harness_coverage_pct = 0.0` on every row (a G309 gap) is untouched and still unexplained; the
  two census games with no ledger line are excluded, so n is 13, not 15.
- No frame decoded, no render, no label: **no eye check exists for this row**, and no harness,
  register, gate or report reads the additive keys yet.
