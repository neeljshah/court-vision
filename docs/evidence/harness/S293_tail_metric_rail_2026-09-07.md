# S293 tail metric rail -- pod scoring (2026-09-07)

## Verdict

NOT VALIDATED (instrument landed, no candidate accepted). S293 implements and
reproduces calibration measurement only. It fits nothing, accepts nothing, and
charges nothing. The frozen `+0.004` Brier comparison bar is untouched.

Scored by the orchestrator's pod scorer on 2026-09-07 because the codex build
lane could not reach the pod: its sandbox failed before `pod_run` launched with
Git Bash `CreateFileMapping` Win32 error 5, and WSL is not installed. The lane's
implementation, preregistration and test are scored here unchanged except for
the three scorer corrections listed under "Scorer corrections" below.

## Preregistration seal

Preregistration: `docs/evidence/harness/S293_tail_metric_rail_prereg_2026-09-07.md`

    stated   S293_PREREG_SEAL_SHA256=8af6d5591a3b70f983d94dd5ab9b2a34dc659f0d65b18126b7482175e18618e8
    computed 8af6d5591a3b70f983d94dd5ab9b2a34dc659f0d65b18126b7482175e18618e8

SHA-256 of the preregistration bytes above the seal line after CRLF-to-LF
normalization. Verified three times: locally against the worktree file before
the pod run; inside the scorer on the pod (`_seal()` raises on mismatch); and
against the COMMITTED bytes via `git show HEAD:<path>`, which closes the item
the lane left open because its sandbox denied staged-byte inspection. The seal
predates every metric in this memo.

## Machine and inputs (A9, S1, A11)

Pod scratch `/workspace/wt/a14` via `/c/Users/neelj/bin/pod_run a14` (RunPod,
python 3.12, pandas 2.3.3, scikit-learn 1.9.0, numpy 2.1.2, pyarrow 25.0.1). The
deployed tree `/workspace/nba-ai-system` was never written; `data/` was linked
read-only; no pod process was killed or restarted. `data/registry`,
`backtest_fwer.jsonl` and `hypotheses*.sqlite` never reached the pod.

| Input | Bytes | SHA-256 | Resolution |
|---|---:|---|---|
| `data/cache/inplay_odds/nba_checkpoints_full.parquet` | 2,829,826 | (pod-resident; 465,249 rows) | tabular; not applicable |
| `docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv` | 39,159,272 | `77eebaa5e82d81d6a428874b937939353e15af21b6270b84f83691489297eeed` | tabular; not applicable |
| `docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_summary.json` | 5,290 | `1892f277dc7b55683792b7ac2491e8faf5b06ab20ad1f7b6f3ef087b0be70914` | JSON; not applicable |

Protected route identities, hashed on the pod before and after scoring, both
equal to the preregistered values (`source_identities_before ==
source_identities_after` is true in the summary JSON):

    cpcv_engine.py           5accfbe490031acb084a8e4375a082b00d842cf4011a76c6d27dfc2c7db614a5
    walkforward.py           c8a9b5b0f0f7c84dc5fdb0c7a4a27e0f7f2040f99326ef5376cde011df27bc2e
    s272_ingame_tail_recal.py 83f86f6a653a364c3e8047b58f5976128d69daeecc2a882dc82deffb78ca7c30
    ingame_incumbent_nba.py  476ed9fdfb714b93c5b722f8e99fb1266cdb5987a729495f12e84d2b62ea08ed

Neither `cpcv_engine.py` nor `walkforward.py` was edited; `cpcv_tail_metrics.py`
imports both read-only, which is the S268 precedent. The S272 summary and paired
CSV are byte-identical to their pre-run values.

NOTE ON THE SPEC'S PREMISE. The S293 spec froze
`cpcv_engine e0dd8269...` and `walkforward 1058f981...`. Those two values do NOT
match this worktree and did not before any S293 work; the lane recorded that
premise as FALSIFIED (Q8) and the continuation re-froze the current bytes in the
preregistration, which is what is verified above. The identity check is
therefore against the preregistration, not against the spec's stale strings.
This is a deviation from the spec text and is listed under NOT VERIFIED.

## Sign convention

improvement = baseline loss minus candidate loss. Positive means the candidate
carries the lower loss. In the primary replay the baseline is `recal_null`
(the S272 incumbent recalibrator) and the candidate is the S272 tail
recalibrator. In the S289 and S291 diagnostic tables the baseline is `market`
and the candidate is `recal_null`.

## 1. Replay check -- Brier and ECE reproduce S272 (bar: <= 1e-12)

The unchanged S272 CPCV route was re-run through `cpcv_evaluate` with its
symmetric one-day embargo and season purge (2 folds: 2024-25, 656 games,
198,344 ticks, market fallback; 2025-26, 937 games, 266,905 ticks, 656 train
games). Every one of the 465,249 archived ticks across 1,593 games was scored;
no subset was selected. Tail mask is the original S272 mask
(`market_prob <= 0.10 or market_prob >= 0.90`), 308,756 ticks / 1,590 games,
matching the archive's 308,756 `tail_tick` rows exactly.

| partition | metric | S293 replay | S272 archive | delta |
|---|---|---:|---:|---:|
| all (465,249 ticks / 1,593 games) | candidate Brier | 0.07335361389463317 | 0.07335361389463317 | 0.000e+00 |
| all | recal_null Brier | 0.07331694555660052 | 0.07331694555660052 | 0.000e+00 |
| tail (308,756 ticks / 1,590 games) | candidate Brier | 0.00684043525954786 | 0.00684043525954786 | 2.602e-18 |
| tail | recal_null Brier | 0.00678518157184189 | 0.00678518157184189 | 0.000e+00 |
| tail | candidate ECE | 0.00124458478236057 | 0.00124458478236057 | 0.000e+00 |
| tail | recal_null ECE | 0.00149340987492018 | 0.00149340987492018 | -1.084e-18 |

Largest deviation 2.602e-18, inside the 1e-12 bar by six orders of magnitude.
The all-tick Brier improvement interval reproduces byte-identically:
`[-7.042297493210607e-05, -8.368211469821433e-06]`, S272 `-3.66683380326361e-05`
vs S293 `-3.666833803263752e-05` (delta 1.4e-18).

Every number in this section was recomputed by the scorer directly from the
fetched per-tick CSV, independently of the scorer script's own assertions (A2).

## 2. The new fields -- log loss and tail log loss

Epsilon = 1e-15, applied by clipping to `[eps, 1-eps]`. No row is excluded:
`excluded_rows = 0` on both arms.

| partition | arm | log loss | improvement (recal_null minus candidate) |
|---|---|---:|---:|
| all (diagnostic only) | candidate | 0.22101275549941980 | -0.00137501143633797 |
| all (diagnostic only) | recal_null | 0.21963774406308179 | |
| tail | candidate | 0.03083380630060955 | -0.00207193607814845 |
| tail | recal_null | 0.02876187022246110 | |

Per the preregistration, the all-tick log loss is an implementation diagnostic
and carries no comparison claim. Both improvements are negative: on this corpus
the S272 tail recalibrator carries a HIGHER log loss than `recal_null`, matching
the direction of its Brier result. An honest BEHIND is a valid result.

### Endpoint and clipping accounting

| arm | n | p = 0 rows | p = 1 rows | clipped rows | excluded rows |
|---|---:|---:|---:|---:|---:|
| candidate | 465,249 | 62,154 | 80,162 | 142,316 | 0 |
| recal_null | 465,249 | 0 | 0 | 0 | 0 |

The candidate's isotonic tail arms saturate to exactly 0 or 1 on 142,316 ticks
(30.6 percent). `recal_null` never saturates. On the 156,493 non-tail ticks the
candidate is identical to `recal_null` by construction (verified: 156,493 of
156,493 rows equal).

### The log-loss comparison on this candidate is epsilon-dominated

Only 18 of the 465,249 ticks are saturated AND wrong (`p = 0` with `y = 1`, or
`p = 1` with `y = 0`); all 18 fall inside the tail mask. At epsilon 1e-15 each
costs `-log(1e-15) = 34.54`, so those 18 rows alone account for 0.001336 of the
0.001375 all-tick log-loss gap (97.2 percent) and 0.002014 of the 0.002072 tail
gap (97.2 percent). Sweeping epsilon confirms it:

| epsilon | all-tick improvement | tail improvement |
|---|---:|---:|
| 1e-15 | -0.001375011436338 | -0.002071936078148 |
| 1e-09 | -0.000840490256714 | -0.001266492801585 |
| 1e-06 | -0.000573541935547 | -0.000864241705331 |
| 1e-03 | -0.000503604861360 | -0.000758857020245 |

The sign is stable across four orders of magnitude but the magnitude moves by
2.7x. The Brier improvement is epsilon-free at `-0.000036668338033` (all) and
`-0.000055253687706` (tail). Reported finding of this rail: tail log loss is a
usable ranking instrument here but not a stable magnitude instrument against a
saturating isotonic arm without a declared clipping policy. The 18 rows are
named and counted, never dropped; the headline numbers above include them.

## 3. S289 diagnostic -- favorite-longshot fine bins (frozen mask)

Bins are defined on `market_prob`; each arm's loss and reliability is computed
over ALL ticks in the bin, not over the ticks whose own probability lands in the
bin. All six declared bins are published, including the two where `recal_null`
loses to market. Every bin reproduces the spec's frozen tick and game counts
exactly.

| bin | ticks / games (spec) | ticks / games (measured) | recal_null log loss | market log loss | improvement (market minus recal_null) |
|---|---|---|---:|---:|---:|
| [0.01,0.05) | 9,226 / 649 | 9,226 / 649 | 0.108935350460834 | 0.109064231604745 | +0.000128881143911 |
| [0.05,0.10) | 8,982 / 691 | 8,982 / 691 | 0.261167621122677 | 0.261923312933974 | +0.000755691811297 |
| [0.10,0.20) | 15,778 / 826 | 15,778 / 826 | 0.468033294804994 | 0.469461864991162 | +0.001428570186167 |
| [0.80,0.90) | 23,912 / 1,005 | 23,912 / 1,005 | 0.452100455173979 | 0.452417312322612 | +0.000316857148633 |
| [0.90,0.95) | 13,123 / 871 | 13,123 / 871 | 0.251914078110729 | 0.251267723457134 | -0.000646354653595 |
| [0.95,0.99) | 12,624 / 827 | 12,624 / 827 | 0.127493601362987 | 0.126642126705553 | -0.000851474657434 |

Reliability (mean probability vs empirical outcome rate) per bin:

| bin | empirical rate | recal_null mean p | recal_null gap | market mean p | market gap |
|---|---:|---:|---:|---:|---:|
| [0.01,0.05) | 0.023520485584219 | 0.029990627536936 | 0.006470141952717 | 0.027602427921093 | 0.004081942336874 |
| [0.05,0.10) | 0.074148296593186 | 0.078496674137341 | 0.004348377544154 | 0.073909151636607 | 0.000239144956580 |
| [0.10,0.20) | 0.177652427430600 | 0.157833978780023 | 0.019818448650576 | 0.151790626188364 | 0.025861801242236 |
| [0.80,0.90) | 0.830336232853797 | 0.845506462866299 | 0.015170230012502 | 0.848871403479425 | 0.018535170625627 |
| [0.90,0.95) | 0.929817877009830 | 0.921297399589748 | 0.008520477420082 | 0.924106797226244 | 0.005711079783586 |
| [0.95,0.99) | 0.971720532319392 | 0.969772851285098 | 0.001947681034294 | 0.971488355513308 | 0.000232176806084 |

`recal_null` carries the lower log loss in four bins and the higher log loss in
the two strong-favorite bins `[0.90,0.95)` and `[0.95,0.99)`; on reliability gap
market is closer in four of six. No bin is dropped to improve a mean. Every bin
is >= 30 ticks (Q7).

## 4. S291 diagnostic -- comeback states (frozen mask)

Mask fixed before scoring, by margin and clock alone:
`period <= 4 AND abs(margin) >= 12 AND (4 - period) * 720 + game_clock_s <= 720`.
Measured `remaining_s` range 0.0 to 720.0.

| quantity | spec (frozen) | measured | note |
|---|---|---|---|
| ticks | 133,319 | 133,184 | -135 (0.10 pct) |
| games | 1,113 | 1,111 | -2 |
| `outcome_home_win` split | 77,516 / 55,803 | 77,381 / 55,803 | home-loss half matches exactly |

The whole 135-tick shortfall sits on the home-win half, in 2 games. The mask
definition reproduces; the corpus is 2 games short of the count frozen in the
spec. Reported, not reconciled.

| arm | ticks | log loss | improvement (market minus recal_null) |
|---|---:|---:|---:|
| market | 133,184 | 0.016139711921027 | -0.000095632319090 |
| recal_null | 133,184 | 0.016235344240117 | |

No clipping, no endpoint rows, no exclusions on either arm in this mask.

Trailing-side accounting: 55,871 ticks have the home team trailing, 77,313 have
it leading. The trailing team went on to WIN in 434 of the 133,184 ticks and
LOST in 132,750 (0.33 percent completion). Ticks where the trailing team still
lost are included; nothing is restricted to completed comebacks.

LABEL DEFECT, NUMBERS UNAFFECTED. The preregistered transform is "1-p and 1-y
only when the home team is trailing", which maps every tick into the LEADING
team's frame, not the trailing team's. The summary JSON keys `trailing_wins`
(132,750) and `trailing_losses` (434) therefore carry inverted names; the
correct reading is 434 trailing-team wins and 132,750 trailing-team losses, as
recomputed above directly from `margin` and `y`. Log loss is invariant under the
joint flip `(p, y) -> (1-p, 1-y)`, so both arms' log-loss figures stand exactly
as printed. The transform was NOT changed, because the preregistration froze it;
the label is corrected here instead.

## 5. Added accounting (OT, zero clock, grain)

- OT periods 5-6: 14,765 ticks, matching the spec's frozen count exactly.
  Counted outside the S291 mask, which is `period <= 4`.
- Zero-clock ticks: 271,154 of 465,249 (58.3 percent). Period distribution is
  P1 44,428 / P2 68,825 / P3 52,645 / P4 284,586 / OT5 13,152 / OT6 1,613: this
  checkpoint corpus is dominated by period-4, clock-zero states, which is why
  `remaining_s <= 720` admits most period-4 ticks. Named because it materially
  shapes the S291 denominator.
- Mixed-grain refusal exercised on the real archive: the S272 paired CSV mixes
  1,593 `all_game` rows with 308,756 `tail_tick` rows (310,349 total, both
  counts asserted at run time), and `refuse_mixed_grain` rejects it. Per-tick
  losses are REGENERATED through the unchanged route; none is replayed from the
  archive's game sums (astra audit item 19).

## 6. Retained comparison bar -- reported as a comparison, not a pass condition

The all-ticks Brier improvement interval is `[-7.042297493210607e-05,
-8.368211469821433e-06]`. Its lower bound `-0.0000704` is above the
preregistered non-inferiority tolerance `-0.0005` (1/8 of the frozen `+0.004`
bar). S293 neither passes nor fails on this: it is a COMPARISON RESULT about
S272's candidate, published because the merged S289/S291 clauses require it.
S293 owns the metric implementation only; S310 owns fitting a candidate.

Read honestly: the interval lies entirely below zero, so the candidate is
measurably BEHIND `recal_null` on Brier, by an amount far smaller than the
`-0.0005` tolerance. The `+0.004` bar is neither met nor moved, and no trial was
charged.

## 7. Tests

    python -m pytest tests/platformkit/test_s293_tail_metric_rail.py -q -p no:cacheprovider
    2 passed in 1.89s     (before the scorer corrections)
    2 passed in 3.53s     (after the scorer corrections)

    python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
    1 passed in 1.34s     (A12; neither S293 file is on the allowlist -- 107 and 193 lines)

The two S293 tests cover the LF seal arithmetic, finite tail log loss on one
archived game, endpoint/clipping arithmetic, mixed-grain refusal, the
trailing-side fixture, and the additive-field attachment.

## 8. Scorer corrections (applied to the lane's own new file, documented)

The lane's first pod dispatch never ran, so these defects were unobserved until
the scorer's first pod run crashed. All three are in
`scripts/platformkit/ingame/s293_tail_metric_replay.py`, a new file under
`scripts/platformkit/**`; no protected route, no test, and no preregistered
definition was changed.

1. `_fine_table` and `_comeback` asked for `incumbent` / `outcome_home_win`,
   which the joined per-tick frame had already renamed to `p_close` / `y`.
   Result was `KeyError: 'incumbent'`; the first pod run died there
   (`/workspace/wt/a14/pod_run_20260907163751.log`, `POD_RUN_DONE rc=1`) AFTER
   the 1e-12 replay assertions had passed and the per-tick CSV had been written.
2. `_fine_table` passed the bin edges `(left, right)` as the reliability-table
   edges for BOTH arms. For `recal_null`, whose probabilities need not lie in
   the market bin, that would have silently dropped every tick outside the
   numeric range -- a circular metric (B1) with an unnamed exclusion set.
   Changed to `(0.0, 1.0)` so each arm is scored over the whole bin mask. The
   market arm is unaffected, its values being inside the bin by construction.
3. ECE was gated on `part["tail"].iloc[0]`, inferring the partition from the
   frame's first row (B7 in miniature). Changed to an explicit `is_tail`
   argument at the two call sites. Behaviour on the tail partition is identical.

Plus one operational change: the per-tick differential is written gzipped. The
uncompressed CSV is 108,436,313 bytes, over the 100 MB hard limit of the public
origin this repo pushes to; gzipped it is 7,071,869 bytes. The prose reference
inside the auto-generated memo was updated to match.

No metric was observed before these corrections -- the crashed run wrote no
summary and no diagnostic table -- so no comparison was selected after seeing a
result.

## 9. Artifacts

| path | bytes | SHA-256 |
|---|---:|---|
| `docs/evidence/harness/S293_tail_metric_rail_2026-09-04_summary.json` | 13,274 | `bc5c72402d41e878139b81be5c9ca42e07bfa7dc6cc5f7b2ad889f481819683a` |
| `docs/evidence/harness/S293_tail_metric_rail_2026-09-04_paired_losses.csv.gz` | 7,071,869 | `8b56123685ffd6a405c9cb60fe33f097608e46414378fe128f9c84bfb4f486ed` |
| `docs/evidence/harness/S293_tail_metric_rail_2026-09-04.md` | 4,110 | `bfb1e2e16db753aafa03dc5211599ecd1d427882aaacba5e846617c9282778da` |

The per-tick differential (Q9) carries `game_id`, `ts`, `split_id`, `n_train`,
`season`, `game_date`, the state columns (`market_prob`, `period`,
`game_clock_s`, `margin`), both arms' probabilities (`p_model`, `p_close`), the
outcome `y`, and both arms' Brier and log losses plus their deltas -- 465,249
rows, so every CI in this memo is recomputable from the artifact alone.
`S293_tail_metric_rail_2026-09-04.md` is the scorer script's auto-generated
memo, regenerated by this run; it previously held the lane's premise-falsified
closure note, which remains in git history at `7be3400dd`.

## 10. Pod run

    /c/Users/neelj/bin/pod_run a14 \
      --ship docs/evidence/harness/S293_tail_metric_rail_prereg_2026-09-07.md \
      --ship docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv \
      --ship docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_summary.json \
      --fetch docs/evidence/harness/S293_tail_metric_rail_2026-09-04_summary.json \
      --fetch docs/evidence/harness/S293_tail_metric_rail_2026-09-04_paired_losses.csv.gz \
      --fetch docs/evidence/harness/S293_tail_metric_rail_2026-09-04.md \
      -- python -m scripts.platformkit.ingame.s293_tail_metric_replay

Job log `/workspace/wt/a14/pod_run_20260907164401.log`, tail:

    S293 verdict=NOT_VALIDATED rss_before=195260416 rss_after=847044608
    POD_RUN_DONE rc=0

Scorer RSS 195,260,416 bytes before, 847,044,608 bytes after (186 MB -> 808 MB);
the process was observed at 799,688 kB RSS mid-run. `pod_run`'s machine-wide
`VmHWM` reading was 2,800,956 kB, which is the peak over all pod processes and
is not attributable to this job alone. `/workspace` 8,101 MB of 50,000 MB used.
`pgrep -af wt/a14` and `wt/a15` were checked before launch and returned only the
checking command itself (D4); no sibling scorer was running, and only
`/workspace/wt/a14` was written.

## NOT VERIFIED

- The S293 spec's own frozen identities `cpcv_engine e0dd8269...` and
  `walkforward 1058f981...` do not exist in this worktree and were never
  reconciled. The verified identities are the preregistration's, which are the
  current bytes. The spec's PREMISE line is FALSIFIED (Q8) and this row proceeds
  on the re-frozen values by continuation instruction, not by re-deriving the
  spec's.
- The S291 frozen count `133,319 ticks / 1,113 games` is not reproduced; this
  corpus yields `133,184 / 1,111`. The 2 missing games were not identified.
- The summary JSON's `trailing_wins` / `trailing_losses` keys are inverted
  relative to their names (section 4). The JSON was not regenerated to fix the
  labels, because the transform they describe is preregistered.
- Independent verifier reproduction in master (contract A1/A2) has not run yet.
  (The committed-byte seal check is DONE -- see the seal section.)
- Repeatability of the pod route: this is one successful run
  (B11). The route is deterministic by construction -- fixed seed in S272's
  bootstrap, no sampling in the S293 sibling -- but a second run was not
  executed.
- No candidate is fit, accepted, or advanced. The `+0.004` bar is unmet and
  unmoved; no trial was charged and no ledger or register file was opened.
- No claim of any kind is made about market efficiency, and none of the metrics
  here is a statement about anything other than calibration.
