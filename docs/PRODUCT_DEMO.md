# Product Demo -- the 15-minute path

A tight walkthrough of the newest layer: the system checking its own health, making a
live prediction, answering a factual question with a receipt instead of folklore,
showing its composed betting-board output in honest units/CLV language, and exhibiting
its own graveyard of rejected ideas. Every command below is copy-pasteable and every
number quoted was run live for this doc.

For the older, broader setup + CV-pipeline walkthrough see [DEMO.md](DEMO.md). For every
number's proof artifact and the do-not-claim list, see
[JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md). Nothing here is a dollar edge, an ROI,
or a "beat the market" claim -- see [../.claude/rules/no-edge-claims.md](../.claude/rules/no-edge-claims.md)
if you're checking.

```bash
pip install -r requirements-predictor.txt   # slim install; no CV/web/daemon stack needed
```

---

## Minute 0-3 -- system_proof: one command, the whole system's health, honestly

```bash
python -m scripts.platformkit.proof_harness.system_proof
```

This composes the existing gates, sentinels, and ledgers into one ASCII table -- it
computes nothing new, it only reads what already exists and refuses to average a down
section into a green summary. A real run on this repo today (2026-07-15):

```
SYSTEM PROOF -- one-command liveness harness
==============================================================================
SECTION      STATUS            SUMMARY
------------------------------------------------------------------------------
fleet        RED               1/45 heartbeats RED: m2_inplay_capture
gates        GREEN             38/38 checks green (exit 0)
data         RED               census: 26 ok/8 drift/1 missing; 8/8 key stores fresh
predictions  GREEN             4/4 sport smokes returned a pregame prediction
ledgers      RED               4 ledger issue(s): validation_ledger_nba, validation_ledger_mlb, validation_ledger_soccer, validation_ledger_tennis
autonomy     RED               cannot enumerate job registry (maintenance_templates.py unreadable/moved)
integrity    GREEN             guard hashes match baseline
------------------------------------------------------------------------------
OVERALL: RED  (4 RED section(s), 0 PENDING-RESTART section(s))
```

**Read it as a feature, not a bug.** `fleet` names the one stale scraper by name;
`data` names the exact census-count drifts instead of a vague "something's off";
`ledgers` names the exact ledger files it could not clear, and `autonomy` names the
exact file it could not read to enumerate the job registry, instead of a silent pass.
The harness itself was fixed one commit before this doc (`2eedc37e`) specifically to
stop reporting decorative green on drift/staleness/an empty registry -- the RED above
is the harness working as intended, on a real box, right now.

---

## Minute 3-6 -- predict_matchup: a live calibrated prediction, any of 4 sports

```bash
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL --no-banner --json
```

```json
{
  "sport": "nba", "home": "BOS", "away": "LAL",
  "edge_claimed": false,
  "framing": "Pregame MATCHES the devigged close (calibration/sharpness, not an edge); in-game ADDS the realized state. No $ edge.",
  "pregame": { "p_home_win": 0.605, "total_mean": 211.3, "margin_home": 3.0 }
}
```

Swap `--sport` for `mlb`, `soccer`, or `tennis` -- same interface, same honest framing
baked into the response (`edge_claimed: false` is stamped on every call, not just this
one). This is the same subprocess call `system_proof`'s `predictions` section runs
above, so the two commands are cross-checking each other.

---

## Minute 6-9 -- ask the oracle a mechanism question and get a receipt, not a guess

The answer-engine oracle answers "does X actually happen in our data" questions by
routing to exactly one deterministic source -- the mechanism knowledge ledger -- and
quoting its verdict, sample size, p-value, and source file. It is a deterministic
stand-in for "any LLM following the answer contract": no model call, so a real LLM
client that follows the same rule reproduces this output byte-for-byte.

```bash
python -m scripts.platformkit.answers.contract_client "does b2b_rest_penalty hold up" --sport nba
```

```
b2b_rest_penalty: CONFIRMED_LOCAL effect=-1.73 n=4732 p=0.0056 (player_boxscores_2024_25_2025_26):
avg margin on 0-rest (-1.41, n=856) vs >=1-day rest (0.32, n=3876) | LOCAL single-corpus
finding(s) -- not a market-beating or causal claim | source:
domains/basketball_nba/knowledge/validation_ledger.jsonl | as-of: 2026-07-09T22:33:58Z
```

Ask about a mechanism that was tested and found to hold NULL (`three_in_four_fatigue`,
`pace_mismatch_variance`, ...) and you get the same receipt shape with a NULL verdict --
the oracle is required to state a null just as plainly as a confirmed effect. It cannot
be talked into a plausible-sounding basketball belief that was never tested: an
unregistered question type returns `NOT_SUPPORTED`, never an improvised answer. The
knowledge behind it is fully drained across all 4 sports -- 287 mechanism hypotheses
closed (130 confirmed incl. replications, 119 honest nulls, 29 not locally testable,
the rest provisional/reject/partial) -- so most factual "does X matter" questions about
NBA/MLB/soccer/tennis already have a row to cite.

Underneath the mechanism answers sits an **effect graph** (`data/frontend/ops/effect_graph.json`,
627 nodes / 335 edges across all 4 sports) that links every mechanism, interaction,
attribute, and outcome the system has ever adjudicated -- built by labeling and linking
existing ledger rows, computing zero new statistics.

---

## Minute 9-12 -- the composed best-bets board, in units/CLV language

```bash
python -c "import json; d=json.load(open('data/frontend/best_bets.json')); print(d['card_count']); print(json.dumps(d['cards'][0], indent=2))"
```

One real card from the composed board (58 cards on the board as of this run):

```json
{
  "sport": "mlb", "matchup": "San Francisco Giants vs Colorado Rockies",
  "market_type": "moneyline", "side": "home",
  "model_prob": 0.6901, "market_prob": 0.545248, "edge_vs_market": 0.144852,
  "units": 1.0, "confidence": 0.6901, "tier": "A", "decision": "bet",
  "clv": {"clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": true, "beat_close": null},
  "honest_note": "Calibrated decision-support only. Markets are efficient; no $ edge claimed. edge_vs_market = model_prob - market_prob (prob diff, NOT $). clv=INSUFFICIENT_DATA when no liquid in-play prices (offseason). units = flat_unit from policy (1.0 per bet, UNITS not $)."
}
```

Notice what the board refuses to say: `edge_vs_market` is a probability difference, not
a dollar figure; `units` is a flat sizing policy, not P&L; `clv_status` reports
`INSUFFICIENT_DATA` rather than fabricating a closing-line-value number it can't yet
compute. Every card repeats its own `honest_note` -- the board's honesty is per-row, not
a disclaimer bolted on somewhere else.

---

## Minute 12-15 -- the gap ledger + the reject ledger, the honesty exhibit

```bash
python -m scripts.platformkit.reject_ledger show
```

645 recorded REJECT/DEFER verdicts across NBA/MLB signal candidates -- one row per
candidate that did NOT survive the gate, with its reason, source, and date:

```
SIGNAL GRAVEYARD -- latest verdict per signal that did NOT survive the gate
A REJECT is honest market-efficiency evidence, not a failure; calibration != edge (no $ claim).
--------------------------------------------------------------------------------------------
sport  signal                          verdict source            when        reason
--------------------------------------------------------------------------------------------
mlb    mlb_atbat                       REJECT  funnel_gate       2026-06-21  UNPROVEN -- CALIBRATION...
mlb    mlb_sp_ra_diff_asof             REJECT  manual            2026-07-09  asof reclaim sweep: Brie...
...
```

Pair it with the ranked, human-readable [gap_ledger_2026-07-11.md](research/gap_ledger_2026-07-11.md)
(31 ranked open items from the most recent full-system audit, each with its own verdict
and evidence) and [JOB_EVIDENCE_PACKET.md section 4](JOB_EVIDENCE_PACKET.md#4-do-not-claim-list-never-put-these-in-front-of-a-recruiter),
the do-not-claim list. **The negative-result count is meant to dwarf the positive one.**
513 rejects and 151 mechanism verdicts with 51 honest NULLs are not a shortfall -- they
are what an audit that is actually trying to find the truth looks like when it succeeds.

---

## What you just saw

| Step | Command | What it proves |
|---|---|---|
| System health | `python -m scripts.platformkit.proof_harness.system_proof` | Composes real state, reports RED honestly |
| Prediction | `python -m scripts.platformkit.predict_matchup --sport nba ...` | Live calibrated forecast, `edge_claimed: false` |
| Oracle receipt | `python -m scripts.platformkit.answers.contract_client "..." --sport nba` | Mechanism answers cite verdict/n/p/source, never improvise |
| Composed board | read `data/frontend/best_bets.json` | Units/CLV language, no dollar claims, per-card honest_note |
| Honesty exhibit | `python -m scripts.platformkit.reject_ledger show` | 513 honest rejects; the graveyard is the proof of rigor |

No step above required a human decision, a market call, or a dollar figure. That is the
product: a calibrated, self-auditing forecasting system that tells you plainly what it
knows, what it doesn't, and what it tried and threw away.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
