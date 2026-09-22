# S385: provenance of the S86 NBA model-side constants (read-only scout, codex gpt-5.6-sol, 2026-09-21)

Archived verbatim by the orchestrator. Finding, not a measurement. Every constant is UNKNOWN; arm D is not untouched out-of-sample on the NBA corpus.

VERDICTS

UNKNOWN - ELO_K=20. `ee7087200` introduced it with only the heuristic "NBA carries ~3-4x more signal per game than MLB" (`elo_config.py:8-10`). No NBA Elo tuning script was found.

UNKNOWN - ELO_MEAN=1500. It is documented only as the unseen-franchise prior (`elo_config.py:12-13`). It is effectively an Elo scale anchor, but no provenance record identifies why 1500 was selected.

UNKNOWN - ELO_HFA=76. The only rationale is an uncited league home-win assumption of 59-60 percent (`elo_config.py:15-17`). Commit `ee7087200` also reports a 4,846-game build with home-win mean 0.555, but does not say those games fitted 76. Since that build includes 2024-25 and 2025-26 games, corpus influence cannot be excluded.

UNKNOWN - SEASON_REGRESS=0.25. The recorded rationale is only "NBA rosters turn over less" than MLB (`elo_config.py:19-21`); no seasons, fit, or calibration data are named.

UNKNOWN - margin sigma=13.5. Its earliest accessible source is `0f1aff49f`/`20b51ae5f`, `src/ingame/universal_winprob.py:27-28`: "NBA ~13-14 pts." `d7490804d` copied it into `config.py:209,225`; `cab70ccb1` copied it into `repricer.py:30`; `ef7775966` copied it into the benchmark. No originating sample is recorded. S98/S103 later fitted different sigmas from S86 outcomes, but did not rewrite 13.5 (`s98_nba_better_prior.py:36-45,145-155`; `s103_nba_sigma.py:77-99`).

COMMAND EVIDENCE

```
$ git log --follow --format='%h %ad %s' --date=short -- domains/basketball_nba/elo_config.py
0a4ac02c7 2026-09-17 publish: sync the public tree from 4de853616

$ ... -- domains/basketball_nba/repricer.py
0a4ac02c7 2026-09-17 publish: sync...
7e11693cb 2026-07-09 fix(nba): repricer OT defect...
cab70ccb1 2026-06-15 feat(ingame): W123 -- NBA in-game re-pricer...

$ ... -- scripts/platformkit/ingame/nba_checkpoint_benchmark.py
0a4ac02c7 2026-09-17 publish: sync...
6f7279e97 2026-07-09 feat(nba): full-scale in-game checkpoint corpus...
7e11693cb 2026-07-09 fix(nba): repricer OT defect...
ef7775966 2026-07-09 feat(nba): in-game checkpoint benchmark...
```

The public-sync topology hid the original Elo commit; `git blame` returned `ee7087200 2026-06-13` for all four constants. Constant-diff output was:

```
ee7087200: +ELO_K=20.0 +ELO_MEAN=1500.0 +ELO_HFA=76.0 +SEASON_REGRESS=0.25
cab70ccb1: +_DEF_MARGIN_SIGMA=13.5
ef7775966: +_DEF_MARGIN_SIGMA=13.5
7e11693cb: [no constant change]
6f7279e97: [no constant change]
```

Whole-tree fitting search found S98/S103 only. S98 reads `s86_nba_every_tick_2026-09-03.csv`, checkpoints, games, and outcomes, fitting TRAIN-fold sigmas (`s98...:36-45,118-155`). It writes result CSV/JSON, not the fixed constant (`:281-284`).

Ledger output: `RESULTS_LEDGER_SYSTEM.md:193` says S58 evaluated all 1,593 games; `:236` says S86 evaluated 797 screen games; `:255` records S98 fitting sigma on 571 games. The same grep over `docs/evidence/tracking/RESULTS_LEDGER.md` returned no matches.

Replay excludes the evaluated outcome: `ratings.py:153-154` skips `row_date >= until` before reading season or outcome. Regression is triggered only from processed rows (`:158-163`). Observed season ranges are monotonic, 2022-23 through 2025-26, so future season labels do not trigger an early boundary.

CONCLUSION

Arm D cannot be called untouched out-of-sample on this corpus: S58 already evaluated all 1,593 games, S86 evaluated 797, and every substantive fixed parameter remains UNKNOWN. The cheapest decisive check is to recover the original authoring transcript or design artifact for `ee7087200` and `0f1aff49f`, then inspect its exact input paths: overlap with the 1,593 games means LEAK; a named disjoint pre-2024-10 source means CLEAN.
