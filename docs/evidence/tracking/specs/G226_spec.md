GAP G226 | sport ncaa_basketball / wnba | worktree a8 | log g226_basketball_tracking_adapter
**THIS IS A BUILD ROW, NOT A MEASUREMENT ROW -- the first of the night.** Build in
`domains/basketball/tracking/` (a SANCTIONED area, not human-gated) and register in
`scripts/platformkit/adapter_run.py` (also sanctioned). **`src/` REMAINS HUMAN-GATED: READ and IMPORT
only, edit nothing there.** **`domains/tennis/`, `domains/soccer/`, `domains/football/` and
`domains/baseball/` are READ ONLY -- copy their patterns, do not modify them.**

**HELD FOR THE POD RUN ONLY -- DO NOT RUN A CLIP UNTIL G211 HAS REPORTED.** The BUILD and its tests are
local and may start immediately. The daemon and keeper are permanent residents and are the load floor,
**not** a reason to wait; never kill or restart them.

**WHY THIS ROW EXISTS -- BASKETBALL, THE PROGRAMME'S PRIMARY SPORT, HAS NEVER BEEN SCORED BY THE HARNESS
ONCE, AND THE REASON IS NOT CALIBRATION.** From G207's landed sport summary: **`wnba` 2 directories ->
0 scored, 2 EXCLUDED; `ncaa_basketball` 1 -> 0 scored, 1 EXCLUDED**, while football scored 3, kbo 8,
mlb 12, npb 3, soccer 3 and tennis 3. **The basketball tables are not empty** -- 3,377, 4,171 and 271
rows -- **they are excluded for "noncanonical columns".** The two headers, read from the pod:
  - **basketball (legacy `unified_pipeline` path):** `frame, timestamp, player_id, team, x_position,
    y_position, x_norm, y_norm, velocity, acceleration, direction_deg, court_zone, ball_possession,
    distance_to_ball, nearest_opponent, nearest_teammate, event, team_spacing, spacing_hull_area,
    team_centroid_x, team_centroid_y, paint_count...` -- a derived-FEATURE table.
  - **canonical (`tennis_01`, adapter path):** `frame, track_id, cls, x, y, calibration_provenance,
    projection_status, projection_rejection_reason, raw_projected_x_ft, raw_projected_y_ft,
    coordinate_space, observation, calibration, source_fps, source_height, source_duration`.
**Basketball declares no `coordinate_space`, no `calibration_provenance`, no `projection_status`, so the
harness cannot audit its frame of reference and drops it before any gate runs.**

**The structural cause, verified in master: basketball is the ONLY sport with no tracking adapter.**
`scripts/platformkit/adapter_run.py:30-33` registers exactly `tennis`, `soccer`, `baseball`, `football`.
`domains/basketball/tracking/` holds only `keypoints.py` and `line_calibration.py` -- no `adapter.py`,
no `geometry.py` -- against soccer 7 non-test modules, tennis 10, football 12, baseball 12.

**WHAT SUCCESS IS, AND IT IS DELIBERATELY MODEST: move basketball from EXCLUDED to SCORED.** Football,
baseball and soccer all emit `image_px` and all fail `coordinate_contract` -- **but they are SCORED, so
their failure is visible and measurable. Basketball is not even that.** **Getting basketball to "scored,
failing coordinate_contract" is a real advance and is this row's target.**

**DO NOT TRY TO SOLVE CALIBRATION IN THIS ROW.** Automatic basketball corner search is measured at
**0 of 17** (G210b, G214) and G217 attributes the residual to detected line geometry; G223 and G224 are
in flight on that. **This adapter must emit HONEST PROVENANCE: when no calibration is available, declare
`coordinate_space=image_px` and say so in `projection_status` / `projection_rejection_reason`.** The
architecture already expects exactly this -- `adapter_run.py:45` reads *"Add a sport here only once its
adapter supports image_space=True"*. **Emitting a court coordinate you cannot justify would be far worse
than emitting an honest pixel coordinate.**

METHOD:
  1. **Read `domains/soccer/tracking/adapter.py` (148 lines) and `domains/football/tracking/adapter.py`
     (126 lines) first and MIRROR them.** Do not invent a new shape. The soccer interface is
     `detect_players`, `detect_players_image_space`, `process_video(..., player_only, image_space)`,
     `write_csv`, plus a geometry mixin and `_assign_tracks`. **Match the canonical column set and its
     semantics exactly**, verified against a real adapter table, not from this spec's transcription.
  2. Add `domains/basketball/tracking/geometry.py` with a basketball geometry mixin. **Reuse what
     exists**: `domains/basketball_wnba/tracking/court_config.py`, `domains/basketball/tracking/
     line_calibration.py`, and the 94x50 ft court with 19 ft paint depth and the league lane widths
     already used by `court_points_for_sport` (NCAA 12 ft, WNBA 16 ft). **If a piece is unusable, say
     why rather than silently reimplementing it.**
  3. Add `domains/basketball/tracking/adapter.py` with a `BasketballAdapter`. **`image_space=True` must
     work and must be the honest default when no homography is available.** Reuse the existing detector
     rather than writing a new one.
  4. Register basketball in `adapter_run.py`'s adapter registry. **That file is SHARED with a concurrent
     session -- make an ADDITIVE change only, commit it with an explicit pathspec, and do not reformat,
     reorder or otherwise touch the other sports' entries.** Note it already carries
     `"basketball": False` and `"ncaa_basketball": False` entries in its ball-capability map, so the
     file anticipates basketball; **leave those `False` unless you have evidenced ball detection, which
     you do not.**
  5. **<= 300 LOC per file** (the rail). If it does not fit, split honestly rather than compressing.
     **Per-file tests for every new module, pasted.** **If a commit grows an allowlisted file, raise its
     entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12) and run that
     rail test.**
  6. **THEN, after G211 reports, run it on ONE basketball clip on the pod, bounded**, and **score the
     result with the harness.** Report the harness verdict and the FIRST FAILURE HEAD. **Report the
     column-by-column comparison against the canonical schema so a reader can confirm the contract is
     met.** **DISK GUARD: `df` is NON-AUTHORITATIVE on this pod; do a real `dd` write probe first,
     record `du -sm /workspace/nba-ai-system/data` (baseline ~30,900 MB of 50,000), and STOP if the
     probe fails.** Delete temporary artifacts and report bytes freed.
  7. **Do NOT delete, overwrite or migrate the existing legacy basketball tables.** They are the
     historical record and other rows cite them. Write to a NEW directory.

**HONEST LIMITATIONS to state, not discover:** an adapter is **necessary but demonstrably NOT sufficient**
for court coordinates -- football, baseball and soccer all have adapters and all still fail
`coordinate_contract`. **So the expected outcome of this row is a SCORED row that FAILS, and that is the
success.** One clip is one clip. The route is non-deterministic (G190/G195/G198/G203) and no
deterministic mode exists, so a single run is one draw; say so and do not present a single score as
stable. **You are NOT claiming the legacy basketball feature table is wrong** -- it is a different
artifact serving a different purpose; this row adds a canonical one beside it.

ACCEPTANCE RULE:
  metric        = the harness verdict and first failure head for one basketball clip run through the new
                  adapter, plus a column-by-column check of the emitted schema against the canonical
                  adapter schema, plus per-file test results
  before        = basketball is 0 scored / 3 EXCLUDED for noncanonical columns and is the only sport with
                  no tracking adapter; its output declares no coordinate space or calibration provenance
  bar           = **basketball reaches SCORED rather than EXCLUDED.** A `coordinate_contract` failure at
                  that point is the EXPECTED and ACCEPTED outcome. **Do NOT change the coordinate
                  contract, any gate, any threshold, or the harness to make a row pass** -- that is the
                  one thing that would make this row worthless. If you cannot reach SCORED, report why
                  and what is missing; an honest failure here is a real result.
  n             = 1 clip, bounded run (EXISTENCE of a canonical basketball table, not a rate)
  eye check     = none required; this row is a schema and contract result
  must not move = the coordinate contract, every gate, threshold, bar and verdict, the harness,
                  `src/` (READ and IMPORT only), the other sports' adapters and their registry entries,
                  the existing legacy basketball tables, the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g226_basketball_tracking_adapter_2026-09-04.md with the schema
comparison, the harness verdict and first failure head, the LOC counts per new file, the pasted test
results, every disk-guard probe result, bytes freed, and a NOT VERIFIED list. Commit BEFORE reporting
(A7).
TEST: per-file tests only, pasted. NEVER a full pytest.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
