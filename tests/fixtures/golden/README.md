# Golden game-state fixture -- SYNTHETIC reproducibility anchor

`game_states.json` is the frozen golden set for the calibration eval gate
(roadmap N1, `scripts/platformkit/eval_gate/`). It lets a skeptic reproduce the
gate offline, with no network and no `data/`, in well under 60 seconds.

## THIS IS A SYNTHETIC ANCHOR -- NOT A REAL CALIBRATION CLAIM

Read this first, it is load-bearing:

- The 103 states in this file are **machine-generated** by a seeded deterministic
  builder (`scripts/platformkit/eval_gate/gen_golden.py`, seed `20260616`). They
  are **NOT real NBA games**, the team codes are placeholders, and the numbers do
  not correspond to any actual market close or any actual outcome.
- The payload carries `"_synthetic": true` to make this explicit in the data.
- This fixture exists purely as a **reproducibility / regression ANCHOR**: it
  gives the gate a stable, byte-identical input so a code change that silently
  degrades the forecaster is caught as a regression-vs-frozen-baseline.
- By construction the `devig_close_prob` is a slightly-noised oracle, so the
  in-window predictor **cannot beat the close** on this set. A `BSS <= 0` /
  `MATCHES_CLOSE` / `BEHIND` verdict here is the **HONEST, expected result**, and
  an honest SUCCESS -- never a failure. The gate blocks ONLY on
  regression-vs-frozen-baseline or a leak-guard assertion, never on "fails to
  beat the close".
- The REAL calibration bar is the `--corpus` path against real corpora under
  `data/domains/<sport>/` (gitignored, human-run). This fixture is the anchor for
  that path's plumbing, not a substitute for it.

## How the set is built (coverage + provenance)

A one-time, fully deterministic builder draws 103 states stratified across the
fragile regimes the gate must exercise:

| regime         | count | what it stresses                              |
|----------------|-------|-----------------------------------------------|
| pregame        | 35    | the prediction-time boundary (state == tip)   |
| q1 / q2 / q3 / q4 | 12 each | in-game states at increasing minutes      |
| blowout        | 6     | extreme `strength` -> near-degenerate p       |
| foul_trouble   | 6     | extra `foul_diff` feature shifting the latent  |
| early_season   | 4     | games forced into October (window trap)       |
| longshot       | 4     | near-0.06 / near-0.94 favorite-longshot bias  |

Seasons split `2023-24` (51 states) / `2024-25` (52 states) so the gate's
two-corpus rule has two independent legs. Each state's latent truth comes from a
fixed generative model `p_true = sigmoid(beta . features)` with
`beta = (1.4, 0.5, 0.25)`; `outcome` is a Bernoulli draw on `p_true`; the
`devig_close_prob` is `p_true` plus small Gaussian noise (the near-oracle close).
Every feature's `availability_date` is set strictly before the state timestamp so
the vintage leak-guard runs even on the fixture.

## How to regenerate (byte-identical)

```
cd /c/Users/neelj/nba-ai-system
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m scripts.platformkit.eval_gate.gen_golden
```

The builder seeds `numpy.default_rng(20260616)` once, uses no wall-clock / uuid /
hashing, validates with `schema.validate_golden`, and writes sorted-key,
6-dp-rounded ASCII JSON -> re-running produces a byte-identical file and a stable
git diff. Expected console line: `OK 103 states, regimes=[...]`.

## How to re-freeze the baselines (human-blessed)

After an INTENTIONAL change to the predictor or fixture, a human re-freezes the
per-corpus baselines (also SYNTHETIC anchors) from the actual offline run:

```
cd /c/Users/neelj/nba-ai-system/scripts/platformkit/eval_gate
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe baseline.py --freeze
```

This writes `baselines/nba_2023_24.json`, `baselines/nba_2024_25.json`
(`"_synthetic": true`) and registers the `mlb_2024` skip-until-X2 slot. Commit the
new baselines only after reviewing the diff -- the gate is non-regressing by
construction on the run it was frozen from.

## Run the gate against this fixture

```
cd /c/Users/neelj/nba-ai-system
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m scripts.platformkit.eval_gate.run_gate --golden
```

Exit 0 == no regression / no leak (honest verdicts BEHIND / MATCHES_CLOSE are
fine). Exit 1 == a corpus regressed vs its frozen baseline or a leak fired.

Field-by-field schema: see `SCHEMA.md` in this directory.
