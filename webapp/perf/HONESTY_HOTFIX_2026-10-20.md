# Honesty hotfix -- terminal half -- 2026-10-20

Scope: the honesty-rail breaks in docs/research/site/UX_AUDIT_2026-10-20.md sections 1-3 for the
older "terminal" half of webapp/. Not committed. Truth source: docs/JOB_EVIDENCE_PACKET.md.

Concurrent restructure: while this lane was editing, the restructure lane turned these routes into
redirect stubs (lib/redirects.ts): /bets, /records, /paper, /progress, /system, /today, /live, /p6,
/models, /risk, /atlas, /lab, /use-it, /evidence/retraction-story, /analytics/findings/retraction. It
also added app/layout.tsx + app/not-found.tsx (a shell-wrapped 404) and /evidence/retractions/ (the
packet's section 4 table, read verbatim at build time). The page-level edits this lane made to /bets,
/records and /paper were overwritten by those stubs. The component-level edits below still apply
wherever the components are mounted (/paper-trading, /today/TodayEquity, /games/<sport>/<id>, and
any page the restructure re-mounts them on).

## One shared sentence and one snapshot label

New file lib/clvUnavailable.ts (10 lines):

- CLV_UNAVAILABLE = "No closing-line-value reading exists as of 2026-10-19 (forward paper series
  since 2026-10-06, no verdict); the July 2026 snapshot's CLV figures were a proxy and are not shown."
- JULY_SNAPSHOT_LABEL = "July 2026 model snapshot, simulated units, not the forward record (as of
  2026-07-16)"

## 1. Wording

| file | before | after |
|---|---|---|
| components/bets/BetsMoneyHeadline.tsx (panel title) | "Money-makers -- paper equity (units)" | "Paper equity -- July 2026 model snapshot (simulated units)" |
| components/bets/BetsMoneyHeadline.tsx (lede) | "How much you would have made staking the best bets below." | JULY_SNAPSHOT_LABEL + "Paper simulation, units only -- no $." |
| components/bets/BetsMoneyHeadline.tsx (stat) | "net paper P&L" | "net simulated units" |
| app/(terminal)/bets/page.tsx (now a stub) | title / h1 "Best Bets"; "MONEY HEADLINE ... money-makers" | "Paper record" (overwritten later by the restructure stub) |
| app/(terminal)/bets/[sport]/SportBetsPageClient.tsx | "Best Bets", "best bets board", "Could not load best bets." | "Paper record", "paper record board", "Could not load the paper record." |
| components/bets/BestBetsBoard.tsx | "Best bets board", "<tab> best bets" | "Paper candidate board", "<tab> paper candidates" |
| components/p6/BestBets.tsx | "Best bets (paper)" | "Candidate board (paper)" |
| components/home/HomeTodayCard.tsx | "Best bets today", "Best bets board ->" | "Candidates today", "Paper record board ->" |
| components/bets/SortControls.tsx, RefreshAffordance.tsx, app/(terminal)/games/GameCard.tsx | "Sort best bets", "Refresh best bets now", "best bet: tier" | "Sort paper candidates", "Refresh paper candidates now", "paper candidate: tier" |
| components/bets_detail/CardDetailView.tsx, PlacedBetsForGamePanel.tsx | "the money-makers" | "the placed paper positions" / "in the paper ledger (simulated)" |
| app/(terminal)/today/page.tsx (now a stub) | "how much you would have made ... the PLACED (staked) money-makers, day P&L" | "the PLACED (staked) paper positions, day units ... (July 2026 model snapshot, not the forward record)" |
| components/Nav.tsx (labels only) | "Live", "Desk", "Bets" | "Paper live view", "Paper desk", "Paper record" |
| app/(terminal)/methodology/page.tsx (MODEL_SHARPER_PROVISIONAL meaning) | "The model's calibration beat the devigged close on this fold, provisionally." | "Sharper than the live market on this cell (CRPS or Brier), provisional; the reference is the live market, not the devigged close." |
| public/data/insights/calibration_stability.json (title) | "the market's MLB calibration is statistically perfect" | "no MLB market bin's gap interval excludes zero (10 of 10 within noise)"; body "indistinguishable from perfectly calibrated" -> "no MLB market bin's gap interval excludes zero at this sample" |
| components/depth/SignalVerdictBadge.tsx (soccer corners on /how-it-works) | chip "SHIP", note "calibration-only, vs_close UNPROVEN" | chip "CALIBRATION SURVIVOR -- NOT SHIPPED", note "...; a proposal, not shipped (0 of 60 signal classes shipped, JOB_EVIDENCE_PACKET s4)" |
| app/(terminal)/paper/page.tsx (now a stub) | "Edge-proportional (capped 1/4-Kelly)", "a paper track record" | "Conviction-proportional ...", JULY_SNAPSHOT_LABEL |
| components/p6/QuantPanel.tsx, components/records/RecordsRollup.tsx | column "Edge", "avg edge pp" | "Divergence", "avg divergence pp" |
| components/bets/LineShopPanel.tsx | "best bettable line" | "best available line" |
| lib/api.ts HONEST_DISCLAIMER | "... Paper mode only. Local only." | "... Paper mode only." |

Grep (app/, components/, lib/; tests and comments excluded) for money, best bet, ROI, profit,
beat(s) the, alpha, sharp-as-advantage: the remaining hits were judged acceptable because they are
negations, definitions or identifiers:

- negations: evidence/page.tsx:31 "no ... edge, ROI, or bankroll result is claimed"; methodology:255
  "Nothing on this site claims a dollar edge, ROI"; receipts/[row]:238 "the model does not beat the
  market Brier"; HonestFindings:31 and lib/api.ts:197 "does not beat the devigged close";
  sportSignals.ts:49/71 "does not beat the ... curve"; CalibTrendPanel:137 "NOT a market-edge or
  profit metric"; ClvFeedbackPanel:99 "NEVER a profit/ROI target"; HonestBanner:29; riskTerms:52;
  every "Real money is DENY" / "real-money" string.
- definitions: glossary.ts:51 ("An EDGE means ... We do NOT"), glossary.ts:67/98 (BSS sign, vs_close).
- identifiers / testids: BetsMoneyHeadline (component name, money-* testids), moneyline, alpha/beta
  in the shrinkage finding, the forbidden-word regexes.

## 2. CLV -> Unavailable sentinel (components kept, tests updated)

Every CLV tile, strip and stat renders `<Unavailable reason={CLV_UNAVAILABLE} />`:

| placement | before | after |
|---|---|---|
| BetsMoneyHeadline.tsx:191 (testid money-clv) | "MEAN CLV +13.4%", footer "1233 graded vs close; beat-close 36%" | sentence |
| PaperEquityPanel.tsx:217 (paper-tally-clv) | "CLV (MEAN) +13.36%" | sentence |
| paper-trading/PaperTradingTally.tsx:35 (clv-mean-clv) | "MEAN CLV +4.4% (proxy close, n=264)" | sentence |
| paper_pm/VenueSummary.tsx:96 | "CLV (n=..) +x.xx%" per venue | sentence |
| p6/ClvScoreboard.tsx:26 (records, games detail) | "CLV scoreboard (beat the close)", Mean CLV +4.4%, by-sport table | "CLV scoreboard" + sentence |
| records/RecordsClvStrip.tsx:21, RecordsClvSeries.tsx:22 | strip + "CUMULATIVE MEAN CLV +12.99%" curve | sentence (both) |
| paper/PerMarketClvStrips.tsx:22, paper/EvidenceTrendPanel.tsx:13 | median CLV by market, CLV trend | sentence |
| paper/ExecutionQualityPanel.tsx:56 | "avg expected CLV +1.40%" | sentence |
| system/ClvOverTimePanel.tsx:12, p6/ClvFeedbackPanel.tsx:122, p6/PaperHistory.tsx:129 | mean CLV / beat-close stats | sentence |
| bets/BetCardHelpers.tsx:43 (per-card chip) | "CLV +3.2%" | "CLV: unavailable" (title = sentence) |
| paper/page.tsx CLV strip, bets pages banner | Median/Mean CLV tiles; "CLV may show INSUFFICIENT_DATA" | sentence (pages now stubs) |

Equity-curve decision: KEEP the July curve (+101.54u, 100 -> 201.54 units), labelled. Reason: the
units, record and win rate are real snapshot values with source times already printed (P&L
snapshot generated 2026-07-16 01:37:24 UTC), the labelled panel no longer sits under a profit
heading, and hiding it would also hide the record counts the tests pin. The label
JULY_SNAPSHOT_LABEL sits on the panel itself in BetsMoneyHeadline.tsx (money-snapshot-label) and in
PaperEquityPanel.tsx's header (paper-equity-snapshot-label, title "Paper equity -- July 2026 model
snapshot"). The /paper "Paper bankroll" panel title carries the same snapshot wording.

## 3. Home delta sign (app/(terminal)/page.tsx)

cross_sport_scoreboard.json stores paired_delta_mean = market minus model (checked at source:
last_run_ingame_mlb.json total_runs|end_inning_7 market_crps 1.76 - model_crps 1.0273 = +0.7327;
run_mlb.py:152 "positive => market CRPS higher => model sharper"). The header says "model - market".
Fix in computation: new lib/scoreboardDelta.ts `modelMinusMarket()` negates the value and swaps the
interval, rounded to 4 dp (also ends the 18-digit tooltip floats). Before: NBA end_q1 "-0.0084 ...
MARKET SHARPER"; after: "+0.0084 [+0.0008, +0.0161] MARKET SHARPER". The MLB hero reads "-0.7327
CRPS" with "model minus market (lower CRPS is better; negative = model sharper)". Legend under the
table (testid delta-legend): "lower Brier is better; delta = model minus market; positive = model
worse (lower CRPS is better too)." Test: app/(terminal)/__tests__/scoreboard-delta-sign.test.ts;
home.scoreboard.test.tsx updated to the displayed sign.

## 4. Unsupported figures and counts

- /progress "Brier 0.2025 -> 0.0958": the route is now a redirect stub (restructure). The figure
  still lives in components/progress/CompletenessStrip.tsx:6 and :66 (tooltip) -- NOT edited by this
  lane because the component is no longer mounted; left for the restructure lane to delete or
  replace (no packet source).
- Check count: home footer "52/52 on a bare clone" -> read at build time from
  scripts/platformkit/analytics_showcase/out/check_all_report.json: "97 of 111 module self-checks
  PASS, 14 have no self-check; check_all_report.json as of 2026-10-20" (working-tree copy; the
  committed copy says 96 of 110, 14 NO_CHECK, as of 2026-09-17). The analytics "Snapshot checks
  96/96" reads public/data/showcase/check_all_report.json (96 rows, all PASS, as of 2026-07-25) via
  components/analytics/workspace/Workspace.tsx -- analytics lane, not edited.
- Tallies: home strip 168 / 351 / 740 now carries a scope line (testid tally-scope): "rows of the
  four per-sport validation ledgers (domains/<sport>/knowledge/validation_ledger.jsonl),
  honesty_exhibit.json as of 2026-07-22. A different population from the analytics site's published
  research records and from the README's gate-verdict count." The 287 (analytics) and 513 (README)
  are outside this lane.
- Desk dates: components/desk/DeskShell.tsx header (testid desk-dates): "2026-09-24 = first night in
  the fill-realism table (recorded capture history); 2026-10-03 = first ledger night with paper
  fills; 2026-10-06 = start of the prospective forward paper series (JOB_EVIDENCE_PACKET.md section
  5). No verdict yet." (Checked against public/data/desk/latest.json: ledger starts 2026-10-03 with 6
  fills, nights start 2026-09-24.)

## 5. /records as-of

app/(terminal)/records/page.tsx: removed `new Date(...).toLocaleTimeString()` for the as-of and the
"last refreshed" clock; as-of = the data file's as_of / generated_at sliced to YYYY-MM-DD, else
"as-of: the published data file carries no timestamp (July 2026 model snapshot)" (the baked
api_paper_predictions_limit_500.json has neither field). The restructure then replaced /records
with a redirect stub, so this edit is not on the live route.

## 6. Retraction pages

Done by the restructure lane, not this one: both old pages are redirect stubs to
/evidence/retractions/, which parses the packet's section 4 table verbatim (packetTable.ts) and
links the public packet; no tracked webapp file names src/prediction/prop_cv_split.py any more
(grep: zero hits in app/, components/, lib/, public/data/).

## 7. Small items

- Shell-wrapped 404: app/not-found.tsx + app/layout.tsx now exist (restructure lane). This lane did
  not add one: under Next 14.2 a top-level app/not-found.tsx without a root layout exits the build
  (next-app-loader: the default layout is only injected for the built-in not-found page).
- 375 px overflow (home): root container px-6 -> px-4 sm:px-6 plus [overflow-wrap:anywhere]; the
  footer's long mono paths (python scripts/platformkit/analytics_showcase/check_all.py) get
  [overflow-wrap:anywhere]; the POSITIONING chip gets max-w-full flex-wrap. NOT measured in a
  browser (browser pane barred for RAM); the overflowing element was inferred, not confirmed.
- 12 px floor: text-[8..11px] -> text-xs in every file touched here (home, DeskShell,
  BetsMoneyHeadline, PaperEquityPanel, SignalVerdictBadge, ExecutionQualityPanel, records, paper,
  bets). The shared `.microlabel` class lives in globals.css (owned by another lane) and was not
  changed; its size still governs microlabels.
- "Local only." removed from the rendered HONEST_DISCLAIMER (lib/api.ts:216). The two remaining
  hits are source comments (lib/api.ts:16, app/(terminal)/games/page.tsx:9) and do not reach the
  export.

## Left for the restructure lanes

- CompletenessStrip.tsx 0.2025 -> 0.0958 (unmounted component).
- Per-row CLV columns in tables (RecordsTable, PaperTradeRow, PmGradedTable, SettleGradePanel
  "beat close x%", ClvInline, LiveInGamePanel, ExecutionTrail) still print July proxy-close values
  where mounted; aggregate tiles and the card chip are done.
- HomeRecordsHero.tsx (unmounted) still renders a CLV strip.
- public/data/insights/xsport_structure.json title "near-perfectly calibrated" (analytics half).
- Analytics "96/96" vs home "97 of 111" (different report copies, different dates).
- app/(terminal)/page.tsx is 356 lines (was 322 before this lane, already over the 300 cap).

## Verification

See the end of this file for the test and tsc results (appended after the RAM-clear message).
