# Pregame versus close: public per-game files

`soccer_ou25_holdout.csv` holds the 7,558 held-out soccer Over/Under 2.5 matches behind the
published pregame row in `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`: one row per match
with the model probability, the proportionally devigged closing probability and the outcome
(devigged probabilities only, no prices); its data card is `soccer_ou25_holdout_CARD.md`. Score it
in one command: `python -m scripts.platformkit.eval_gate.score_vs_close --csv docs/evidence/pregame_vs_close/soccer_ou25_holdout.csv --devig proportional`
(numpy only; prints n, both Brier scores, the gap, the match-clustered 95% interval, DM p, MDE and
ten reliability bins per forecaster). The honest reading: the model TRAILS the close, Brier 0.2465
vs 0.2390, gap +0.0076, 95% CI [+0.0059, +0.0092]. This is a calibration readout, paper only. An
ATP file is not published: its match spine and outcomes come from the Sackmann corpus, whose
licence ledger row (row 10) reads UNREAD.
