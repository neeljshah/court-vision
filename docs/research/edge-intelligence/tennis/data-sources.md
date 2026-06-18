# TENNIS -- DATA SOURCES (have / missing / how-to-get)
_Grounded in data/domains/tennis/ (inspected 2026-06-18) + domains/tennis/ingest_*.py. ASCII.
The binding gap: we have DEEP HISTORY but ZERO same-day prop lines and a thin live feed._

## HAVE (on disk, leak-disciplined)

| Source | Path | Rows | Freshness | Notes |
|---|---|---|---|---|
| ATP matches (Sackmann) | data/domains/tennis/matches.parquet | 30,616 | 2015-01-04 .. 2025-12-17 | 20 cols: event_id, date, surface (Hard 18152 / Clay 9164 / Grass 3228), best_of, round, p1_id<p2_id (SYMMETRIC, leak-safe), winner, score, minutes. The Elo spine. `ingest_sackmann.py`. |
| WTA matches | data/domains/tennis/wta_matches.parquet | 11,270 | 2015 .. 2025-11-01 | same schema, tour=wta. `wta_corpus.py`. Smaller, no odds. |
| ATP odds (Pinnacle/B365/max/avg) | data/domains/tennis/odds.parquet | 25,898 | matched to matches | b365w/l, psw/psl (Pinnacle), maxw/l (best-of-N), avgw/l; ps_p1/ps_p2 + b365_p1/p2 already mapped to the SYMMETRIC id-order (outcome-independent). From tennis-data.co.uk via `ingest_tennisdata*.py`. |
| Match stats (Sackmann) | data/domains/tennis/match_stats.parquet | 59,312 | per match | 38 cols: p1_ace (mean 4.61), p1_df, p1_svpt, p1_1stIn, p1_1stWon, p1_2ndWon, p1_SvGms, p1_bpSaved, p1_bpFaced (+p2), seeds, age, rank_points. THE prop-model ingredient store. |
| As-of hold% (leak-free) | data/domains/tennis/asof_hold.parquet | 30,616 | per event_id | trailing hold% + svpts-won%, overall + per surface (hard/clay/grass), snapshot-before-update, debut=NaN, no-future-leak assert. `asof_hold.py`. Serve-dominance shaping prior. |
| As-of features (leak-free) | data/domains/tennis/asof_features.parquet | 30,616 | per event_id | broader trailing feature block. `asof_features.py`. |
| Postmortem (descriptive) | data/domains/tennis/postmortem.parquet | 30,616 | per match | realized n_breaks (mean 3.73), n_tiebreaks (0.48), straight_sets (0.594), retirement (3.41%), decided_by, noise_flag. Calibration target for games/sets markets. |
| Players | data/domains/tennis/players.parquet | -- | static | id->name, dob, hand, country. |
| ESPN live matches | data/domains/tennis/espn_matches.parquet | 1,610 | 2026-06-06 .. 2026-06-21 | comp_id, set scores s1..s5 + tiebreak tb1..tb5, status, winner, sets_won, best_of. The LIVE / same-day feed. `ingest_espn.py`. Set/tiebreak granularity only -- NO point/game stream, NO odds. |

## MISSING (the gaps that cap edge)

1. **Tennis PROP lines -- entirely absent.** odds.parquet is match-winner two-way only. There is NO
   scraped line for: total games O/U, total sets O/U, set handicap, correct set score, ACES O/U,
   double-faults, 1st-serve-%, break-points. The prop scraper stack (deep-dive 03) maps ONLY
   soccer_intl (`prop_edge._SUPPORTED == {"soccer_intl"}`); no tennis provider exists at all. This
   blocks EVERY P1 soft-prop pocket -- we can PRICE these markets (markets.py) but have nothing to
   price them AGAINST.
2. **WTA odds -- absent.** No wta_odds.parquet. We cannot run the beat-the-close test for WTA, so the
   "WTA closes are softer" hypothesis is untestable today.
3. **Same-day / pre-match FRESHNESS for the model.** matches.parquet ends 2025-12-17; espn_matches is
   the only 2026 feed and it carries no rankings/withdrawals/walkover-news. The model never sees the
   injury/late-withdrawal/conditions info that drives Pinnacle's +0.0149 Brier edge. This is THE
   structural reason pregame is efficient-against-us (cut-list CUT-1 logic).
4. **Point-by-point / in-set game path.** espn_matches gives set scores + tiebreak flags, not the
   per-point or per-game serve sequence. So `markets.POINT_MODEL_GAPS` (tie-break Y/N, within-set
   games, exact game score) stay unpriceable and there is no live game/point repricer.
5. **Live ODDS for in-game.** We can reprice after each set (repricer.py) but scrape no in-play
   tennis line, so the in-game lift is calibration-only with no CLV channel.

## HOW-TO-GET (keyless-first, mirrors deep-dive 03 scraper stack)

- **Tennis match-winner live odds (keyless):** ESPN `summary?event=<id>` exposes `pickcenter[]`
  republished moneylines for tennis the same way it does for NBA/MLB (deep-dive 03 sec 2b). Add a
  tennis league map to `odds_provider/espn.py` (`tennis -> tennis/atp` etc.) -> instant keyless
  moneyline + a live-odds channel to start CLV capture. LOWEST-effort, model-free.
- **Tennis props (keyless, the real prize):** PrizePicks `/projections` and Underdog
  `beta/v5/over_under_lines` BOTH carry a TENNIS league (games, aces, sets pick'em/lines) on the
  SAME endpoints the soccer providers already hit. Add `prop_prizepicks`/`prop_underdog` tennis
  league resolution + a `prop_edge` tennis branch (lift `_SUPPORTED` to include tennis). This is the
  single highest-leverage data add: it UNBLOCKS the P1 pocket. Validate parser on real payload first.
- **Best-price multi-book moneyline:** already on disk (odds.parquet max/avg). For live, The Odds API
  `tennis_atp` h2h via the existing keyed `odds_shop.fetch_odds` adds multi-book best-line for true
  line-shopping (deep-dive 03 #7). Keyless default + optional keyed "more books".
- **Continued Sackmann refresh:** `ingest_sackmann.py` / `ingest_sackmann_matchstats.py` pull the
  CC-BY-NC-SA GitHub CSVs (private research use only); re-run to roll history forward to current.
- **WTA odds:** tennis-data.co.uk publishes WTA odds files; extend `ingest_tennisdata*.py` with the
  WTA path to build wta_odds.parquet and unblock the WTA beat-the-close test.

## The same-day-freshness gap (one line)
We have arguably the DEEPEST tennis history of any sport we model (30.6k ATP + 11.3k WTA matches,
59k match-stat rows, leak-free as-of hold). The ceiling is NOT history depth -- it is (a) zero prop
lines to price against, and (b) no same-day injury/withdrawal/conditions feed, which is exactly the
information Pinnacle uses to be 0.0149 Brier sharper than our Elo.
