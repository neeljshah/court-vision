# Closing-line comparison, CLV and maker markout: the methods page

PAPER ONLY. Calibration and execution-quality language only. This page defines the measurement
vocabulary a desk reviewer will use on this repository, names the code that implements each term,
and says for each one what is measured today (with the file that shows it) or that it is not yet
measured. Every figure here is also in [CANONICAL_FIGURES.json](evidence/CANONICAL_FIGURES.json) and
is checked against the other public pages by `python -m scripts.platformkit.eval_gate.claim_consistency --repo-root .`.

"Public" below means the file is in the public export allowlist (`scripts/hooks/public_allowlist.txt`);
"private tree" means the code exists in the full repository but is not in the public export.

## 1. Devig: from quoted prices to a fair probability

| Term | Definition on this desk | Code | Public? |
|---|---|---|---|
| Proportional devig | p_home = imp_home / (imp_home + imp_away), where imp is the implied probability of each quoted price | the pregame harnesses (`scripts/platformkit/proof_mlb/`, `proof_soccer/`, `proof_nba/`), called by `scripts/platformkit/eval_gate/dm_recompute_pregame.py` | recompute script public; harnesses private tree |
| Shin devig | Shin (1992) insider-share model, solved by bisection on z; rows whose booksum is below 1 have no valid Shin price and are dropped | `scripts/platformkit/eval_gate/shin.py` (`shin_devig`, `shin_devig_decimal`) | public |

The closing price used is the last pregame quote in each corpus. The 2026-09-24 recompute reports
both devig methods; no verdict changes between them
([DM_RECOMPUTE_2026-09-24.md](evidence/pregame/DM_RECOMPUTE_2026-09-24.md), sensitivity table).

## 2. Scoring a forecaster against the close

| Term | Definition | Code | Public? |
|---|---|---|---|
| Brier, log loss against the outcome | per game: (p - y)^2 and -[y ln p + (1 - y) ln(1 - p)], for the model and for the devigged close on the same games | `scripts/platformkit/eval_gate/dm_recompute_pregame.py` | public |
| Close-relative gap | mean over games of loss_model minus loss_close; positive means the close is sharper | same | public |
| Game-clustered Diebold-Mariano | t-test on the per-game loss differences with cluster-robust variance, Student-t with G - 1 degrees of freedom; the 95% interval is the reported CI | `scripts/platformkit/eval_gate/dm_test.py` (`diebold_mariano`, `cluster_blocks`) | public |
| Verdict rule | MATCHES_CLOSE if the CI includes 0, TRAILS_CLOSE if it lies above 0, BEATS_CLOSE if below | `dm_recompute_pregame.py` | public |
| MDE | 1.429 x the CI half-width: the smallest gap the row could detect at 80% power | [POWER_PAGE_2026-09-22.md](evidence/POWER_PAGE_2026-09-22.md) | public |

**Measured today** (source: [DM_RECOMPUTE_2026-09-24.md](evidence/pregame/DM_RECOMPUTE_2026-09-24.md)):

| Row | n | Gap (Brier) | 95% CI | DM p | Verdict |
|---|---|---|---|---|---|
| MLB moneyline, proportional devig | 13,992 | +0.0039 | [+0.0028, +0.0051] | 3.6e-12 | TRAILS_CLOSE |
| Soccer O/U 2.5, proportional devig | 7,558 | +0.0076 | [+0.0059, +0.0092] | 1.1e-19 | TRAILS_CLOSE |
| NBA moneyline, Shin devig | 372 | +0.0069 | [-0.0038, +0.0175] | 0.20 | MATCHES_CLOSE (underpowered, MDE 0.0152) |

Reading: the close is measurably sharper on MLB moneyline and soccer O/U 2.5. On NBA moneyline the
gap cannot be told apart from zero, and a gap the size of the MLB one could not have been detected at
n=372. Nothing beats the close.

## 3. CLV: price improvement against the devigged close

| Term | Definition | Code | Public? |
|---|---|---|---|
| CLV | for a recorded price on one side, clv_pct = (fair_close - taken_p) / taken_p x 100, where fair_close is the Shin-devigged closing probability of that side and taken_p is the probability implied by the recorded price. Positive means the recorded price was better than the close | `scripts/platformkit/clv_ledger.py`, with append-only IO in `clv_ledger_io.py` and de-duplication in `clv_ledger_dedup.py` | public as readable source; imports a private-tree module, so it does not run on a public clone |

**Measured today: not yet measured.** No real-close CLV reading exists for a forecast recorded before
the close. An earlier aggregate CLV figure was circular and is on the do-not-claim list
([JOB_EVIDENCE_PACKET.md section 4](JOB_EVIDENCE_PACKET.md)). The ledger is the instrument that will
record it; it has no qualifying rows.

## 4. Maker markout and fill realism (in-play paper desk)

| Term | Definition | Code | Public? |
|---|---|---|---|
| Paper maker fill | a resting paper quote is filled only when a later captured book trades THROUGH its price (touching it is not a fill, because queue position is not modelled) | `scripts/platformkit/execution/paper_maker.py` (`trades_through`) | public as readable source; imports a private-tree module, so it does not run on a public clone |
| Markout | after a fill, later_mid - fill_price for a YES order, (1 - later_mid) - fill_price for a NO order, minus the fee per contract; in probability points per contract, never a currency amount | `scripts/platformkit/execution/markout.py` (`markout`, `markout_summary`) | public as readable source; imports a private-tree module, so it does not run on a public clone |
| Strict horizon markout | the markout at fixed horizons of 30, 120 and 300 s after the fill, using the first usable same-game mark in a window that opens at each horizon and lasts at most 30 s (a missing mark is a counted refusal), with a leave-one-game-out range in the summary | `scripts/platformkit/execution/markout_causal.py` (`DEFAULT_HORIZONS_S`, `summary_strict`) | private tree |
| Fee netting | the venue maker fee from the one canonical schedule, subtracted as a magnitude so it can only lower a markout | `scripts/platformkit/execution/venue_fees.py`; see [KALSHI_NOTE.md](KALSHI_NOTE.md) | public, runs on a public clone |
| Fill realism | a counterfactual replay of each paper quote against captured trade prints: a quote is credited only when prints during its life (TTL 5 s or 30 s) at its price deplete the modelled queue ahead of it, under several queue-depth multipliers (an unknown queue is never treated as depleted); refusals are counted by reason | `scripts/platformkit/execution/fill_realism.py` and `fill_realism_markout.py`, `fill_realism_classify.py`, `fill_realism_io.py`, `fill_realism_night.py` | private tree |

How each receipt is produced: the nightly paper run writes one fill-realism receipt per night to
`docs/evidence/forward/fill_realism/<date>.json` and multi-night execution-quality summaries to
`docs/evidence/forward/exec_quality/`; the cumulative roll-up reads them into
`docs/evidence/forward/cumulative/<date>.md`. A missing or unreadable receipt is counted as unknown,
never as zero.

**Measured today** (source: [cumulative/2026-10-04.md](evidence/forward/cumulative/2026-10-04.md)):
10 nights with any receipt (2 COMPLETE), 0 qualified games in any sport, 136 TTL-30 and 48 TTL-5
credited paper fills on unqualified tape (unknown on 4 nights). Fills are reported as counts only.
Every pooled cell is INSUFFICIENT. **A per-fill markout table with game-clustered intervals is not yet
published**; the exec_quality receipts carry engine statistics labelled INSUFFICIENT.

## 5. What is and is not claimed

- Claimed: the pregame model trails the devigged close on MLB moneyline and soccer O/U 2.5 by the
  intervals above, and is indistinguishable from it on NBA moneyline at an underpowered n=372.
- Claimed: the instruments above exist and are tested; the scoring instruments (eval_gate) and the fee
  module run on a public clone (the five commands in [QUANT_BRIEF.md section 6](QUANT_BRIEF.md)).
- Not claimed: that any forecaster is sharper than the close or the live market; any CLV reading;
  any markout level; any statement about returns. A markout is a microstructure diagnostic, and a
  single fill, night or game is not evidence about the desk.

---
**Navigate:** [Quant brief](QUANT_BRIEF.md) - [Kalshi note](KALSHI_NOTE.md) - [Evidence index](../EVIDENCE.md) - [Job Evidence Packet](JOB_EVIDENCE_PACKET.md)
