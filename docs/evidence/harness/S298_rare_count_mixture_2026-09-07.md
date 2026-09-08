VERDICT: BEHIND -- the fixed six-comparison bar is NOT met. Holm-adjusted paired 95 percent lower bounds are positive on 2 of 6 (STL/NB2 +0.002132, BLK/NB2 +0.002133) and decisively negative on the other 4 (hurdle-NB2 and ZINB on both stats, -0.36 to -0.50 discrete log-score units). The bar requires all six, so S298 fails it; the bar was not moved.

# S298 rare-count mixture comparison (2026-09-07, attempt 2)

This is a SINGLE-WINDOW calibration comparison on one corpus window. Improvement
is Poisson log score minus candidate log score in discrete log-score units;
positive means the candidate carries the lower loss. This is a calibration
comparison only; no market or monetary quantity is measured or claimed here. The
NBA Brier bar +0.004 is not this comparison's threshold either: count log scores
have their own units. A BEHIND result is a valid, honest outcome.

## Preregistration and candidate lineage (verifier CORRECTION 2)

The sealed preregistration
`docs/evidence/harness/S298_rare_count_mixture_2026-09-07_prereg.md` EXISTS as
commit `287ae3aca`, with LF-normalized bytes-above-seal SHA-256
`906ef129f74c860192046e1c60d21fffb2dd9c98a780efc766f2b30597be082b`; the scorer
recomputed that seal at launch and the run aborts on any mismatch. The attempt-1
candidate EXISTS as commit `99d4e78c9`; the verifier rejected it in
`docs/evidence/harness/S298_VERIFY_2026-09-07.md` because no scored headline
could be reproduced. The attempt-1 memo,
`docs/evidence/harness/S298_rare_count_mixture_2026-09-04.md`, is retained
unrewritten as that attempt's record; this file is the new dated memo and does
not replace it.

The verifier's CORRECTION 1 (emit secondary summaries and per-fold cluster
counts/assertions) is applied. One further change was required, so a
preregistration SUPPLEMENT
`docs/evidence/harness/S298_rare_count_mixture_2026-09-07_prereg_supplement.md`
(seal `fa854d69bb279e4570403005ac7a7b593b74629bd2d9125de1315e9a369e5a8a`) was
sealed and committed ALONE before the first metric, per contract Q1. The sealed
preregistration 287ae3aca otherwise governs UNCHANGED: the same premise, the
same two source parquets, the same four families, the same PMF support and tail
cutoff 20, the same six fixed comparisons, the same sign convention, and the
same Holm-adjusted paired 95 percent lower-bound bar.

The supplement's substantive clause: the sealed preregistration records the
inner strictly-past walk-forward selection "per stat and outer fold", but
candidate 99d4e78c9 recomputed it once per held-out state. Measured on this
corpus that is 132,952,773 prior-window PMF fits at 41.7 us each, about 12.3
hours, past the pod job budget. It is now computed once per stat and outer fold
and stamped on every forecast in that fold. It remains a diagnostic only: it
removed, omitted and relabelled no outer comparison, and every family including
the worst is published below.

## Binding premise, re-measured inside the scoring process

| Path | Bytes | SHA-256 | Rows | Resolution | First three (game_id, player_id) | STL zeros | BLK zeros |
|---|---:|---|---:|---|---|---:|---:|
| `data/domains/basketball_nba/player_boxscores.parquet` | 1118538 | `9590d276e075309a181b0c4cb46e9d157dc2ab9f340cfeb63c07a0cba7252152` | 77744 | tabular; not applicable | `('0022300001', 202684)`, `('0022300001', 1627747)`, `('0022300001', 1627777)` | 40520 | 53267 |
| `data/cache/omni_box_refresh/nba_player_box_extension.parquet` | 34147 | `d18f69c03d6fd8b00bd3d4cf047a112ffc651b614cadb4e27c07badbf8393e94` | 1023 | tabular; not applicable | `('0042500121', 203468)`, `('0042500121', 203903)`, `('0042500121', 1626157)` | 669 | 799 |

Required 40,520 / 53,267 and 669 / 799: reproduced exactly. The premise is not
falsified. The pod copies of both parquets are byte-identical to the local
copies (same sizes and SHA-256 values), so no source was shipped and no source
path was overridden.

## The six fixed comparisons

Union corpus 78,767 player-games over 3,645 game clusters; purged CPCV, five
date groups, one held-out group per fold, symmetric one-day embargo; every
source state held out exactly once. Bootstrap of game-cluster means, seed 298,
4,000 resamples. Holm step-down over the six comparisons.

| Stat | Family | Held-out states | Game clusters | Mean improvement | Paired 95 pct CI | Holm-adjusted 95 pct lower bound | Holm alpha | One-sided p | Meets bar |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| stl | nb2 | 78767 | 3645 | 0.003408 | [0.002468, 0.004354] | 0.002132 | 0.004167 | 0.00000 | YES |
| stl | hurdle_nb2 | 78767 | 3645 | -0.466006 | [-0.494721, -0.437065] | -0.503716 | 0.006250 | 1.00000 | NO |
| stl | zinb | 78767 | 3645 | -0.450305 | [-0.478679, -0.421303] | -0.484667 | 0.008333 | 1.00000 | NO |
| blk | nb2 | 78767 | 3645 | 0.003191 | [0.002347, 0.004031] | 0.002133 | 0.005000 | 0.00000 | YES |
| blk | hurdle_nb2 | 78767 | 3645 | -0.348459 | [-0.371226, -0.326352] | -0.374532 | 0.012500 | 1.00000 | NO |
| blk | zinb | 78767 | 3645 | -0.339889 | [-0.362794, -0.317485] | -0.362794 | 0.025000 | 1.00000 | NO |

No family was omitted after scoring, and none was dropped or relabelled. The
bar is "Holm-adjusted paired 95 percent lower bound greater than 0 over all six
stat x family comparisons". Four of the six lower bounds are far below zero, so
the bar fails: BEHIND. The bar was not lowered, and no subset of the six is
reported as though it were the bar.

The measured direction is that the strictly-past NB2 dispersion correction buys
a small but interval-positive log-score reduction over the strictly-past Poisson
on both rare counts, while the two zero-handling families -- hurdle-NB2 and
ZINB -- are decisively worse than Poisson on both. Their loss comes from the
positive tail: pinning the zero mass to the strictly-past empirical zero rate
leaves too little mass on the observed nonzero counts.

## Secondary diagnostics (verifier CORRECTION 1)

| Stat | Family | Mean log score | Mean RPS | Predicted zero mass | Observed zero rate | Zero reliability abs error | Mean per-state zero abs error | Randomized PIT mean | PIT KS vs uniform |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| stl | poisson | 3.933082 | 0.024226 | 0.625938 | 0.522922 | 0.103016 | 0.454419 | 0.555937 | 0.114973 |
| stl | nb2 | 3.929593 | 0.024218 | 0.640706 | 0.522922 | 0.117784 | 0.454110 | 0.561303 | 0.109240 |
| stl | hurdle_nb2 | 4.394037 | 0.024272 | 0.638102 | 0.522922 | 0.115180 | 0.454287 | 0.559931 | 0.108350 |
| stl | zinb | 4.377994 | 0.024245 | 0.646209 | 0.522922 | 0.123287 | 0.454358 | 0.562562 | 0.109587 |
| blk | poisson | 2.783758 | 0.016441 | 0.739530 | 0.686404 | 0.053126 | 0.361383 | 0.526997 | 0.078199 |
| blk | nb2 | 2.780358 | 0.016397 | 0.752455 | 0.686404 | 0.066051 | 0.358390 | 0.531801 | 0.073707 |
| blk | hurdle_nb2 | 3.127684 | 0.016424 | 0.750268 | 0.686404 | 0.063864 | 0.359223 | 0.531993 | 0.073402 |
| blk | zinb | 3.118985 | 0.016395 | 0.755860 | 0.686404 | 0.069456 | 0.357868 | 0.533466 | 0.074163 |

The secondary diagnostics agree with the primary metric in ordering but are far
less separated: RPS moves only in the fourth decimal across all four families,
and every family OVER-predicts the zero rate (predicted zero mass exceeds the
observed zero rate by 0.053 to 0.123, absolute). Randomized PIT means all sit
above 0.5 with KS distances from uniform of 0.073 to 0.115, so NONE of the four
families is well calibrated on these rare counts; the NB2 result is a relative
win inside a uniformly mis-calibrated set. That is a calibration statement, not
a claim of sufficiency.

## Per-fold n rail (verifier CORRECTION 1)

The spec rail is every held-out player-game and at least 30 held-out game
clusters per fold. The route asserts the 30-cluster rail itself; the shared
evaluator does not implement it, contrary to the preregistration's description,
and the supplement records that correction.

| Fold | Held-out states | Held-out game clusters | Train states | Rail (>= 30 clusters) |
|---:|---:|---:|---:|---|
| 0 | 16705 | 775 | 61813 | PASS |
| 1 | 17522 | 812 | 60965 | PASS |
| 2 | 16088 | 755 | 62156 | PASS |
| 3 | 16624 | 768 | 61568 | PASS |
| 4 | 11828 | 535 | 66687 | PASS |

Total 78,767 held-out states over 3,645 game clusters, every state held out
exactly once. No row was excluded after its outcome was known.

## Declared limit: cold-start dilution, measured not inferred

Every fit uses only train states STRICTLY EARLIER than the test state, while the
CPCV train set straddles the test block on both sides. The earliest date group
therefore has no strictly-past train state at all. Measured from the PMF
archive, 16,705 held-out states (fold 0, 21.2 percent of the corpus) have
`asof_n == 0`: all four families collapse to the same near-degenerate point mass
at zero there, and their paired improvement is approximately zero by
construction. A further 1,395 / 221 / 1,702 / 192 states in folds 1-4 have no
strictly-past record for that player and fall back to the strictly-past league
pool (`used_player_prior == 0`). These states are RETAINED in every denominator
and reported here; none was dropped after its outcome was known. The effect
shrinks every mean improvement toward zero and is a limit of the sealed design,
stated rather than corrected after the fact.

The inner strictly-past walk-forward selection returned `nb2` for both stats in
all five outer folds -- exactly one value per stat and fold, as the supplement
fixed. It gated no outer comparison.

## Machine, cost and rails

Run once, CPU only, on the pod, job `S298_attempt2_20260907` under
`/workspace/wt/a10/jobs/S298_attempt2_20260907`, launched as
`pod_run a10 --ship <prereg> --fetch <3 outputs> -- python -m scripts.platformkit.s298_rare_count_mixture`.
No GPU; the 16-worker tracking daemon shared the box throughout, and the scorer
held roughly 16 percent of one core under that contention.

- Wall time 6054.394977901131 s (100.9 min); remote rc=0.
- RSS before 189.1953125 MB; RSS after 2674.203125 MB. Under the 8 GB rail.
- Route SHA-256 at run time (contract A11):
  `scripts/platformkit/s298_rare_count_mixture.py` =
  `aeae95b5e80164e1c80411d7d761590aa3cfcd5e76daeee7291a5dbd25c3037e`;
  `scripts/platformkit/eval_gate/cpcv_vector_distribution.py` =
  `5217dd0dab015efc2d0795b4b3e39830ce4209d59146d3d810b508026bb7aee0`;
  `scripts/platformkit/eval_gate/cpcv_engine.py` =
  `5accfbe490031acb084a8e4375a082b00d842cf4011a76c6d27dfc2c7db614a5`.
- No deployed pod tree, source store, `data/` path, register or feature flag was
  written. No push.

## Test

Two independent commands (verifier correction: list separately, not combined):
- `python -m pytest tests/platformkit/test_s298_rare_count_mixture.py -q -p no:cacheprovider --confcutdir=tests/platformkit`
  -> `3 passed`. Checks the preregistration seal, finite PMFs, PMF sums, zero
  support and tail finiteness across all four families, strict-prior feature
  availability, the eight secondary-diagnostic rows, the per-fold rail raising
  below 30 held-out game clusters, and (new) that
  `s298_pmf_shards.load_pmf_shards` streams the canonical hash and
  `shard_manifest()` reconstructs the committed manifest from the 8 shards
  (skips with a clear message when available RAM is under 1 GB).
- `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests/platformkit`
  -> `1 passed`.

`scripts/platformkit/s298_rare_count_mixture.py` is 300 LOC, at the rail; no
allowlist entry was added. `scripts/platformkit/s298_pmf_shards.py` is 117 LOC.

### B2 correction (verifier REJECT on fix 2c, `d6ff90e22`)

The verifier rejected fix 2c because `artifacts.pmfs` changed from a filename
scalar to the shard-manifest object with no alias, while the scorer still
emitted the scalar. Fixed here: `artifacts.pmfs` is restored to the scalar
filename `S298_rare_count_mixture_2026-09-07_pmfs.csv.gz`; the shard manifest
moves, unchanged, to the sibling key `artifacts.pmf_shards`. The scorer now
builds this exact shape itself -- `pmf_shard_artifacts()` in
`scripts/platformkit/s298_pmf_shards.py` returns `{"pmf_shards": ...}` when
all 8 committed shards are present on disk (re-validating the streamed
reconstruction first) and `{}` otherwise, so a fresh, not-yet-sharded run
keeps the original scalar-only contract. Re-run in this session:
`python -c "import json; from scripts.platformkit.s298_pmf_shards import pmf_shard_artifacts; d=json.load(open('docs/evidence/harness/S298_rare_count_mixture_2026-09-07.json')); print(pmf_shard_artifacts()['pmf_shards']==d['artifacts']['pmf_shards'])"`
-> `True`: the manifest the scorer would emit today equals the one committed.
`load_pmf_shards` was also rewritten to stream the reconstruction one shard
(gzip member) at a time, hashing line-by-line instead of materializing the
full ~329 MB decompressed archive (and a joined-rows copy) in memory; it adds
a decompressed-byte-count assertion (328969124) alongside the existing row
count and SHA-256 checks.

## Reproduction from the archive alone (contract A2, Q9)

Recomputed in this session from
`S298_rare_count_mixture_2026-09-07_paired_losses.csv.gz`, with no model re-run:
472,602 paired rows over 78,767 unique player-game keys; the identity
`poisson_log_loss - candidate_log_loss - improvement` has maximum absolute
residual 3.774758283725532e-15; and all six game-cluster mean improvements
reproduce the JSON headline to six decimals. The PMF archive replays every
family's integer PMF over support 0..20 plus `pmf_tail_gt_20`, with ids, dates,
observed count, zero flag, split id, `asof_n`, `used_player_prior` and the
inner-selected family.

### Reassembled from the committed shards (verifier CORRECTION, durability fix)

The PMF archive is now committed as 8 row-range shards (below); nothing outside
this repo is required to replay it. `scripts/platformkit/s298_pmf_shards.py`
decompresses and concatenates the 8 shards in name order and asserts the
result is exactly 630,136 rows with canonical decompressed SHA-256
`c6e2db5f8a9b5a8ee0f524088043274d77539af06cf8fdb2e072705a7ab5c161` (the
original whole-archive SHA-256 `b9da5f26...` stays the canonical reference for
the pre-sharding bytes; it hashes the gzip container, not the decompressed
CSV, so it is not itself re-derivable from the shards, which is why the
decompressed-content hash above is the one the reader checks). Re-run in this
session from the reassembled shards, with no model re-run:
- `python -m scripts.platformkit.s298_pmf_shards` ->
  `S298_PMF_SHARDS_OK rows=630136 sha256=c6e2db5f8a9b5a8ee0f524088043274d77539af06cf8fdb2e072705a7ab5c161 bytes=328969124`.
- Loading all 630,136 shard-reassembled PMF rows and the unchanged
  `_paired_losses.csv.gz` together: 472,602 paired rows over 78,767 unique
  keys; loss-identity maximum absolute residual 3.774758283725532e-15
  (unchanged, re-quoted above); all six game-cluster mean improvements
  reproduce the JSON headline to six decimals (stl/nb2 0.003408, stl/hurdle_nb2
  -0.466006, stl/zinb -0.450305, blk/nb2 0.003191, blk/hurdle_nb2 -0.348459,
  blk/zinb -0.339889).
- Recomputing each row's discrete log score directly from the shard-reassembled
  PMFs (`pmf_0..pmf_20`, `pmf_tail_gt_20`, `observed`) and comparing to the
  poisson/candidate log-loss columns in `_paired_losses.csv.gz` for all three
  non-Poisson families: maximum absolute residual 7.460698725481052e-13
  (floating-point summation order only; well inside the 1e-12 tolerance
  applied elsewhere in this memo).

## Artifacts

| Artifact | Bytes | SHA-256 | In git |
|---|---:|---|---|
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07.json` | 10955 | `0530cdf2072bd1e7c459a353d88f881916830e45fdb2c324eb0913f9ecd2b668` | yes |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_paired_losses.csv.gz` | 7310563 | `9de25558752aa7567ffae32e3c38bb51b30a2227e491354e941646bea2ac8dd2` | yes |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_pmfs_part01.csv.gz` | 439588 | `10bb38ff6bc334cf73a3269c8ad4e4477e3cf5152d9e9aeff0c6245f049e0b5b` | yes |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_pmfs_part02.csv.gz` | 3690587 | `3c053711b290b97bc658b6bacfb2b86b9fc663edca6699709d5e787f90afbdee` | yes |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_pmfs_part03.csv.gz` | 10694405 | `7f7f6c93b40809c3c90324d5983c9c4e548f8d152dbeb07bd93604740f0bd791` | yes |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_pmfs_part04.csv.gz` | 11118146 | `90bfaa5e7d9ae050f125d58bcd1769f7926b4469241f3d3dd0669bfd6ed1ef40` | yes |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_pmfs_part05.csv.gz` | 11763949 | `810c6288dcc6a16b9ca72d42d7e92b02cf03d0728ee5698f709a67f4aa055f0e` | yes |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_pmfs_part06.csv.gz` | 11771831 | `2290dd73169f95c920cbc5e1d97440cdd8dc2a1687d6c5de5a62146264afc9a6` | yes |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_pmfs_part07.csv.gz` | 11713094 | `195021cbfb7523b38efe06526e862212f2834e222a53b83efcdd8d262c93e48d` | yes |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_pmfs_part08.csv.gz` | 12322806 | `2eaf44a9c4f0731c9eda482c92bc6dd2100553a033be20cd79312c57f9f9bee3` | yes |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_prereg.md` | 5077 | `9ecf6f2ce4381cc1e17eb757def7b935963c51483c1156160f41acfb27ef6f01` | yes (287ae3aca) |
| `docs/evidence/harness/S298_rare_count_mixture_2026-09-07_prereg_supplement.md` | 3941 | `11d02ec3ac40ab266d28d3043a74604f4e43c26277e16f7608e665ba71e8278a` | yes |

The three text artifacts (`.json`, `.md`) are hashed as their LF-normalized
bytes; git stores them LF-normalized, so re-hash after normalizing CRLF to LF
if a fresh checkout disagrees. The `.csv.gz` archives are binary and their
SHA-256 values are checkout-independent.

The whole PMF archive is 73,504,906 bytes with SHA-256
`b9da5f26db957289ccf699e0e0dd604cab08f13c1b894ad7b974a191a5f9801e` (the
canonical reference for the pre-sharding bytes) and stays out of git by size,
as S296 did with its paired-losses archive -- but unlike S296, it is no longer
absent from a clean checkout: it is committed here as the 8 row-range shards
above (largest 12,322,806 bytes, all under the 45 MB commit rail), which
`scripts/platformkit/s298_pmf_shards.py` reassembles and verifies against
canonical decompressed SHA-256
`c6e2db5f8a9b5a8ee0f524088043274d77539af06cf8fdb2e072705a7ab5c161` and row
count 630,136 (see "Reassembled from the committed shards" above). The
uncommitted whole archive remains present in the a10 worktree at
`docs/evidence/harness/S298_rare_count_mixture_2026-09-07_pmfs.csv.gz` purely
as a local convenience; the pod copy is
`/workspace/wt/a10/jobs/S298_attempt2_20260907/docs/evidence/harness/S298_rare_count_mixture_2026-09-07_pmfs.csv.gz`.

## Corrections applied at landing

Both items come from the verifier memo
`docs/evidence/harness/S298_VERIFY_2026-09-08.md` (verdict ACCEPT WITH
CORRECTIONS, verifier codex-sol, contract A/B/Q) and were applied by the lander
before this memo was committed to master.

1. CORRECTION (codex-sol): the artifact table's byte counts and SHA-256 values
   for the `.json` and `.md` artifacts were labelled as on-disk Windows
   working-copy bytes. They are LF-normalized bytes -- the recorded 10955 /
   `0530cdf2...` for the JSON reproduce only after CRLF-to-LF normalization,
   while the Windows working copy is 11293 bytes / `242e7acf...`. The paragraph
   above the table now says LF-normalized bytes. The recorded numbers
   themselves are unchanged and correct.
2. NEW GAP (codex-sol): the "Tests" section above claimed the test reconstructs
   the committed manifest, but the test asserted only row and shard counts. An
   exact JSON-manifest equality assertion was added to
   `tests/platformkit/test_s298_rare_count_mixture.py`: it compares
   `s298_pmf_shards.pmf_shard_artifacts()["pmf_shards"]` against the committed
   `artifacts.pmf_shards` object in
   `docs/evidence/harness/S298_rare_count_mixture_2026-09-07.json`. The test was
   re-run on master after the change and passes.

## NOT VERIFIED

- Any second corpus. This is one window; Q5 makes the verdict SINGLE-WINDOW, and
  no AHEAD is claimed for any family, including the two NB2 comparisons whose
  Holm-adjusted lower bounds are positive.
- Any behaviour for players or seasons outside these two parquets, and any
  transfer to other rare counts (turnovers, personal fouls, three-point makes).
  Only STL and BLK were scored.
- Whether the 21.2 percent cold-start fold-0 dilution changes the sign of any
  comparison. Re-scoring on a strictly-past-only outer design was NOT run and is
  not implied by these numbers.
- Any dispersion or zero-inflation model beyond the four sealed families
  (Poisson, NB2, hurdle-NB2, ZINB) with strictly-past moment estimators. No
  covariate model, no shrinkage and no likelihood fit was attempted.
- Repeatability of the pod route across runs; this is one execution (B11). The
  route is deterministic given the archived seeds and route hashes, but that was
  not demonstrated by a second run.
- The calibration sufficiency of ANY of the four families. All four over-predict
  the zero rate, and all four have randomized-PIT KS distances of 0.073 to 0.115
  from uniform.
