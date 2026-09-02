# Signal-inventory red team -- the honest catalogue (2026-09-03)

Lane Y (read-only sweep, main repo). Question: the front-door documents advertise
"85 trained signals" and an "80-artifact intelligence layer". How many of those
carry a leak-free MARKET-RELATIVE out-of-sample verdict -- the only kind that
counts toward a calibrated forecast -- and how many are something weaker?

Calibration language only (Q6). REJECT / NULL / BEHIND / NOT_TESTABLE are
successes here. No claim in this memo is a claim of beating any market; the two
places a market comparison exists, the market is level or sharper, and it is
printed that way. Truth source for any claimable number:
[docs/JOB_EVIDENCE_PACKET.md](../../JOB_EVIDENCE_PACKET.md).

## Headline

**14.** That is the lifetime count of charged, prereg-sealed trials in
`data/cache/eval_gate/backtest_fwer.jsonl` (`k_cumulative` 1..14, verified by
reading all 14 lines). Every other number below is weaker evidence than one of
those 14 rows.

| evidence class | count | what it means |
|---|---|---|
| charged walk-forward vs a close, prereg-sealed | **14 trials** | the FWER ledger; 0 AHEAD, verdicts MATCH / BEHIND / REJECT |
| market-relative but historical vectors NOT archived | **60 catalog signals + 9 NBA mechanisms** | REJECT-first / BEHIND; cannot be re-derived from disk |
| uncharged descriptive local effect | **87 wired mechanisms** (129 ledger-confirmed) | `DESCRIPTIVE_ONLY`, `edge_claimed=false` |
| in-sample or own-baseline fit only | **77** (21 signal-lab + 26 foundry + 30 test-log) | scored against our own baseline, never a close |
| no market-relative test at all | **86 registry signals + 151 intelligence artifacts + 176 T0/T1 screens + 116,370 grammar hypotheses** | never met a close in any form |
| retracted | **40 rows** | `data/registry/signal_edge_registry.parquet` -- see the do-not-claim note below |

## Inventory -- one row per family

Evidence type: **CHARGED** = charged walk-forward vs a close with a prereg seal |
**MKT-UNARCH** = market-relative but the per-signal loss vectors are not archived |
**DESCR** = uncharged descriptive local effect | **INSAMP** = own-baseline fit
only | **NONE** = no market-relative test at all | **RETRACTED**.

| family | sport | horizon | evidence | artifact | n | market-relative number | verdict on disk |
|---|---|---|---|---|---|---|---|
| gate signal catalog | NBA | pregame | MKT-UNARCH | `eval_gate/retro_correction_report.txt` | 16 signals, `n_trials`=85 | none archived | REJECT x16 |
| gate signal catalog | MLB | pregame | MKT-UNARCH | same | 14, `n_trials`=85 | none archived | REJECT x14 |
| gate signal catalog | soccer | pregame | MKT-UNARCH | same | 15, `n_trials`=85 | none archived | REJECT x15 |
| gate signal catalog | tennis | pregame | MKT-UNARCH | same | 15, `n_trials`=85 | none archived | REJECT x15 |
| SPA cross-check of the same 60 | 4 sports | pregame | MKT-UNARCH | `eval_gate/spa_catalog_report.txt` | 60 | `family_spa_p=NA` | NOT_EVALUABLE x60 |
| null-ship calibration of the gate | n/a | n/a | CHARGED (instrument) | `eval_gate/post_hardening_revalidation_report.txt` | 200 null candidates | 0 ships at alpha 0.05 | PASS |
| mechanism wiring | NBA | mixed | MKT-UNARCH | `analytics_showcase/out/mechanism_wiring.json` | 27 | 9 rows vs close | BEHIND 9 / NOT_TESTABLE 18 |
| mechanism wiring | MLB | mixed | NONE | `out/mechanism_wiring_mlb.json` | 22 | none | NOT_TESTABLE 22 |
| mechanism wiring | soccer | pregame | DESCR | `out/mechanism_wiring_soccer.json` | 15 | 0 with a trigger | NOT_TESTABLE 15 |
| mechanism wiring | tennis | pregame | DESCR | `out/mechanism_wiring_tennis.json` | 23 (3 scored) | 3 residual-vs-devig effects | NULL_LOCAL 3 / NOT_TESTABLE 20 |
| mechanism ledgers (full) | 4 sports | mixed | DESCR | `out/mechanism_survival.json` | 287 rows | none | 129 confirmed-local, survival 0.5039 |
| player/team scouting registry | NBA | pregame | NONE | `data/registry/signal_registry.parquet` | 86 rows | none | 72 folded / 14 deferred; `coverage_pct` null 86/86 |
| signal lab | NBA | pregame | INSAMP | `data/registry/signal_lab_registry.parquet` | 21 | none (RMSE vs own baseline) | 5 VALIDATED / 16 REJECTED |
| foundry scoreboard | NBA possession | in-game | INSAMP | `data/registry/foundry_scoreboard/` | 26 | none | 0 FDR survivors; 23 does-NOT-replicate, 3 insufficient-seasons |
| aspect sweep / test log | NBA possession | in-game | INSAMP | `data/registry/signal_test_log/` | 30 | none | rejected-redundant / null / overfit |
| S12 factory screens | soccer+ | pregame | NONE (screen) | `data/cache/eval_gate/trials/` | 176 files (88 hyp x T0/T1) | none | 88 COVERED, 88 SCREEN, 0 promoted to T2 |
| S11 hypothesis grammar | 4 sports | both | NONE (construct) | `S11_grammar_2026-09-03.md` | 116,370 distinct hashes over 979 columns | none | CONSTRUCT, 0 collisions |
| MLB in-game arms | MLB | in-game | CHARGED | `data/cache/eval_gate/e4_promotion_trial_2026-09-01.json` | 158 games / 47,104 ticks | e4 Brier 0.207033 vs market 0.195387, gap +0.011646 CI[0.003485,0.021119] | market sharper; arm verdict SHIP_TO_SHADOW |
| Hedge over 4 arms | MLB | in-game | CHARGED | `hedge_trial_2026-09-01.json` | 158 / 47,104 | 0.223656 vs market 0.195387 | BEHIND, regret 2.063 in a 66.793 bound |
| Nested-CV stacker | MLB | in-game | CHARGED | `s06_stacker_trial_2026-09-03.json` | 158 / 47,104 | 0.296943 vs incumbent 0.207033 | BEHIND (SINGLE-WINDOW), deflated_p 0.000553 at K=14 |
| NBA in-game win prob | NBA | in-game | CHARGED | `benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json` | 1,592-1,593 games | end_q1 -0.0084 [-0.0161,-0.0008]; 3 later checkpoints straddle 0 | MARKET_SHARPER_PROVISIONAL / UNDERPOWERED x3 |
| static -> conditional calibration | NBA, MLB | in-game | NONE (self-comparison) | `proof_nba/ingame_accuracy.py`, `proof_mlb/ingame_accuracy.py` | real-corpus OOS | none -- deliberately not a market test | 0.209->0.159, 0.241->0.126 |
| per-regime isotonic | 4 sports | pregame | NONE (calibration) | `S05_calibration_report_2026-09-03.md` | 1,814 / 39,162 / 25,834 / 41,886 | devig close beats `p_base` on soccer + both tennis units | FLATTENED x4 (honest null: buys ECE, pays resolution) |
| intelligence layer | NBA | pregame | NONE | `data/intelligence/` | 151 files | none | not in any gate; all mtime 2026-06-02 |
| runtime registry | 4 sports | pregame | n/a (contract) | `signals/runtime_registry.py` | 32 columns | none | 30 RUNTIME / 2 TRAIN |
| historical prop-signal registry | NBA | pregame | RETRACTED | `data/registry/signal_edge_registry.parquet` | 40 rows | see note | do-not-claim |

**Retraction note.** `signal_edge_registry.parquet` carries columns literally
named `roi`, `base_roi` and `lift` over five assist/points corpora at n=33..71.
This is the retracted assist result. It is listed here only so the inventory is
exhaustive; it is not evidence of anything and must never be quoted as current
(JOB_EVIDENCE_PACKET do-not-claim list, `.claude/rules/no-edge-claims.md`).

## Gap analysis

**How many of the advertised set have a leak-free market-relative OOS verdict?**
Of the 86 rows in `signal_registry.parquet`: **0**. Not one carries a market
comparison, a coverage figure (`coverage_pct` is null 86/86), or a test artifact.
Their `status` field is `folded` (72) or `deferred` (14) -- a build state, not a
verdict. The 60 gate-catalog classes DO have a market-relative verdict (REJECT,
all 60), but they are a different, disjoint population from the 86.

**Descriptive only.** 87 wired mechanisms (NBA 27 / MLB 22 / soccer 15 / tennis
23), of which only the 3 scored tennis rows produced a residual-vs-devigged-close
number, and all 3 are NULL_LOCAL. The wider ledgers hold 287 hypotheses with 129
confirmed-local. `edge_claimed=false` and `label=DESCRIPTIVE_ONLY` on every
artifact -- correctly labelled, and correctly worth nothing toward a forecast.

**Stale.** All **151/151** intelligence artifacts have mtime 2026-06-02; the gate
corpora they would be tested against were rebuilt 2026-09-02 (`gate_corpus_*.parquet`)
and MLB runs to 2026-07-12. Every intelligence artifact is older than the corpus
it cites. Worse, `gate_manifest.json` governs **19** artifacts (2 ledger + 17
tracking evidence) and **0** of them is a signal, mechanism or intelligence
artifact -- so S09's staleness machinery cannot see this layer at all.

**Runtime-available vs training-only.** `runtime_registry.py` declares **32**
columns (30 RUNTIME, 2 TRAIN) against the **979** catalogue columns S11
enumerated -- **3.3 % declared**. S11's own memo records that `Hypothesis`
carries no `runtime_available` field, so the grammar cannot express the split it
requires per column. The product contract (runtime student uses APIs only) is
therefore unenforceable for 947 of 979 columns.

**In-game families never tested against a devigged close.** Soccer: no in-game
family exists at all. Tennis: none (the 3 scored rows are pregame residuals).
MLB mechanisms: 22/22 NOT_TESTABLE -- S10 measured the modern MLB close join at
8.17 % (913/11,179). NBA mechanisms: 18/27 NOT_TESTABLE. The ONLY in-game
families with a market comparison anywhere are the four MLB tick arms and the
four NBA checkpoint rows -- and in both, the market is level or sharper.

## Top 10 next tests (S12 T2 charged), highest expected information first

Each names the corpus already on disk, the exact incumbent, and why. In-game
first, per the standing preference; all corpora are local, none needs new data.

1. **MLB `e2_regime` on its own covered slice.** Corpus `gate_corpus_mlb` ticks,
   6,579 of 47,104. Incumbent: `e4_blend` at Brier 0.206786. Why: S06 named
   regime heterogeneity as one of three structural causes of the Hedge regret and
   never tested the regime arm where it is actually covered. Cheapest resolution
   of a named cause.
2. **NBA halftime checkpoint, powered.** Corpus ALLGAMES_v3 (1,593 games) plus
   `gate_corpus_nba` (1,814 games, 2024-10-22..2026-04-12). Incumbent: the
   market's own in-game win probability. Why: halftime CI [-0.0098, 0.0015] is
   the single closest-to-resolving row in the whole system; end_q1 already
   resolved and it resolved against us. Resolving it either way is information.
3. **Promote the 88 screened hypotheses to T2.** Corpus: whichever the screen
   used (soccer, `corpus_sha` 81a66c860ada55c6). Incumbent: the devigged close.
   Why: 176 T0/T1 files exist and **0** have ever been charged. The factory's
   promotion rule has never once fired on real hypotheses; until it does, the
   grammar is untested machinery.
4. **The 9 BEHIND NBA mechanisms, re-run charged.** Corpus `gate_corpus_nba`.
   Incumbent: devigged close. Why: they already carry a market-relative verdict
   with no prereg seal and no ledger charge; converting 9 uncharged BEHINDs into
   9 charged rows is the largest single gain in charged coverage available.
5. **Tennis ATP + WTA as two corpus units (T3).** Corpus `gate_corpus_tennis`,
   ATP 25,764 and WTA 8,002 joined rows. Incumbent: devigged close (already
   beats `p_base`, 0.1986 vs 0.2164 ATP / 0.1935 vs 0.2157 WTA). Why: this is
   the only place on disk where S08's `min_corpora_eff` 2-corpora floor can
   actually be satisfied. The replication gate has never gated a real AHEAD.
6. **RUNTIME-only feature set vs the full teacher set.** Corpus `gate_corpus_mlb`
   (39,162 rows). Incumbent: the full-feature forecaster. Why: nothing has ever
   measured what the API-only runtime restriction costs. That number is a
   product fact, not a research one, and it is missing.
7. **The 5 VALIDATED signal-lab rows against a close.** Start with
   `oreb_matchup` (team-game margin, n=2,158). Corpus `gate_corpus_nba`.
   Incumbent: devigged close. Why: all 5 were validated against our own RMSE
   baseline only; a "VALIDATED" label with no market benchmark is the exact
   shape of claim this program exists to catch.
8. **MLB 2026 single-season slice.** Corpus: the 63.18 % joinable 2026 rows from
   S10 (per-season only, never the headline). Incumbent: devigged close.
   Why: it is the only modern MLB close on disk; one honest, explicitly
   season-labelled T2 is worth more than 22 NOT_TESTABLE rows.
9. **Soccer stacker as a second corpus for S06.** Corpus `gate_corpus_soccer`,
   16,322 rows with a close (2019-08-02..2026-05-24). Incumbent: devigged close.
   Why: S06's BEHIND is SINGLE-WINDOW; soccer is the largest joined corpus we
   have and would make the stacker verdict replicable rather than one-window.
10. **One T1 screen of the intelligence layer.** Corpus `gate_corpus_nba` residuals
    against the largest artifact family (the matchup matrix). Incumbent: devigged
    close. Why: 151 artifacts, zero market-relative tests, ever. Even a NULL
    would be the first evidence this layer has produced about forecast quality.

## Numbers quoted in documents that no artifact reproduces

| where | quoted | what the artifact says |
|---|---|---|
| `README.md:28` | "0/85 candidate signals survive" | The survivor count reproduces (**0**). The denominator does not: `retro_correction_report.txt` and `spa_catalog_report.txt` both enumerate **60** catalog classes (NBA 16, soccer 15, tennis 15, MLB 14), re-derived by import as 8+8, 7+7, 7+8, 7+8 = **60**. **85** is the `n_trials` multiplicity count printed on every one of the 60 rows -- a k, not a signal count. |
| `CLAUDE.md`, front-door copy | "85 trained signals" | No artifact holds 85 signals. `signal_registry.parquet` = **86** rows (never tested); the gated catalog = **60** classes. The two are disjoint populations, and neither is 85. |
| `CLAUDE.md`, `docs/PUBLIC_EVIDENCE.md:45,73,187` | "80-artifact intelligence layer" | Disk holds **151** files under `data/intelligence/`. `INTELLIGENCE.md` states the later additions beyond the 80-core are "not yet individually catalogued", so the 80-subset is not enumerable from disk by any script. The 151 figure reproduces; the 80 does not. |
| `out/mechanism_exposure.json` `ledger_cross_check` | parsed 27/22/15/23 = **87** | vs `ledger_confirmed` 45/32/29/24 = **130**. **43** ledger-confirmed mechanisms parse into no wiring row and are invisible to every downstream artifact. |
| `out/mechanism_survival.json` vs `out/mechanism_exposure.json` | 129 confirmed | vs 130. The MLB key differs (31 vs 32) and `mechanism_survival` splits one sport across two keys, `basketball_nba` (82) and `nba` (3). Two artifacts, two answers. |
| `S19` register row (already recorded) | memo premise 101.172 s | verifier reproduced 65.000 s. Noted for completeness; the row already carries the correction. |

## Candidate register rows (measured BEFORE included; orchestrator assigns ids)

- **Registry signals carry no market-relative status.** BEFORE: 0/86 rows in
  `data/registry/signal_registry.parquet` carry a verdict against any close;
  `coverage_pct` is null 86/86 and `status` holds a build state (folded 72 /
  deferred 14), not an outcome. Must-not-move: no bar, no gate value.
- **The intelligence layer is outside freshness governance.** BEFORE: 0 of 151
  `data/intelligence/` artifacts appear in `gate_manifest.json` (19 rows), and
  151/151 have mtime 2026-06-02 against gate corpora rebuilt 2026-09-02.
- **The runtime/teacher split is undeclarable for 96.7 % of columns.** BEFORE:
  32 columns declared in `runtime_registry.py` (30 RUNTIME / 2 TRAIN) vs 979
  catalogue columns enumerated by S11; `Hypothesis` carries no
  `runtime_available` field (S11 memo, own admission).
- **The factory has never charged a T2 from grammar.** BEFORE: 176 screen files
  in `data/cache/eval_gate/trials/` (88 T0 COVERED + 88 T1 SCREEN), 0 promoted;
  all 14 ledger rows were hand-called from four named modules.
- **43 ledger-confirmed mechanisms parse into no wiring row.** BEFORE: 87 parsed
  vs 130 ledger_confirmed in `mechanism_exposure.json`'s own cross-check.
- **The public denominator does not match the artifact.** BEFORE: README quotes
  0/85; the artifacts enumerate 60 classes at n_trials=85. Bar: the printed
  denominator equals a count a script reproduces.

## NOT VERIFIED

- Whether the 60 catalog REJECTs are *leak-free* -- the reports state plainly
  that historical per-signal DM vectors are not archived, so no re-derivation
  was possible in this lane. I read the verdicts; I did not reproduce them.
- The 129 vs 130 mechanism discrepancy is located to the MLB key but the
  offending row was not identified (the ledgers themselves were not read).
- The two static->conditional Brier pairs (0.209->0.159, 0.241->0.126) were read
  from `docs/evidence/ingame-conditioning.md`, not re-run.
- No test file was executed in this lane; every number above is a read of an
  on-disk artifact, a parquet shape, an mtime, or a Python import of a catalogue
  constant. No corpus was rebuilt, no gate was run, no ledger row was charged.
- `data/intelligence/` file contents were not opened -- only the count (151) and
  mtimes were measured.
- The top-10 list is a proposal, not a result. None of the 10 has been run.
