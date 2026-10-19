# S542 build memo: market-anchored state projection + live-like replay (2026-09-29)

Row: S542 (spec `docs/evidence/tracking/specs/S542_spec.md`, items 1-7 with AMENDMENTS 1, 2 and 3 binding; n = 35 cases: the 32 of AMENDMENT 1 plus 33-35 of AMENDMENT 2).
Builder: Opus builder subagent in worktree `nba-harness-h211` (branch `harness-h211`); MUST-NOT-MOVE pins taken at
`586ec022422e6d8e5390d5fff0a47add546c14d8`; FIX r1 applied on master `2c2ac60b365518f9f67aff060d6c0e9e3ccaa3ab`; FIX r2 (AMENDMENT 3) applied on master
`5b8d1c6f6`. The header base and the inventories are regenerated at landing.
LANDING (orchestrator, 2026-09-29): landed from a worktree at master 6ee541f3c6bda18c86c4a48c67cb643fa9f18946; the inventory block below was generated from the FIX r1 candidate, and the S542-owned files changed since then are exactly anchor_projection_io_mlb.py, test_s542_anchor_projection.py and this memo (FIX r2 / AMENDMENT 3; contract r3 checked them).
Status: CANDIDATE, not committed (the orchestrator lands with a pathspec commit). Calibration wording only: PROJ is a
staleness backstop scored by Brier against the STALE book; nothing here is a claim against a fresh mid.
The real-archive replay was NOT run by the builder (the orchestrator runs it after landing, so the sealed prereg
predates the first metric).

## Before-condition (quoted)

The spec's metric before-condition, re-run at the pinned base (not the moving ref):

```
$ git ls-tree 586ec022422e6d8e5390d5fff0a47add546c14d8 scripts/platformkit/ingame/ --name-only | grep -ci anchor
0
```

So before = 0 of 32 cases (no module existed). The streaming before-probe numbers in the spec (r1 465,249 rows /
1,593 games, dead-tick counts, zero-lag live Brier contrasts) are the orchestrator's; the builder did not re-read
the real archive (construct and fixture tests only).

## What was built (OWNED files)

| file | role |
|---|---|
| `scripts/platformkit/ingame/anchor_projection.py` | pure formulas (Stern WP / mu inversion with clip, MLB normal-approximation WE / 60-step mu bisection), S148 live class incl. `tied_regulation_end`, run starts, `Stream`, the event-aware `decide` / `evaluate` / `project`, logit + SHRINK formula, compact `Ticks` columns |
| `scripts/platformkit/ingame/anchor_projection_io.py` | streaming NBA loaders: r1 games (strict rows, counted refusals, duplicate-ts refusal), cached ESPN payloads (never a fetch), RSS `Guard` (every 10,000 lines, 400 MiB; `check()` samples on demand) |
| `scripts/platformkit/ingame/anchor_projection_io_mlb.py` | (sixth module, AMENDMENT 2 (i)) MLB state + Kalshi books in two passes (extract_k linking re-implemented), `mlb_state_out_of_range` refusal, inning-break rows parsed as state (AMENDMENT 3 (a)), home-ticker-only quote rows |
| `scripts/platformkit/ingame/anchor_projection_stats.py` | game-clustered bootstrap, recovery fraction with the UNDEFINED rule, sigma argmin + boundary flag, placebo cell + deterministic donors, SHRINK fit (sklearn), prereg seal + strict loader, AMENDMENT 1 (f) verdict, cell summaries, atomic writers, generated .md |
| `scripts/platformkit/ingame/anchor_projection_replay.py` | the CLI: NBA population, lags {0, 18, 31, 60} plus canary -18, sigma cross-fit, arms, S_18, placebo, SHRINK, MLB cells, strict outputs; RSS sampled every 10,000 scored ticks and before each bootstrap cell; exits 0 / 2 / 3 / 5 |
| `docs/evidence/harness/S542_prereg.json` | sealed prereg `s542_prereg_v1` (every (a)-(g) constant, verdict text, and since AMENDMENT 2 (b) the `placebo_population` key); seal `95e9cfa5ba51959666e97e3aa491ac7fccedb259fc062e2d4f9104b373dbec29` (case 32 pins it). The file is gitignored by `docs/evidence/harness/**`: the landing commit must `git add -f` it |
| `tests/platformkit/ingame/test_s542_anchor_projection.py` | cases 1-12, 19, 20, 29, 31, 33 (MLB range check and home-ticker filter) |
| `tests/platformkit/ingame/test_s542_replay.py` | cases 13-18, 21-28, 30, 32 |
| `tests/platformkit/ingame/test_s542_verdict_e2e.py` | case 34 (verdict wiring end to end against an independent numpy recomputation), case 35 (RSS guard in the scoring loop and before each bootstrap cell) |
| `tests/platformkit/ingame/fixtures/s542_real/**` | real-row fixtures (provenance below) |
| `tests/platformkit/ingame/fixtures/s542_make_expected.py` | ONE-TIME setup script that wrote `s542_expected.json` from the PROBE formulas (ast-lifted `wp`, `inv` from probe_p5 and `RE24`, `HALF_MEAN`, `moments`, `prob`, `implied_mu` from probe_p4) with hand-derived fixture decisions; it never imports the new modules |
| `tests/platformkit/ingame/fixtures/s542_expected.json`, `s542_seal.json` | expected numbers + provenance; MUST-NOT-MOVE sha256 pinned at the base commit |
| `.gitattributes` | three added lines: `tests/platformkit/ingame/fixtures/s542_real/** text eol=lf`, `tests/platformkit/ingame/fixtures/s542_*.json text eol=lf`, `docs/evidence/harness/S542_* text eol=lf` |

A fifth module was used as pre-authorised by AMENDMENT 1 (j), and the sixth (`anchor_projection_io_mlb.py`) by
AMENDMENT 2 (i) because (d) and (e) would push io.py past 300 lines; no assertion was deleted to fit the cap.

## Readings the builder had to choose (open questions for the verifiers)

1. `state_unchanged` compares the current known state S(t - L) with the state the FEED knew at the anchor time
   (latest entry known at tau_a - L), while the mu inversion pairs the anchor mid with the play-time S(tau_a)
   over the stream known at t - L. Read literally (both sides play-time S), `mid_event_reflected` is unreachable
   once tau_a >= tau_s, which contradicts the spec's own examples (L = 60 and the MLB receipt 18:17:56.624397 are
   both labelled `mid_event_reflected`). The chosen reading reproduces every item-2 example, reason and value.
2. Item 2 says "moving tau_s to 19:11:19 -> projected"; with tau_a = 19:11:20 that satisfies tau_a >= tau_s, so the
   rule itself gives `mid_event_reflected`. Case 9 tests the evident intent (case 6 wording): tau_s one second AFTER
   tau_a (19:11:21, L = 59 so the play is known) gives `projected`; tau_s == tau_a (L = 60) gives reflected.
3. `project(...)` returns `(p, reason, mu_clipped)` (the spec text says `(p, reason)` with mu_clipped counted
   separately); the third element is that count's source.
4. Placebo donors are drawn within the same season (the contrast is per season); a cell with one game gives
   `placebo_no_donor`. The recipient and donor set (L = 18 projected ticks, same season) is now sealed as the
   prereg key `placebo_population` (AMENDMENT 2 (b)).
5. `INSUFFICIENT` carries `s544_scorer: withdrawn` (the spec is silent for that branch).
6. MLB population also requires STALE strictly inside (0.005, 0.995) (`mlb_stale_out_of_range`), mirroring NBA.
7. The MLB lag distribution uses state-tuple changes and excludes the first entry of each game (a capture that
   starts mid-game would otherwise inflate it). Case 19 asserts the out received 18.299161 s after its play.
8. A season whose training season has no population ticks cannot select a sigma: its PROJ cells are not scored and
   its ticks are counted `sigma_unselectable_ticks` (verdict then INSUFFICIENT by the game floor).
9. ESPN plays sharing one wallclock second keep the payload order (states_from_payload's stable sort); they are
   distinct plays, not duplicate records. Naive or unparseable wallclocks, missing fields and out-of-range clocks
   are refused and counted `espn_play_refused` before any state is used.
10. Exits 2, 3 and 5 return before any write, so they write nothing and leave earlier outputs at the prefix in
    place. If the write phase itself raises, `atomic_write` removes its temp files AND any earlier final outputs
    at the same prefix (AMENDMENT 2 (g)).

## Fixture provenance (byte-exact, LF, original order; copied by a streaming line-number filter)

| fixture | source (main checkout, read-only) | bytes | sha256 |
|---|---|---|---|
| `s542_real/nba_checkpoints_r1/00529e50...5a78.jsonl.txt` (renamed from `.jsonl` by AMENDMENT 2 (c); bytes and sha256 unchanged; tests copy it into the tmp root under its `.jsonl` name) | `data/cache/ingame_grade_joined/nba_checkpoints_r1/00529e50...5a78.jsonl`, lines 1-3 | 1071 | `03d5c0b90b3f758fe84491fd9976650d6bfdf5bebe4c267a447951d2986f5b9b` |
| `s542_real/espn/401810825.json` | `data/cache/nba_pbp_wallclock_raw/summary/401810825.json`, `{"plays": plays[0:11]}`, each play object byte-verbatim in the source | 5981 | `fc0a7bb7f6d66666ea88db93d53a1f0b07028cc33db23110547255c6eb109a1e` |
| `s542_real/mlb/state/2026-09-29.jsonl` | `data/cache/ingame_capture_view_v2/state/mlb/2026-09-29.jsonl` lines 1904, 1911, 1912 | 31203 | `65edd624cdd7179b471adbecc06f4df7c6e3e7942f39f47f7e37c8da02974cbe` |
| `s542_real/mlb/kalshi/2026-09-29.jsonl` | `data/cache/ingame_capture_view_v2/kalshi/mlb/2026-09-29.jsonl` lines 6905, 6907, 6909, 6913 | 21308 | `04278d1c4773659027c36e8aa44cd98cac100a72a277a094888bc474b3b39905` |

The named lines matched the spec's description (mids 0.625 / 0.625 / 0.635 / 0.635; out played 18:17:33.671,
received 18:17:51.970161). The fixture set holds 11 plays, so the canary at L = -18 sees the 19:12:28 play (not a
19:12:32 play). CONSTRUCT rows (labelled in `s542_expected.json` provenance): no `final` row for game 849845
existed at copy time (1,346 rows for the game, 0 final), so the tests append ONE constructed final row (ATL 4, PHI 2);
the CLI tests also add a copy of the NBA fixture game moved 365 days earlier (game id S542SHIFT, season 2024-25)
so that both seasons exist and the sigma cross-fit runs end to end. MLB cells assert reasons and outputs, not a
Brier against a real MLB outcome.

## Tests, preflight, CLI

```
tests/platformkit/ingame/test_s542_anchor_projection.py: 17 passed
tests/platformkit/ingame/test_s542_replay.py: 16 passed
tests/platformkit/ingame/test_s542_verdict_e2e.py: 2 passed
```

Metric: 35 of 35 enumerated cases pass. `python -m scripts.platformkit.ingame.anchor_projection_replay --help` exits 0.
Case 22 runs the CLI twice in fresh subprocesses (PYTHONHASHSEED 1 and 2) over the fixture roots: `.json`,
`.games.jsonl` and `.md` are byte-equal, strict-JSON parsed, and equal `s542_expected.json` (sigma 26.0 chosen on
both sides, at the grid boundary, disclosed; verdict INSUFFICIENT at 1 game per season).
Preflight (`--base master --spec docs/evidence/tracking/specs/S542_spec.md`) over every owned path (18 paths, incl.
the renamed r1 fixture, the prereg, this memo and .gitattributes): 0 FAIL.

Case 34 (AMENDMENT 2 (a)) builds a CONSTRUCT corpus of 32 games per season (r1 files plus ESPN payloads in a tmp
root), runs `rp.run` (load_nba, score_nba, build: the CLI path) and checks `verdict.inputs` (n_games, s18,
canary_hi, d_hi, placebo_hi), the chosen sigma, the placebo tick count and mean Brier, and the D_18 CI against a
numpy recomputation in the test that shares no helper with anchor_projection_stats (own states and reasons, own
Stern formulas, own placebo donors, own game-clustered bootstrap: default_rng(13), 2000 draws, percentiles 2.5 and
97.5). Pinned literals: D_18 CI upper bound 2025-26 = -0.05196687602947155; placebo mean Brier 2025-26 =
0.14969810884097007. The constructed verdict reaches rule step 2 on CONSTRUCT data; this says nothing about the
real corpus.

Mutation kills: the adversarial tier's harness (`ingame2/vscratch_adv/mut.py`, one exact-string replacement
loaded through its sitecustomize import hook) rerun against ALL three test files
(`ingame2/vscratch_adv/run_mutants_r2.py`):

| mutant | result | killed by |
|---|---|---|
| B2a verdict_inputs reads `lo` instead of `hi` | KILLED | e2e |
| B2b d_hi reads the `all` subset | KILLED | e2e |
| B2c CI percentile 97.5 changed to 90 | KILLED | e2e |
| B2d placebo_hi hard-coded -1.0 | KILLED | e2e |
| B2e canary_hi hard-coded -1.0 | KILLED | e2e |
| B2f s18 hard-coded 1.0 | KILLED | e2e |
| B2g placebo margin change x3 | KILLED | e2e |
| B2g placebo Brier + 0.01 | KILLED | e2e |
| B2h S_18 computed from lag 60 | KILLED | e2e |
| B2i projected subset widened to `why != "state_unchanged"` | KILLED | e2e |
| r1 canary `< 0` to `< 1` | KILLED | replay |
| r1 `s18 >= 0` | KILLED | replay |
| r1 placebo dropped from the ACCEPT check | KILLED | replay |
| r1 `n_chg += 1` | KILLED | replay, e2e |
| r1 canary arm + 0.01 | KILLED | replay, e2e |
| r1 anchor-run look-ahead `starts[i]` | KILLED | replay, e2e |
| r1 sigma fit on own season | KILLED | replay |
| r1 tau_a `>=` to `>` | KILLED | anchor_projection |
| A2 (d) range check removed | KILLED | anchor_projection (case 33) |
| A2 (e) home-ticker filter removed | KILLED | anchor_projection (case 33) |
| A2 (f) pre-cell RSS check removed | KILLED | e2e (case 35) |
| A2 (f) scoring-loop RSS tick removed | KILLED | e2e (case 35) |

22 mutants, 22 KILLED, 0 SURVIVED.

Driver caveat (AMENDMENT 3 (b)): the fix agent's mutation driver counted any "error" text in the output as a kill.
The adversarial tier's strict driver (`vscratch_adv/r2/run_mine.py`) independently confirmed the BLOCKING-2 kills.

## FIX r2 (AMENDMENT 3): MLB inning-break rows are state

Round 2 refused 3,717 real rows as `mlb_state_out_of_range` (half 'Middle' 1,983, half 'End' 1,734, 46 games),
all at outs = 3 with bases empty. They are now parsed: 'Middle' with outs == 3 maps to (inning, Top, 3 outs) and
'End' with outs == 3 maps to (inning, Bottom, 3 outs); mlb_moments already handles outs = 3. Any other half value,
Middle/End with outs != 3, inning < 1, outs outside 0..3, base outside 0..7 and a negative score are still refused
as `mlb_state_out_of_range`. Case 33 now refuses 'Mid', (Middle, 2 outs) and (End, 0 outs) and asserts the two
break mappings. The S542 MLB fixture rows hold no Middle/End row, so `s542_expected.json` is unchanged; the prereg
and seal do not change (MLB-only, descriptive; it cannot move the NBA verdict).

MLB cells (orchestrator real-row probe after fix r2, 2026-09-29: full real MLB state + Kalshi roots, 3-game NBA smoke root;
exit 0, 21.0 s, peak 164 MB; lines copied from the probe output, columns as in the replay .md):

| cell | games | ticks | FRESH | STALE | PROJ | PROJ-STALE | PROJ-FRESH | R | canary / placebo |
|---|---|---|---|---|---|---|---|---|---|
| mlb/Lreal/2026-09/all (vs own stale receipt) | 35 | 10067 | +0.20357 | +0.20412 | +0.20321 | -0.00091 [-0.00208, -0.00011] | -0.00036 [-0.00124, +0.00044] | +1.66633 [+0.23662, +3.33617] | - |
| mlb/Lreal/2026-09/noclip (vs own stale receipt) | 35 | 10067 | +0.20357 | +0.20412 | +0.20321 | -0.00091 [-0.00208, -0.00011] | -0.00036 [-0.00124, +0.00044] | +1.66633 [+0.23662, +3.33617] | - |
| mlb/Lreal/2026-09/projected (vs own stale receipt) | 34 | 2160 | +0.18858 | +0.19061 | +0.18639 | -0.00422 [-0.00980, -0.00046] | -0.00218 [-0.00664, +0.00189] | +2.07260 [+0.25832, +4.86544] | - |

- book_dropped_crossed_or_empty: 9395
- mlb_state_out_of_range: 0

This reproduces contract r2's in-process estimate (2,160 ticks, -0.00422 [-0.00980, -0.00046]) exactly. Rounds 1 and 2 (break rows refused)
gave 1,464 ticks, -0.00592 [-0.01282, -0.00087]. Every MLB cell is vs our own stale receipt, single window, descriptive only.

## Inventory (generated from the FIX r1 candidate by the builder's inventory script)

```
MUST-NOT-MOVE files pinned 74, moved 0 []
tree api files 52 digest EQUAL
tree kernel files 34 digest EQUAL
tree src files 436 digest EQUAL
.gitattributes other lines NOT EQUAL
prereg seal 95e9cfa5ba51959666e97e3aa491ac7fccedb259fc062e2d4f9104b373dbec29
candidate HEAD 2c2ac60b365518f9f67aff060d6c0e9e3ccaa3ab verification base 586ec022422e6d8e5390d5fff0a47add546c14d8 NOT EQUAL
```

`.gitattributes other lines NOT EQUAL` and `HEAD NOT EQUAL` come from master moving since the pin commit (nine
.gitattributes lines added on master between 586ec022 and 2c2ac60b3, none by this row); the worktree diff of
.gitattributes against HEAD is exactly the three owned lines. The base sha and these inventories are regenerated
at landing. Per-file LOC: anchor_projection.py 258, anchor_projection_io.py 130, anchor_projection_io_mlb.py 199,
anchor_projection_stats.py 290, anchor_projection_replay.py 295, test_s542_anchor_projection.py 240,
test_s542_replay.py 293, test_s542_verdict_e2e.py 217, s542_make_expected.py 108.

## Q2 / Q4 / Q5

Q2: no ledger trial is charged; this is a research replay, not a SHIP trial. Q4: one forward fold 2024-25 to
2025-26 across the offseason; SHRINK never sees 2025-26; each season's sigma is chosen on the OTHER season (cross-fit),
so no season's verdict uses a sigma tuned on its own outcomes. Q5: the two seasons are the two corpus units;
one venue (Polymarket), labelled SINGLE-VENUE in every output.

## Mandatory disclosures

- The NBA corpus was already scored exploratorily by P5 and by the spec's before-probe; only the lag scenarios, the
  event-aware anchor and the extended sigma grid are unseen.
- Polymarket price-point semantics are undocumented; the price at ts is treated as known at ts.
- ESPN wallclock is whole seconds and its alignment with the venue clock is NOT VERIFIED.
- L is a scenario for NBA and a measurement for MLB; the MLB STALE is our own previous receipt, not the venue.
- Any SHRINK coefficient from the replay is Polymarket-specific; a Kalshi anchor uses c = 0 until fitted on Kalshi.
- Sigma is cross-fit per AMENDMENT 1 (b); a boundary choice is flagged, not rerun.
- OT uses the OT clock in the same formula; no 300 s staleness rail applies at L != 0.
- `r1_state_mismatch` will be NONZERO on the real corpus: about 300 of about 200k ticks, estimated from 10 of
  about 13.7k on a 50-game subset. Causes: the r1 builder's non-stable pandas sort of plays that share one
  wallclock second, and later score corrections in the cached ESPN payloads. It is not a replay leak; the count
  is printed and never gates.
- The `state_unchanged` reading (compare with the feed state at tau_a - L) is adopted and matches every item-2
  example. Outputs differ from the literal S(tau_a) reading only in the reason label for a state tuple that
  reverts.
- The ACCEPT branch assumes the ESPN wallclock does not lead the real event. The canary cannot detect such a
  lead; it is listed under NOT VERIFIED.
- `atomic_write` also removes earlier final outputs at the prefix if the write phase raises; exits 2, 3 and 5
  return before any write.
- The base sha and the inventories are regenerated at landing.

## Reproduction

Run the three test files one at a time (per-file only), then the CLI twice over fixture roots built as in
`roots()` of `test_s542_replay.py` in fresh processes and compare the three outputs byte for byte. Rebuild the
expected numbers with `python tests/platformkit/ingame/fixtures/s542_make_expected.py` (it must reproduce
`s542_expected.json` exactly).

## NOT VERIFIED

- Any number on the real archive: the replay over nba_checkpoints_r1, the ESPN cache and capture_view_v2 was not
  run by the builder; its verdict, cells, peak RSS and wall time are unmeasured here. A synthetic 200-game scale
  check (no real rows) ran in 3.6 s at 169 MB peak; the real corpus is about ten times larger.
- The orientation of reading 1 above against the spec author's intent (it is the only reading that reproduces
  every item-2 example, but it is a builder choice).
- The size of `r1_state_mismatch` on the real corpus (expected nonzero, see the disclosures; it is 0 on the
  fixture ticks and on the CONSTRUCT corpus of case 34).
- Whether the ESPN wallclock leads the real event; an ACCEPT is conditional on it not leading.
- ESPN wallclock versus venue clock alignment; the Polymarket point meaning behind each r1 price.
- The MLB linking path on doubleheaders (G-suffixed events) and on an ambiguous schedule match: exercised only by
  code reading of extract_k.py, not by a fixture.
- Whether the feed ever sends Middle/End with outs != 3 (none in the six real shards).
- Behaviour under a real RSS approach to 400 MiB (the cap is exercised with an injected sampler only, at the
  load, scoring-loop and pre-cell sample points).
