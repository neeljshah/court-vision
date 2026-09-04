# S236 season-block partition preregistration

Scope: re-quote the fixed S202 one-way clustered effective sample size beside a
new season/ISO-week partition count for NBA, MLB, and tennis. Soccer remains a
corpus-unit control. This is an evidence-only calibration diagnostic; it does
not change a serving route, gate, feature flag, register, ledger, or data
store.

Inputs: read the four S202 gate corpora and their named label stores one sport
at a time, using the paths in `s202_two_way_neff.CONFIG`. Retain every gate row
after the existing one-to-one event-id label join. The fixed denominators are
NBA 1814, MLB 39162, soccer 25834, and tennis 41886. The source date column is
the joined `event_date`; blank or unparseable dates are an input failure, not a
row-drop rule.

Partition: NBA rows map to ISO season `NBA-YYYY-YY`, where months October
through December use the calendar year as the start and months January through
September use calendar year minus one. MLB rows map to `MLB-YYYY-Www` and
tennis rows map to `TENNIS-YYYY-Www`, using ISO calendar year and ISO week.
Soccer is not repartitioned: its reported control count is its six
`corpus_unit` values. A block is counted only when it has at least one retained
row; no retained rows may be excluded to alter its count.

Metrics and bars: print each sport's S202 corpus-unit count and one-way n_eff
unchanged as BEFORE. Print the season-block count and the same fixed-denominator
one-way n_eff for NBA, MLB, and tennis. NBA, MLB, and tennis each meet the bar
only at block count at least 3; otherwise print CLOSED AT LIMIT. Soccer must
reproduce a count of 6. No value in `min_corpora_eff` is modified.

Leak audit: before reporting the metric, route each sport's retained rows
through `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` with
`embargo_days=1` and its imported symmetric purge. States use only event-time
descriptors and an availability timestamp one second earlier. The audit
predictor is the fixed corpus probability and has no fitted arm. Archive the
audit counts; this is a leak-contract validation, not a calibration comparison.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Q2 is not applicable: this diagnostic creates no charged trial and does not
open a ledger. Calibration language only. ASCII only.

Seal SHA-256 of the pre-seal content above:
`C26751B85E039209C93B2B1890176267A32DB438A1B03E05C163EA73A89986FC`.
