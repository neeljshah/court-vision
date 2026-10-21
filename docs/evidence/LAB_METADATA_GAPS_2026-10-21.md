# Measurement-lab metadata gaps (2026-10-21)

A live audit of `/analytics/lab/` found two kinds of missing provenance on the dataset
headers: no as-of date, and "Not published" for the sport, population and observation
window of several datasets. The lab now reads both from the source JSON at build time
(`webapp/lib/analytics/labHelpers.ts: sourceAsOf`, and the per-row `definition` each
builder sets). This note lists, per dataset, which published field each value comes from
and, where nothing is published, which file and producer would have to carry it. Nothing
is filled from memory: a field with no published source stays "not published" on the page.

All source files live in `webapp/public/data/showcase/`; every producer lives in
`scripts/platformkit/analytics_showcase/` and is named by its source id (for example
`rim_deterrence.json` is written by `rim_deterrence.py`).

## What each dataset publishes

| Lab dataset | Source JSON | As-of (field) | Sport from | Population from | Observation window from |
|---|---|---|---|---|---|
| Pitch mix and velocity profiles | `statcast_showcase.json` | not published | `sport` | `n_pitches` | season named in the `source` corpus path only (`statcast_fuller__2025`); exact dates not published |
| Player consistency | `nba_consistency_profiles.json` | `as_of` | `source` input path (`data/domains/basketball_nba/...`) | `input_coverage.players_meeting_floor`, `input_coverage.unique_players`, `methodology.min_game_minutes_floor`, `methodology.min_qualifying_games_floor` | `methodology.seasons_pooled` + `as_of` |
| Five-player lineup synergy | `lineup_synergy.json` | `generated_at` | not published | `n_qualified` + `method` qualification rule | `observation_window.season` |
| Opponent rim profile: on vs. off | `rim_deterrence.json` | `generated_at` | `method` text ("NBA zone shot-mix cache") | `seasons[].n_qualified` + `seasons[].min_on_floor` | `observation_window.seasons` + `observation_window.note` |
| Home advantage across eras | `soccer_home_advantage.json` | `generated_at` | source `by_era` rows (already published) | `by_era[]` counts (already published) | `by_era[].era` (already published) |
| Tennis surface views (8) | `tennis_surface_transfer.json` | not published | `sport` | `combos.<tour_window>.n_players_in_snapshot` + `floors` | not published |
| Line Half-Life | `novel_line_half_life.json` | `as_of` | `results[].sport` | `results[].n_move_pairs` | `results[].observation_window` |
| Live-Clock Fraction | `novel_live_clock_fraction.json` | `as_of` | `results[].sport` | `results[].n_games_total` | not published |
| Load-Bearing Index | `novel_load_bearing_index.json` | not published (`as_of` holds period labels, not a date) | not published | one published row per team in `results` | `as_of.estimator_a` + `as_of.estimator_b` (both estimator periods, kept distinct) |
| Market Foresight Premium | `novel_market_foresight_premium.json` | `as_of` | `results.<sport>` keys | not published | not published |
| Overreaction Harvest Gap | `novel_overreaction_harvest_gap.json` | not published | `results[].sport` | not published | not published |
| Back-to-back schedule frequency | `novel_schedule_fatigue_tax.json` | not published | not published | `schedule_inequality.n_team_seasons` | not published (`results[].season` is shown as Season) |

## What is still missing, and where it would have to be added

Each line names the file that would have to carry the field (and the producer that writes it).
Until it does, the lab shows "as-of not published" or "Not published" for that cell.

- `statcast_showcase.json` (`statcast_showcase.py`): no generation stamp (`generated_at`) and no
  `observation_window` with first/last pitch dates; the corpus season is only implied by the path.
- `tennis_surface_transfer.json` (`tennis_surface_transfer.py`): no generation stamp, and no
  per-combo `observation_window` (snapshot date or match-date range) behind "career" and "recent form".
- `lineup_synergy.json` (`lineup_synergy.py`): no `sport` field. The lab resolves team names through
  `atlas_nba_teams_manifest.json`, whose `sport` is the pack id `nba_teams`, which is not a league label.
- `novel_live_clock_fraction.json` (`novel_live_clock_fraction.py`): no `observation_window`; `as_of`
  is the artifact date and `corpus` is a path, not a date range.
- `novel_load_bearing_index.json` (`novel_load_bearing_index.py`): no `sport` field, and no
  dated generation stamp (`as_of` is an object of period labels; a `generated_at` is needed).
- `novel_market_foresight_premium.json` (`novel_market_foresight_premium.py`): no `population`
  (unique game count) and no `observation_window`; `corpus` is a path.
- `novel_overreaction_harvest_gap.json` (`novel_overreaction_harvest_gap.py`): no generation stamp,
  no `population` (only per-bucket counts) and no `observation_window`.
- `novel_schedule_fatigue_tax.json` (`novel_schedule_fatigue_tax.py`): no generation stamp, no `sport`
  field (its upstream `schedule_density.json` names `basketball_nba` only in a path) and no
  `observation_window` with season date endpoints.

`site_manifest.json` (`build_site_manifest.py`) mirrors each module's `as_of`, so it inherits the
same gaps and cannot stand in for them.

Verification: `webapp/lib/analytics/labAsOf.test.ts` pins every row of the table above to the
built datasets, so a producer that starts publishing one of these fields will surface as a test
update, not a silent change.
