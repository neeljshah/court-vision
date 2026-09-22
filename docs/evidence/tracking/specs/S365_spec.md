GAP S365 | sport all (go-live gate G6) | worktree harness-h23 (master-based) | log cx_s365_family_week_ledger
# G6 continuity ledger: eight CONSECUTIVE qualifying weeks and two INDEPENDENT families need an operational definition (design: docs/evidence/harness/ASTRA_ROUND12_2026-09-21.md section 6 row 6)

SINGLE PROBLEM: docs/GO_LIVE_GATES.md requires eight consecutive qualifying weeks and two independent market families, but nothing
records, week by week, which games qualified, and nothing stops related contracts of ONE game from counting as two families or a
missed week from being stitched over.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/execution/family_week_ledger.py` fails; quote the G6 text from docs/GO_LIVE_GATES.md.

CHANGE:
1. scripts/platformkit/execution/family_week_ledger.py (<= 300 LOC, stdlib): an append-only JSONL ledger of WEEKLY qualification
   records {iso_year, iso_week, family, sport, qualified_games, fill_bearing_games, exclusions by reason, capture gap seconds,
   source artifact path + sha256}. A FAMILY is declared up front in a small JSON table (family id, sport, market type, the rule
   that makes it independent of every other family); two families that share any game_id in a week are reported as NOT
   INDEPENDENT for that week. `streak(family)` returns the current run of consecutive qualifying weeks; a week with no record, or
   with qualified_games below the declared floor, BREAKS the streak -- weeks are never stitched across a break.
   `forecast(family, games_per_week)` prints the earliest calendar date eight consecutive weeks could complete. Counts only.
2. tests/platformkit/execution/test_family_week_ledger.py: missing week breaks the streak; shared game ids void independence;
   duplicate week records refused; ISO week boundaries at year end; forecast arithmetic.
3. Memo docs/evidence/harness/S365_family_week_ledger_2026-09-21.md.

CONTROLS: PREPARE only, NEW files only (edit no pre-existing module; import landed code), construct / fixture tests, no real
archive run, no network, no measured calibration, fill or markout number. ACCEPTANCE: the per-file tests pass; every CLI has
--help; diff = NEW files only. Vocabulary follows contract Q6; automated scan required; assemble retracted-figure literals
from single digits. The memo ends with a NOT VERIFIED list. The pod is OFF.
