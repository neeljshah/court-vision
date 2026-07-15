# Due Diligence -- reproduce every claim in one command

This is the honest, buyer-facing account of what the product is, what it claims,
what it explicitly does **not** claim, and the exact command to reproduce every
verdict yourself. The product is a **calibrated predictor with a real,
CLV-tracked paper trail** -- not a dollar-ROI or betting-edge product. A
sophisticated quant buyer is being sold exactly this honesty: out-of-sample
calibration, closing-line-value discipline, and a leak-free, reproducible
methodology.

## The one command

```
python -m sell.evidence_pack
```

This assembles `data/frontend/sell/evidence_pack/` containing:

| Artifact | What it is |
|---|---|
| `track_record.signed.json` | The signed CLV + calibration track record (HMAC-SHA256). |
| `reproduce.json` | The honest verdicts of every buyer-checkable proof (below). |
| `manifest.json` | A stable sha256 manifest over the packed artifacts (tamper-evident). |
| `methodology.json` | The binding honesty framing (claimed / not-claimed). |

To reproduce only the verdicts in-process:

```
python -c "import json; from sell.reproduce import reproduce_all; print(json.dumps(reproduce_all(), indent=2, default=str))"
```

To independently re-run the underlying gates the pack assembles:

```
python -m governance.run_governance                          # exits 0/1
python -m scripts.platformkit.eval_gate.run_gate --golden    # exits 0/1
python -m sell.cli verify                                    # signature 0/2/3/4
```

## What IS claimed (and how it is proven)

- **Out-of-sample calibration.** Leak-free, walk-forward, truncation-invariant
  Brier / ECE, validated against the **Shin-devigged close**. Proven by the
  eval-gate golden walk-forward (`run_gate --golden`). The golden fixture is a
  SYNTHETIC reproducibility / regression anchor; the gate blocks only on a
  regression-vs-frozen-baseline or a leak-guard assertion.
- **Closing-line-value discipline.** A CLV ledger graded against the **true
  close** (with a labelled proxy-close fallback). `mean_clv_pct > 0` means bets
  were recorded at a better number than the close, on average. CLV is computed by
  the vetted `clv_ledger` / `scoreboard` and is **never recomputed** in the sell
  layer.
- **A signed, tamper-evident track record.** HMAC-SHA256 over the canonical JSON;
  any single mutated field (top-level or nested) fails `verify`.
- **Governance honesty/correctness gates green.** No retracted number, no $-edge
  key, no leak, no train/inference parity break, ledger intact.

## What is NOT claimed (binding)

- **No dollar ROI / P&L / edge anywhere.** There is no `$edge` field by design
  (the prediction contract carries probability / EV only). The track record and
  the sell API carry `edge_claimed=false`. A reported ROI from the paper trail is
  small-N variance, not a claim.
- **In-game gain is calibration, not a market edge.** The in-game proof verdict is
  `CALIBRATION_GAIN_VS_BASERATE` -- a real in-game calibration improvement from
  realized game state versus a base-rate prior. Versus the close it is
  **`UNPROVEN`**: no in-play odds were captured, so no market edge is asserted.
- **Pregame team-strength markets are efficient.** The honest result is that the
  model **matches the devigged close within noise**. A `MATCHES_CLOSE` or even a
  `BEHIND` verdict is an **honest success**, not a failure -- it is recorded as-is
  and never upgraded.

## Verdicts the pack surfaces (honest, never upgraded)

| Proof | Source | Honest verdict surfaced |
|---|---|---|
| Governance preflight | `governance.run_governance.run_all` | `GOVERNANCE_OK` / `GOVERNANCE_BLOCKED` (exit 0/1) |
| Leak-free walk-forward | `eval_gate.run_gate --golden` | per-corpus `BEATS_CLOSE` / `MATCHES_CLOSE` / `BEHIND`; gate `NO_REGRESSION_NO_LEAK` / `GATE_FAILED` |
| In-game proof | `data/frontend/ingame/proof_nba.json` | `CALIBRATION_GAIN_VS_BASERATE`; `vs_close: UNPROVEN` |
| Signed track record | `sell.cli` artifact | `SIGNATURE_VERIFIED` / `UNSIGNED` / `SIGNATURE_INVALID` |

`reproduce_all()` **assembles** these verdicts; it surfaces `MATCHES_CLOSE`,
`BEHIND`, and `UNPROVEN` exactly as the underlying proofs produced them, and
never upgrades a verdict.

## Tamper-evidence

- The track record is HMAC-signed; the secret lives **only** in the environment
  (`SELL_API_SECRET`), never in code. With no secret the record is written
  honestly **UNSIGNED** -- never silently presented as signed.
- The pack manifest is a sha256 roll-up over every packed artifact's content. Edit
  one byte of any artifact and the manifest's `manifest_sha256` changes.
- The whole pack is run through `governance.honesty_linter` before any file is
  written: a banned $-edge key or a retracted number **raises** and nothing is
  written to disk.

## Reproducibility / signing secret

```
# optional: enables a SIGNED (verifiable) track record; absent -> honest UNSIGNED
export SELL_API_SECRET=...        # env only; never committed
python -m sell.evidence_pack
python -m sell.cli verify         # 0 ok / 2 missing / 3 unsigned / 4 invalid
```

## Human-gated step (NOT performed by any agent)

Public deployment and pushing to `origin` are **human-gated**. No part of this
pack, and no agent, ever pushes to a public remote or deploys. That step is a
deliberate manual decision documented here and left to a human.
