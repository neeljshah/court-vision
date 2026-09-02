# S02 soccer close join

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q; spec: `docs/evidence/tracking/specs/S02_spec.md`.

## Premise and preregistration

The pre-metric S02 spec is commit `66f79b32bd6ca97ed83eb2615e7ee8f9b0588ded` (2026-09-01T23:32:14-05:00), content SHA-256 `5988BF894F26A8BEE164A31B7439484A3929068D66C5E4E8A530362A79FDB21C`.
`load_gate_corpus("soccer")`: 25,834 rows and no `devig_close_prob` column.
`matches.parquet`: 25,834 rows. `odds.parquet`: 16,322 rows, 2019-08-02 through 2026-05-24.
Close columns: `ou_close_over`, `ou_close_under`; each has 0 null values and 0 prices less than or equal to 1.0.

## Limit and coverage_report("soccer")

Pre-change raw spine-key limit: 16,322 / 16,322 odds rows joined (100.0 percent); duplicate event ids: odds=0, corpus=0, matches=0.
Overall: denominator=16,322, joined=16,322, unjoined=0, join_rate=1.0, scored=16,322, bad_price_drop_count=0, null_close_count=0.
By year (denominator=joined): 2019=1,187; 2020=2,083; 2021=2,561; 2022=2,259; 2023=2,473; 2024=2,254; 2025=2,290; 2026=1,215 (all join_rate=1.0).
By corpus_unit (denominator=joined): D1=2,142; E0=2,660; E1=3,864; F1=2,336; I1=2,660; SP1=2,660 (all join_rate=1.0).
Brier(devigged close)=0.23946005675766663; Brier(p_base)=0.2627028248079339.
The fixed 16,322-row denominator retains all joined, unjoined, null, and invalid-price cases; none were removed before the reported rate.
`gate_corpus_states("soccer", "2019-08-02", "2026-05-24")` returns 16,322 vintage-safe pregame states.
Verdict: **NOT VALIDATED**. The fixed join and calibration checks pass, but Q1 prevents a scored verdict; no harness threshold changed.

## Exact commands and test output

```powershell
python -c "from scripts.platformkit.eval_gate.close_join import coverage_report; import json; print(json.dumps(coverage_report('soccer'), indent=2, sort_keys=True))"
python -m pytest scripts/platformkit/eval_gate/test_close_join_soccer.py -q
```
`4 passed in 2.48s`.

## Contract self-check

- B1: denominator is all odds rows; B2-B6: additive files only, no schema/reader/gate/deployment/import retirement; B7-B9: no sampled or fitted claim; B10: unchanged thresholds.
- Q1: not satisfied: the pre-metric S02 spec lacks an embedded SHA-256 seal. Q2: no charged trial or trial-ledger operation.
- Q3: the specified bar is unchanged. Q4: this is a deterministic close materialization with no fitted or selected arm; state output is walk_forward-shaped and the 40-state smoke passed.
- Q5: no AHEAD claim. Q6: calibration-only wording. Q7: scored n=16,322 and reproduction is `coverage_report("soccer")`. Q8: premise measured before CHANGE.

## NOT VERIFIED

- Verifier rerun in master after landing, source freshness after this local measurement, and any downstream consumer adoption.

## Verifier adjudication (2026-09-03, master)

Verdict: **ACCEPT WITH CORRECTIONS** -- the lane's own NOT VALIDATED self-label is OVERRULED.
Q1 binds a SCORED COMPARISON entering a prereg/charged trial. The S02 ACCEPTANCE RULE fixes the
bar inside the spec itself and forbids any `_charge_ledger` call, so this coverage report is corpus
infrastructure, not a charged trial; Q1 is not a reject condition here. The memo's own seal
`5988BF89...FDB21C` was independently recomputed and matches `git show 66f79b32b:docs/evidence/tracking/specs/S02_spec.md | sha256sum`,
and 66f79b32b predates the metric commit d7718bdb0.

Reproduced in master from `coverage_report("soccer")`: denominator 16,322 (= all rows of
data/domains/soccer/odds.parquet, 16,322 unique event_id, 2019-08-02..2026-05-24), joined 16,322,
unjoined 0, join_rate 100.0000000000 pct, bad_price_drop_count 0, null_close_count 0, scored 16,322.
Brier(devigged close) 0.2394600568 < Brier(p_base) 0.2627028248 -- both computed over the 16,322
JOINED/scored rows only (here joined == denominator == scored). 2.00/2.00 -> 0.5000 exactly;
devigged probabilities all strictly inside (0,1), min 0.2252252175, max 0.8681710190, mean 0.5131214461
against a base rate of 0.5175223625. `python -m pytest scripts/platformkit/eval_gate/test_close_join_soccer.py -q -p no:cacheprovider`
in MASTER = 4 passed in 4.58s. `walk_forward` over 40 EVENLY SPACED real states from
`gate_corpus_states("soccer", "2019-08-02", "2026-05-24")` (16,322 states, every one carrying
`devig_close_prob`) returned 40 records with no LeakError.

Corrections carried: (1) the lane's NOT VALIDATED verdict on line 21 is superseded by this section;
(2) the Brier scope is now stated explicitly as the joined rows; (3) `by_corpus_unit` is computed
inside the matched rows only, so its per-unit join_rate is 1.0 by construction and carries no
coverage information -- harmless at unjoined=0, misleading for any sport where it is not.

NOT VERIFIED by the verifier: that `y` is the correct over-2.5 orientation for the soccer close
(only its consistency with the close and p_base was checked); the `avgc_over`/`avgc_under` fallback
path (never exercised -- 0 nulls in the primary columns); the synthetic vintage in
`gate_corpus_states` (`state_ts` fixed at 12:00:00, `feature_avail` at 00:00:00), which makes the
walk_forward leak guard pass by construction rather than from a real timestamp; any downstream
adoption by S03 or S22.
