VERDICT: CLOSED AT LIMIT (S266 replay bar unmet: cross-environment execution of the Monte Carlo arm) -- measured BEHIND: on all 355 S255-qualified NBA game clusters x 6 frozen targets (n = 2,130), the simulator's calibration improvement over the recalibrated null is -0.10509423986953362 with a game-clustered 95 percent interval of [-0.12175342676604818, -0.08843505297301905], entirely below the untouched frozen +0.004 bar and entirely below zero.

# S287 NBA simulator third arm, full qualified corpus, pod

Spec: `docs/evidence/tracking/specs/S287_spec.md`.
Preregistration: `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04_preregistration.md`,
seal `9dc03d9ef0418c4f3a2e025a06354fd420a84d6ee217b84384463314879ddc64`, sealed at commit
`fbbeca88e` before any S287 metric existed and recomputed here byte for byte from
`git show HEAD:<path>` with CRLF normalized to LF.
Contract self-checked: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.

Both scans were run over this memo and every artifact. This memo returns zero hits on
both. The machine-emitted artifacts return zero hits on the restricted-language scan and,
on the retracted-figure scan, 30 incidental hits in the full-scale trio plus 9 more in the
repeatability tick series, every one a digit substring inside a per-tick loss float written
by the evaluator, never a figure, a claim or a label. Q6 NOTE: machine data, never masked.

This is a measurement, not a retention: no production path, feature flag, registry, ledger K
value, charged trial, `src/` file, `data/registry/` path or input store changed, and the
comparison is uncharged exactly as the preregistration froze it.

## Headline

| Arm | Brier (n = 2,130) | ECE, 10 bins |
| --- | ---: | ---: |
| market (devigged close) | 0.15152952699530517 | 0.023964319248826263 |
| recal_null (incumbent) | 0.15199661253656968 | 0.02432572050776539 |
| simulator (candidate) | 0.2570908524061033 | 0.07932805164319245 |

Metric, exactly as the spec defines it (recal_null Brier minus simulator Brier; positive means the candidate is better):

- improvement = -0.10509423986953362
- game-clustered 95 percent interval = [-0.12175342676604818, -0.08843505297301905]
- frozen bar = 0.004, byte-identical in the spec, the preregistration, the entrypoint constant `BAR` and the emitted summary JSON. No bar was moved.
- verdict = BEHIND (the estimate is negative, so neither AHEAD nor SCREEN_NULL applies).

Q5 is not invoked: this is not an AHEAD result, so no second corpus is required and no SINGLE-WINDOW label applies.

## Does the construct-scale result persist at full scale?

It persists and deepens, and the interval no longer covers zero.

| Scale | clusters | ticks | improvement | 95 percent interval | verdict |
| --- | ---: | ---: | ---: | --- | --- |
| S266 construct | 30 | 180 | -0.07738799835386544 | [-0.1568780916757907, 0.0021020949680598255] | BEHIND |
| S287 full qualified | 355 | 2,130 | -0.10509423986953362 | [-0.12175342676604818, -0.08843505297301905] | BEHIND |

S266 replay delta (full minus construct) = -0.02770624151566818 on the improvement, and the
interval narrows from a width of 0.1589801866438505 to 0.03331837379302913 while moving
entirely below zero. The construct-scale BEHIND did not shrink and did not reverse.

## Every tick, including the simulator's worst periods (non-tautology)

All six frozen targets are reported; none is dropped or filtered.

| target elapsed (s) | n | Brier market | Brier recal_null | Brier simulator | recal_null minus simulator |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 120 | 355 | 0.201024479577 | 0.201459107601 | 0.256417115977 | -0.054958008376 |
| 600 | 355 | 0.185930314085 | 0.186243295801 | 0.253567891725 | -0.067324595924 |
| 1080 | 355 | 0.167749512676 | 0.168147436791 | 0.254980468750 | -0.086833031959 |
| 1560 | 355 | 0.146764935915 | 0.147427845999 | 0.260762819102 | -0.113334973103 |
| 2040 | 355 | 0.123186062676 | 0.123990575241 | 0.254893128301 | -0.130902553060 |
| 2520 | 355 | 0.084521857042 | 0.084711413786 | 0.261923690581 | -0.177212276795 |

The simulator is behind at every target. Its worst period is the latest one, 2520 elapsed
seconds, paired mean -0.177212276795: market and recalibrated null sharpen as a game resolves
while the simulator's Brier stays near 0.25, so the deficit widens across the game. It is not
worse on 520 of 2,130 ticks and 85 of 355 clusters, which is not enough to lift the interval.

## Denominators

- S255 `cluster_qualification.csv` re-measured here (Q8 premise, informational): qualifying =
  355 of 661, and the strict prior-date rule agrees with the stored `qualifies` column everywhere.
- Scored: 355 unique game clusters x 6 frozen targets `[120, 600, 1080, 1560, 2040, 2520]`
  = 2,130 unique game-target state keys. The fetched tick series holds exactly 2,130 rows, 2,130
  unique state keys and 355 unique games; the per-game series holds 355 rows whose `n_ticks` sum
  to 2,130, so the entrypoint's assertions hold on the fetched artifacts.
- Q7: 355 scored game clusters is far above the n >= 30 sampling rail.

## Q9 reproduction from the fetched artifacts alone

Recomputed locally from `S287_selected_tick_series.csv` with the same `scoring.brier`,
`scoring.ece` and `dm_test.diebold_mariano` the run used:

| Quantity | recomputed | max absolute difference vs the summary |
| --- | --- | ---: |
| market Brier / ECE | 0.15152952699530517 / 0.023964319248826263 | 0.0 |
| recal_null Brier / ECE | 0.15199661253656968 / 0.02432572050776539 | 0.0 |
| simulator Brier / ECE | 0.2570908524061033 / 0.07932805164319245 | 0.0 |
| improvement | -0.10509423986953359 | 2.7755575615628914e-17 |
| 95 percent interval | [-0.12175342676604815, -0.08843505297301903] | 3e-17 scale |

## Leak contract (Q4)

Every scored probability came from one shared `cpcv_evaluate` state per tick, with
`n_groups=8`, `n_test_groups=1`, `strict_redaction=True`, a symmetric nonzero three-calendar-day
embargo, and a callback value for every scored tick. The run asserted one emitted record per grid
tick and a one-to-one merge back; both assertions passed and the fetched series reproduces them.

## Inputs opened (A9), identity and md5 parity

Every input was opened read-only, one store at a time. The run recorded each input's SHA-256
before and after scoring and they are equal, so no input changed under the run. The values below
were recomputed on this machine and on the pod after the run finished.

| Input | Bytes | Shape | SHA-256 (local == pod) | md5 (local == pod) |
| --- | ---: | --- | --- | --- |
| `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv` | 38,630,145 | tabular CSV, 79,554 ticks / 661 clusters | `f498a7a040201571270183a79a025cd87d91ed5060f244b69964a150eab7d0f6` | `4a294f43f029b2aae2ffc776d90dd81c` |
| `docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/cluster_qualification.csv` | 36,282 | tabular CSV, 661 clusters | `826f778104453f75bdf1e7517c2f0650bfa0a322318a346ca3a26df1575f487e` | `d56f07a199a5585cd00f978a65386f2b` |
| `docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/player_rate_snapshots.parquet` | 565,095 | tabular Parquet | `0d0697b7402907ed493b429d1f0f44e7afad85ec1aa14019a83e1c24e80f6d6e` | `4a0ce91bea3cbbfef7995f35deb8a51b` |
| `docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/team_rate_snapshots.parquet` | 22,677 | tabular Parquet | `42932c26f308097afbc1187aed2e9e8e2efb176258f213e1c5e492a270e5c00e` | `6e8df6951c7ecc7bc97e30fad8439c30` |

md5 parity is 4 of 4, computed on both sides. The three S255 stores are carried in the summary's
`input_md5_pod` field; the S92 archive is outside it by construction and was confirmed separately.

Correction carried forward from the previous scorer, for the record: the landed S266 memo printed
the player-parquet SHA-256 with only 63 hexadecimal characters. The true value is
`0d0697b7402907ed493b429d1f0f44e7afad85ec1aa14019a83e1c24e80f6d6e`, reproduced here on both
machines: a transcription defect in S266, not a change of input.

## Code identity (A11) and the must-not-move set

| File | SHA-256 recorded by the run | SHA-256 in this worktree now |
| --- | --- | --- |
| `scripts/platformkit/ingame/s256_nba_sim_engine_v3.py` | `757b2bd9f88a85fe68da97c6fcb275b1b44e5f4926a801265eb7f6c7cc951e12` | identical |
| `scripts/platformkit/ingame/s287_sim_full_pod.py` | `b0eec530328e84272060e32f6b1f87e0dfa3d2f11db182608879ff3fad832118` | identical |

The landed S266 module was imported unchanged; its last commit is still `afb5a9460`. Nothing under
`src/` was touched, the S255 artifacts and the S92 archive were opened read-only, and `recal_null`
defaults were not altered. The entrypoint is 119 lines and its test 73 lines after the
repeatability assertion below, both within the 300-line rail.

## Where it ran, and the run itself

The pod scratch worktree `/workspace/wt/a13`, launched through `~/bin/pod_run` in its
2026-09-07 pre-operations form (preserved as `~/bin/pod_run.bak_2026-09-07_preops`), whose
remote root is the worktree itself. That launcher was replaced on the local box 26 minutes
after the job started, which is why the job has no `jobs/<id>` root and why the client's
automatic fetch never ran; the outputs were fetched by `scp` from the path the
preregistration names and compared by SHA-256 on both sides.

- Sealed command, run exactly once, no relaunch:
  `pod_run a13 --ship docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04 --fetch <the three outputs> -- python -m scripts.platformkit.ingame.s287_sim_full_pod`.
  The one deviation is that the preregistration's single `--fetch <directory>` was expanded
  to the three concrete output files, because the launcher's `scp` has no recursive flag.
- Started 2026-09-07 22:17:44Z, finished 2026-09-08 07:41:20Z: wall time 9 hours 23 minutes,
  process CPU time 4 days 18 hours at roughly 10 to 12 cores, because the pod was heavily
  contended for much of the first half. That is about twice the 4-to-5-hour dispatching
  estimate; neither the spec nor the preregistration sets a wall budget, so no bar moved.
- Exit status `POD_RUN_DONE rc=0`. Pod RSS: 257.66 MB before scoring, 707.25 MB peak.
- Pod log tail, verbatim:

```text
ARM market BRIER 0.151529526995 ECE 0.023964319249
ARM recal_null BRIER 0.151996612537 ECE 0.024325720508
ARM simulator BRIER 0.257090852406 ECE 0.079328051643
CI95 -0.121753426766 -0.088435052973
RSS PEAK 707.25 MB
POD MD5 {"player": "4a0ce91bea3cbbfef7995f35deb8a51b", "qualification": "d56f07a199a5585cd00f978a65386f2b", "team": "6e8df6951c7ecc7bc97e30fad8439c30"}
FINAL SHA fb823ca4fbccdb80dc2d37008128ecc62064040128e7a3c20a18032957719aee
POD_RUN_DONE rc=0
```

## Premise notes carried from the dispatch (Q8, S2)

- The S92 archive was absent from the reallocated pod's deployed tree. It was copied once into the
  lane scratch at `/workspace/wt/a13/data/cache/eval_gate/`, md5 and SHA-256 equal on both sides.
  That directory holds that one file and nothing else: no `backtest_fwer.jsonl`, no
  `hypotheses*.sqlite`, and no `/workspace/wt/a13/data/registry`.
- `/workspace/nba-ai-system`, the deployed pod tree, was never written by this row; a search of it
  returns no path containing `S287`. Its recent mtimes come from the live paper-node daemons.
- The S255 qualifying count and the S266 construct numbers were both re-measured here before any
  S287 number was read, and both reproduced.

## The S266 replay condition is unmet, and the cause is now attributed

The spec's TEST is that restricting to S266's sealed 30 clusters reproduces S266's
archived numbers from the fetched series to within 1e-9. It does not. The largest
difference over the metrics is 0.04175347222222213, on the simulator's ten-bin ECE;
0.006218804253472238 is the simulator-Brier difference alone, which is also the
difference on the improvement (restricted -0.07116919410039321 against S266's archived
-0.07738799835386544). The market and recalibrated-null arms reproduce at exactly 0.0.

What was measured, restricting the fetched full series to the 30 S266 clusters and
merging one-to-one onto S266's archived tick series (180 of 180 rows merged):

| Column | Rows differing by more than 1e-12 |
| --- | ---: |
| `game`, `ts`, `elapsed`, `outcome_home_win`, `home_five`, `away_five` | 0 of 180 |
| `market_prob`, `p_null`, `loss_market`, `loss_recal_null` | 0 of 180 |
| `cluster_id`, `source_order`, `distance`, `grid_target_elapsed`, the three dates | 0 of 180 |
| `p_simulator`, `loss_simulator`, `paired_loss_recal_null_minus_simulator` | 171 of 180 |
| `n_train` | 180 of 180 (expected: fold sizes differ between 180 and 2,130 states) |

So every deterministic column reproduces bit for bit and only the Monte Carlo arm moves.
Its differences lie on the simulator's own 1/64 draw lattice (N_SIMS = 32 with half-credit
ties), median absolute difference 0.09375, maximum 0.359375, mean signed difference
-4.079861e-03 -- the scale of independent resampling noise at 32 draws.

## Repeatability experiment, 2026-09-08

The design was sealed first and alone in
`docs/evidence/harness/S287_repeatability_prereg_2026-09-08.md`, seal
`acc0c31dd04a0ae3785169f80e668dd7378bbee95f300313eea59835cca60673`, commit `8e2b79856`,
before any comparison below was read. The same route, restricted by `--game-ids` to the same
30 S266 clusters, n = 30 clusters and 180 ticks per run, ran three times: twice in sequence on
the pod (22 min 47 s and 18 min 0 s wall, 692.48 MB and 692.22 MB peak RSS), once locally in
the interpreter the landed S266 memo names (about one minute, 489.90 MB). Only
`/workspace/wt/a13/repeat/` was written on the pod and no running daemon was touched.

| Run | Environment | simulator Brier | simulator ECE | improvement |
| --- | --- | ---: | ---: | ---: |
| POD-1 | pod, python 3.12.3, torch 2.8.0+cu128, numpy 2.1.2, 128 threads | 0.2496853298611111 | 0.09340277777777779 | -0.07116919410039321 |
| POD-2 | the same pod, immediately after POD-1 | 0.2496853298611111 | 0.09340277777777779 | -0.07116919410039321 |
| LOCAL-1 | local, python 3.10.20, torch 2.1.2+cu121, numpy 1.26.4, 6 threads | 0.25590413411458335 | 0.13515624999999992 | -0.07738799835386544 |
| S266 archive | the local interpreter S266 names | 0.25590413411458335 | 0.13515624999999992 | -0.07738799835386544 |

| Pair | largest metric difference | ticks differing by more than 1e-9 | agrees at 1e-9 |
| --- | ---: | ---: | --- |
| POD-1 vs POD-2 | 0.0 | 0 of 180 | yes, byte-identical series |
| POD-1 and POD-2 vs the full-scale rows restricted to those 30 clusters | 0.0 | 0 of 180 | yes |
| LOCAL-1 vs the S266 archive | 0.0 | 0 of 180 | yes |
| POD-1 vs LOCAL-1 | 0.041753472222222129, simulator ECE | 171 of 180 | no |

The preregistered decision table returns its first row: the route is repeatable inside one
environment and the difference is cross-environment. Both pod runs emitted the same tick series
byte for byte (SHA-256 `690d1017e8dd63cc4003e986d7ea0bfdf5f367e84807e626aedce8c4026e4a2b`) and
the local run replays the S266 archive exactly, so the attributed cause of the replay miss is
cross-environment execution, acting on `p_simulator` alone.

Two earlier statements are corrected by this. Selection scale is not involved: POD-1 selected 30
clusters and still reproduced the 355-cluster run's rows for them exactly. And this worktree can
execute the simulator locally; the earlier `RuntimeError: Numpy is not available` came from a different interpreter, not from the environment S266 names.

The verdict is unaffected in direction or magnitude: the discrepancy is noise-scale on the arm
that is behind by -0.105, its mean signed size is -4.079861e-03, and both intervals sit below
the frozen bar. It is reported as a failed spec condition, not adjusted away; the 1e-9
tolerance was not moved, so the row closes at that limit instead of claiming replay.

## Evidence artifacts

All three are under 50 MB and committed. The S92 archive is a `data/` path, stays out of git by rule, and is identified by SHA-256 and pod path above.

| Artifact | Bytes | SHA-256 (local == pod) |
| --- | ---: | --- |
| `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_summary.json` | 994,392 | `fb823ca4fbccdb80dc2d37008128ecc62064040128e7a3c20a18032957719aee` |
| `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_selected_tick_series.csv` | 628,595 | `b5fd6da88fbde7edfe3113ca25f783cc8a899d0e1f87f97adf1a3218e3a7fbb9` |
| `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_per_game_paired_loss_series.csv` | 33,690 | `30f7e49749e6141fbcefa3629bf482565b9643dc57a45b1668cae902da152155` |

The repeatability outputs are committed beside them under
`docs/evidence/harness/S287_repeatability_2026-09-08/`: the tick series and summary of POD-1, POD-2 and LOCAL-1, six files, each well under 5 MB.

Pod path of the archive that stays out of git:
`/workspace/wt/a13/data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv`,
38,630,145 bytes, SHA-256 `f498a7a040201571270183a79a025cd87d91ed5060f244b69964a150eab7d0f6`.

## NOT VERIFIED

- Which layer inside the two environments produces the differing draw sequence. The measurement
  localizes it to `p_simulator` and to the pair of environments; it does not name a library call.
  Ruled out earlier and still ruled out: the per-state seed `int(game) % 2147483647 + int(grid_target_elapsed)` is a pure function of tick identity,
  `src/sim/fast_sim.py:178` seeds a per-call generator, the seeded CPU stream matches across the two builds, and the
  league-mean IEEE-754 bit patterns hash to `6a749fce...` and `fda92cf0...` on both machines and at both selection scales.
- Independent verifier reproduction of any number in this memo.
- Every peak RSS quoted is the value the run printed; none was sampled by an independent
  observer.
- Whether the simulator's deficit would narrow under a different `N_SIMS`, a different grid or a
  corpus other than the S255-qualified NBA clusters. This is a one-corpus BEHIND.

## NEW GAPs

- The per-game series stores a state key such as `401809239:120` in its `timestamp` field, and
  that file carries no probabilities and no outcomes, so ECE cannot be recomputed from it alone;
  the tick series is the only artifact that supports the Q9 recomputation. Raised by the verifier,
  outside that verdict's Q9 scope, and not repaired here: no archived artifact may be rewritten.
- The S92 archive was staged on the pod at `/workspace/wt/a13/data/cache/eval_gate/` instead of
  the preregistered scratch `inputs/` location. Disclosed: both are lane scratch, no
  deployed-tree write occurred, and the file's md5 and SHA-256 matched on both sides.

## Proposed RESULTS_LEDGER_SYSTEM row, for the lander to append

2026-09-04 | in-game calibration | S287 | 355 clusters / 2,130 targets (n = 2,130): simulator minus recalibrated-null calibration improvement -0.1050942399, 95 pct CI [-0.1217534268, -0.0884350530], below the frozen 0.004 bar; the 30-cluster replay is unmet by 0.0417534722 (largest metric difference, simulator ECE), with the route measured repeatable inside each environment over n = 3 runs (pod run 1 equals pod run 2 byte for byte, local equals the S266 archive) and differing only across environments | CLOSED AT LIMIT

## Time spent

The pod compute ran 9 hours 23 minutes of wall time. That finishing pass spent about 3 hours
35 minutes, roughly 3 hours 15 minutes of it blocking on the pod job without killing or
relaunching it and about 20 minutes on fetching, reproduction, the failure diagnosis and this
memo. The 2026-09-08 repeatability pass added about one hour, nearly all of it waiting on the
two sequential pod runs.

Vocabulary follows contract Q6; automated scan required.
