# S205 Calibration Bakeoff Attempt 2 Preregistration

Scope: calibration-only evidence over every finite corpus probability with a binary `y` in the read-only NBA, MLB, soccer, and tennis gate corpora. The named denominators are NBA 1814, MLB 39162, soccer 25834, and tennis 41886. No row may be dropped because of a calibrator result.

Arms: every sport scores exactly these three arms: `isotonic`, `temperature`, and `beta`. All arms use the existing `buckets` regime keys, `min_history=200`, the same raw probability column selected by the S05 report, and the same raw rows. Isotonic uses the existing `fit_per_regime` global fallback. Temperature is a single logit scale maximum-likelihood fit. Beta is the fixed three-parameter beta-map maximum-likelihood fit. No arm is tuned after this seal.

OOS design: every arm is evaluated through `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` with `n_groups=8`, `n_test_groups=1`, and `embargo_days=1`. The engine applies its same-team and matchup purge and its symmetric calendar-day embargo. Event dates are normalized to 19:00:00 for the state timestamp and their 00:00:00 availability precedes it. Each row receives exactly one CPCV OOF prediction. The run asserts that no training row lies inside the one-day embargo window of any scored row.

Bin-edge rule: `np.linspace(0, 1, bins + 1)` equal-width edges; bin k is `[lo, hi)` except the last bin is `[lo, hi]`. Exactly ten bin rows are retained per sport and arm, including empty bins.

Verdict rule: `IMPROVES` only when ECE falls, Murphy reliability falls, and Murphy resolution does not fall against the raw probability on the same sport corpus. Every other cell is `FLATTENED`. This rule is unchanged from S05.

Acceptance bar: twelve cells (four sports by three calibrators), all named denominators retained with zero dropped rows, the isotonic column reproducing the four published after-ECEs at max abs diff exactly 0.0, every cell carrying the sealed verdict, ten bins per cell, paired per-row raw and arm log losses, and an actual per-regime `fit_history` count per row. The S05 isotonic premise is remeasured separately before CPCV scoring; any CPCV difference from that legacy expanding-prefix premise is reported but does not relax the verdict rule, bin-edge rule, denominator, or zero-drop bar. No calibration outcome is served, promoted, or enabled.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q. This uncharged measurement reads no ledger K, changes no registry, data file, feature flag, gate threshold, or S05 artifact.

Seal SHA-256 of the pre-seal content above: `4477066E64105687647CF3E55B72E25727589E8635518BEEDDABBDDE9EF8D5D2`.
