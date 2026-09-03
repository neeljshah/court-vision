# S200 Regime Key OOF Preregistration

Scope: re-score NBA, MLB, soccer, and tennis read-only gate corpora under the
existing default regime key and an opt-in train-only confidence key.

Predeclared inputs: `load_gate_corpus(sport)` for one sport at a time. Every
finite corpus probability with a binary `y` remains in its sport denominator.

Predeclared method: the default path remains `regime_calibration.buckets`. The
train path sets each scored row's confidence T1/T2/T3 from tercile endpoints of
only the preceding expanding train window; phase, rest, and month fields remain
row-local. Both paths use the existing expanding walk-forward recalibration and
the existing ten-bin rule. The report archives per-row paired squared losses,
cluster identifier, timestamp when present, and both predictions.

Predeclared acceptance bar: all four denominators are exactly 1,814 / 39,162 /
25,834 / 41,886 with 0 dropped rows; print each train-path ECE and every
confidence-label change count; default post-calibration ECE differs from its
existing S05 artifact by exactly 0.0. An increase in train-key ECE is published
as measured.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
No serving path, feature flag, registry, evaluation threshold, results ledger,
or register is changed.

Seal SHA-256 of the pre-seal content above: `BCDF43B637B3735078033ED47D9A1A21B1612FBB45BE5C694B72AB64AB4B4AFC`.
