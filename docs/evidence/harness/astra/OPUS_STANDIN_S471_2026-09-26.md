# Design critique of the S471 draft (Opus stand-in for the astra lane, read-only, 2026-09-26)

Source: docs/evidence/tracking/specs/S471_spec.md at master ae539e039, against S460 AMENDMENT 5 and 9-12, the landed registry modules and both 2026-09-25 seals. Line numbers are the spec's own.

S471 VERDICT: REVISE (replace the parallel v2 path with one in-place extension and one superseding seal; MLB-only)

1. Critical - the parallel path reopens post-hoc selection (lines 10-14, 31). With v1 and v2 both loadable forever, an operator can score one night twice and report whichever reads better; that is the exact failure ASTRA_S469 concern 1 and AMENDMENT 5(a) were written to kill. AMENDMENT 5(b) contemplates the in-place route: "adding the S467 lineup blocks requires a NEW committed BLOCK_CONFIG_E", and 5(a) makes identity cover the registry code, so a table change is meant to retire the old config by identity mismatch. With zero scored nights, nothing is invalidated. Substitute for lines 10-14: "CHANGE: extend BLOCKS, NOT_RECONSTRUCTIBLE and the field-kind tables inside feature_registry.py; route the new ids from adapt_block to ONE new sealed module registry_adapters_lineup.py (the hook replaces the :280 short-circuit line so registry_adapters.py stays at or under 300 lines); add that module and mlb_lineup_registry_adapter.py to IMPLEMENTATION_FILES; declare ONE new committed BLOCK_CONFIG_E_<date>.json with the new identity and a later effective_from. BLOCK_CONFIG_E_2026-09-25.json stays committed and byte-identical as the superseded record; it refuses block_config_mismatch from the landing on, and the memo states it scored no night." This deletes registry_scorer_e2.py, the second census, the (game_key, ticker, event_us) join and IMPLEMENTATION_FILES_V2.

2. High - one live config per night (missing case). Substitute into load_block_config: "refuse block_config_superseded when another committed BLOCK_CONFIG_E has effective_from later than this one's and at or before the earliest input event." Add case: "two committed configs, one night: exactly one loads; the other refuses a named reason, counted, nothing written."

3. High - commit-time floor belongs in the shared loader (line 13). Substitute: "load_block_config refuses block_config_not_prospective when effective_from precedes the committer time of the commit that added the file; a rebase that moves the time later only makes it refuse (fail-closed); a forged GIT_COMMITTER_DATE is a disclosed limit." Under this rule the 2026-09-25 seal (effective 00:00Z, committed 23:07Z) refuses by name as well, which is the honest record of its retroactive window.

4. High - defer the NBA half (lines 1, 11-12, cases 8-10, line 29). No NBA policy, no NBA season, S468 unlanded, sum/max encodings unmotivated. Substitute line 29: "MLB-only; no S468 dependency. The six nba_pbp blocks move to a new row that writes an NBA PREREG_E (NBA c_fields) and registers them together." n becomes 13.

5. Medium - count check (line 11). Substitute: "numeric_encoding refuses registry_field_undeclared:<field> for any field in neither _COUNT_FIELDS nor _BOUNDS; every S460 field now relying on the default bound is declared explicitly with that same bound, so every S460 encoding is byte-identical." Case: "1.5 for appearances refuses count_refused; each S460 field encodes as at 19213365f on the committed fixture."

6. Medium - the S460-path regression must survive the reseal (case 2). Substitute: "with the NEW config selecting the S460 seven, main on the committed multi-night fixture writes output byte-equal to the 19213365f snapshot except block_config_sha256 and implementation identity; manifest_hash of the seven equals 6a94c03b...; the old config refuses block_config_mismatch, never KeyError."

7. Medium - bar arithmetic (lines 17-19). Cases 1-2 are "never claimed as passes", yet the bar counts them. Substitute: "bar = every new case passes AND every invariant case holds; metric reported as new-cases passing / new cases plus invariants holding / invariants, separately."

8. Medium - census before fit (case 16). Keep, rewritten for one path: "census_features reports every selected field's buckets before fit and on exactly the rows fit consumes (a spy on fit's input)."

9. Note - disclose the floor restart. The superseding seal restarts the 30-game floor at its effective_from, near the end of the regular season. The memo states the post-seal games available under each seal at landing.

Sound:
- The problem statement (line 6) is verified to the line: closed table, fall-through at :75, short-circuit at :280, identity at :95.
- due_up_lineup refused (identities never coefficients); pitcher_hand to version "2" routed before the short-circuit.
- Cases 7, 13, 14 and 15 (per-block perturbation over the manifest, strict-earlier boundary, future-tail invariance, flag-off A and C unchanged) are falsifiable and construct-only.
- Refusal tuples imported, never copied; _causal_prefix imported with a spy.

Owner questions:
- Given the season calendar, does the 2026-09-25 seal reach 30 post-seal games before it would be superseded? If yes, and a scored night under it is wanted, hold the S471 landing until that run; never keep both seals live.
- Is retiring an unscored seal by identity mismatch acceptable as the record, or should the memo also add a register line naming it SUPERSEDED-UNSCORED?
- Encoding choices for current_lineup (resolved-slot counts) and appearance_history: accept as declared candidates, or require a one-line rationale per block?
