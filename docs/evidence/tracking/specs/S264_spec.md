GAP S264 | sport all | worktree a18 | log cx_s264_isoweek_game_id_overlap
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md:53-54,66 fixes ISO-week blocks of state_ts as
  the SF-1 screen/verdict partition basis when a corpus lacks 2+ corpus_units; S209_mlb_phase_recal_fwer_2026-
  09-04.md:48-49 reports ISO week 27 = 15,207 ticks/41 games and ISO week 28 = 18,713 ticks/90 games as
  separate corpus units. NOT FOUND: no memo states whether any game_id appears in more than one ISO-week
  block. This row measures that directly rather than assuming it (Q8).
PREMISE (step 0, INFORMATIONAL): for each gate corpus carrying an ISO-week partition (s88_phase_recal.py's
  build_records; FACTORY_TIERS_SPEC's SF-1 basis), group rows by iso_week(state_ts) and count distinct
  game_id values appearing in more than one ISO-week block; print the exact count and the shared ids found.
  If 0, report FALSIFIED -- the dispatch premise was wrong -- write the memo, commit, and stop; a falsified
  premise is a valid result.
CHANGE (step 1, only if PREMISE confirms >0 shared ids): partition by game id (game-first-date blocks, the
  same construction s88_phase_recal.py already uses for its outer walk-forward) instead of ISO week, only
  where the shared ids occur; keep the existing ISO-week key as an additive alias column beside the new
  game-id-block key. Regenerate the affected calibration table under a NEW filename. Never write data/ or
  docs/research/; no src/ kernel/ api/ intel/ edits; one store at a time, never over 300 MB.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = count of game_ids appearing in more than one ISO-week block of the gate corpus partition,
                  before and after the game-first-date repartition
  before        = not measured anywhere in docs/evidence/ (NOT FOUND); ISO week 27 = 41 games, week 28 = 90
                  games reported as disjoint corpus units without an id-level overlap check (S209 memo:55)
  bar           = if PREMISE finds 0 shared ids, FALSIFIED closes the row; if >0, the game-first-date
                  repartition yields 0 shared ids across blocks, and published numbers reproduce at max abs
                  diff <= 1e-9 when the old ISO-week key is selected via the alias column
  n             = full corpus (every row in every ISO-week block checked), exceeds the 30 rail
  eye check     = n/a (S-row); reproduction = verifier reruns the group-by-id count and, if changed, diffs
                  both partition keys' outputs
  must not move = the existing ISO-week key and its values (kept as an alias); every existing threshold; K
                  unread
NON-TAUTOLOGY: the shared-id count covers every ISO-week block in the corpus, not only weeks 27/28; if the
  repartition changes SCREEN-vs-VERDICT membership for any family, that family's screened_n is reprinted.
EVIDENCE: docs/evidence/harness/S264_isoweek_game_id_overlap_2026-09-04.md plus the shared-id list and (if
  repartitioned) the new calibration table. ASCII only; calibration language only; evidence files under 50 MB.
TEST: one new per-file test (shared-id counter on a synthetic overlapping fixture; repartition idempotence if
  built), run only that file.
REPORT: shared-id count, FALSIFIED or repartition table, test line, SHA. Commit by pathspec, no push.
  NEVER PARK.
