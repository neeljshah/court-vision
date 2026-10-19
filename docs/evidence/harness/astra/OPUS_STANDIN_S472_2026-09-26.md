# Design critique of the S472 draft (Opus stand-in for the astra lane, read-only, 2026-09-26)

Source: docs/evidence/tracking/specs/S472_spec.md at master 3d91bc1c8, against S468 AMENDMENTS 1-4 and the landed nba_pbp_* modules. Re-checked on playbyplay.json: 546 actions, 4 periods, 132 substitutions, periods 2-4 opening with an OUT, one startperiod jumpball, first events 29 act / 11 out / 31 in plus the unnamed technical by 1627666. The 388-cutoff sweep (105 / 167 vs 314 / 304) was NOT reproduced here.

S472 VERDICT: REVISE (rule sound; add a boxscore oracle, own minutes encoding, fix key shape and I2)

1. Critical - no ground truth (lines 7(b), 26, 29, 37(1)). Agreement with _state() is agreement with the derivation being replaced; a missing IN yields a false starter that resolves silently while a real starter has not yet acted. The boxscore.json beside the fixture is the oracle. Add to line 26: "(E2) the probe reads boxscore.json READ-ONLY (bytes, sha256 recorded) and reports (i) period-1 inferred starters per side versus the boxscore starter flags, and (ii) per player, game-clock seconds on court summed from the inferred per-period lineups versus boxscore minutes. Bar: (i) equal on both sides; (ii) every player within 1 second. Any difference is reported as found and the row REJECTs; nothing is tuned." Line 29: delete "the unread boxscore.json is the named future check".

2. High - minutes encoding points the wrong way (lines 13, 15, 16, 37(2)). S468 lower_bound means "at least this" (IN missed earlier). An inferred starter's value is exact when he started and OVERSTATES when an IN went unlogged or he re-entered (bench time). Substitute in items 4-5: "census tallies minutes_so_far of an inferred_starter record in its own bucket 'inferred'; score_vector emits {'inferred_starter': <value>}; player_coverage counts it resolved; the vocabulary never maps it to lower_bound."

3. High - key shape contradicts itself (lines 13 vs 14-15). Item 2 defines lineup_inferred = {'home', 'away'}; items 3-4 read player_state.lineup_inferred_<side>. Use: "player_state.lineup_inferred['home'|'away']". Item 4 names every new census key exactly: inferred_starter, lineup_inference_reasons = {'home': {reason: n}, 'away': {...}}, lineup_disagreement.

4. High - I2 is false as written (line 25). With :259 passing True, nba_pbp_poll's player_state value changes by design; only the capture record is unchanged. Also :265 calls _refused('player_block_error') without the flag, so the error path lacks the two keys. Substitute: "through run_local_state_capture with the opt-in off, the record's key set and values equal master's; the poll item's player_state gains lineup_inferred / lineup_inference on every path except the :265 error path, where their absence is declared and the census counts it absent." Inference ON inside the unreachable block does not breach S468's row-level opt-in rule.

5. Medium - per-side order must cover evidence actions (line 12). The S468 rule at :250-252 scans substitutions only. Substitute: "the per-side order rule applies to every same-side substitution AND evidence action; a mix of valid and missing orderNumber across them refuses order_mixed." C10 gains the evidence-action mix case.

6. Medium - evidence vocabulary: allowlist foul subTypes, name secondary ids (line 12). Substitute: "a foul is evidence only when subType is in ('personal', 'offensive', 'shooting', 'loose ball', 'offensive charge'); every other foul subType (technical, double technical, flagrant, delay) is neither evidence nor acted_off_court. Only the primary personId counts; assist, foul-drawn, block-victim and jumpBall won/lost ids are never evidence and never trigger acted_off_court."

7. Medium - IN-first mode switch loses inference on a legal feed order (line 12). One IN logged before its paired OUT sends the side to in_declared and it never resolves. Substitute: "mode in_declared only when the side's first five same-side events are all INs (the S468 construct shape); otherwise an IN with no pending OUT waits for a same-side OUT at the same clock value and refuses in_without_out only if none follows."

8. Medium - missing cases (line 24). Add: (C13) a side with four first appearances and no refusal -> starters_unseen, unresolved, never guessed; (C14) an OUT logged before the player's second free throw at the same stoppage -> acted_off_court named; (C15) a coach technical with a personId -> no starter, no refusal; (C16) the evidence-action order mix of concern 5. n becomes 20.

9. Note - item 5's vocabulary addition is inert (line 16). A refused side reaches score_vector only as lineup_unresolved, so the new names never appear there; drop the addition. (Item 1 names seven reasons, not eight, one already existing.)

10. Note - two lineups (line 14). Acceptable only with one canonical reader: "state.lineup_<side> is legacy S433; every consumer reads player_state.lineup_inferred."

Sound:
- OUT-first equals starter is sound in general: an OUT with no earlier IN is a period starter or a missing IN, which E2 catches. IN-first equals non-starter likewise.
- The technical-foul counterfactual and orderNumber finding are measured.
- The probe is separated from every test.
- Dependency confirmed: registry_scorer_e_config.py IMPLEMENTATION_FILES (:31-40) names eight files, no nba_pbp module; feature_registry.py has no nba_pbp reference. No S471 dependency.
- The _state() sha256 over :50-175 plus a -U0 diff is the right seam proof.

Owner questions:
- The live CDN boxscore may carry per-player starter and on-court flags; is one extra request per poll acceptable (S468 said zero, and cdn.nba.com is blocked here), which would make inference a fallback?
- Should E2's per-player minutes bar gate the landing, or only the period-1 starter match?
- Is one WNBA game enough before NBA-REGISTRY-E reads lineup_inferred, or is a second game (or the first live NBA night) a precondition?
