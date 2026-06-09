# -*- coding: utf-8 -*-
"""
build_stat_outcome.py  —  OUTCOME-IMPACT: per-stat -> outcome decomposition

CourtVision intel/outcome campaign deliverable.

WHAT THIS PRODUCES
------------------
data/cache/intel_outcome/player_stat_outcome.json

For each player (>= 30 games, 2025-26 regular season) it answers the scouting
question: *which of his box-score stats actually moves with his team WINNING?*
Is he a scoring-to-win, playmaking-to-win, rebounding-to-win, or defense-to-win
player? We decompose the association of each per-game box stat with the game
result and with the on-court margin, then label a dominant "win driver".

METHOD (descriptive, leak-free within season; NOT causal)
---------------------------------------------------------
Per player, across his per-game rows:
  (a) WIN association  -> point-biserial correlation between the binary game
      result (W=1 / L=0) and each per-game box stat. Point-biserial is exactly
      the Pearson correlation when one variable is dichotomous, so we compute it
      as Pearson(stat, win). Reported for PTS, AST, REB, STL, BLK (+ TOV, FG_PCT,
      MIN as context). A positive corr means "on nights he posts MORE of this
      stat, his team tends to WIN."
  (b) MARGIN slope     -> univariate OLS slope of his game PLUS_MINUS (his
      on-court point differential, a proxy for team margin while he plays) on
      each stat: "each extra unit of this stat coincides with +X to his on-court
      margin." (plusminus_per_stat).
  (c) MINUTES-RESIDUAL guard -> because minutes drive BOTH winning (blowouts ->
      more minutes for starters; close wins -> stars stay in) AND counting
      stats, we also residualize win and each stat on that player's MIN and
      recompute the win-corr (corr_*_win_resid_min). Where the residualized corr
      collapses toward 0, the raw corr was largely a minutes/role artifact. This
      is a HONESTY guard, surfaced per player and used to flag collinearity.

DOMINANT DRIVER
---------------
Three scouting buckets from the (minutes-residualized) win-corr:
  scoring     = corr_pts_win_resid_min
  playmaking  = corr_ast_win_resid_min
  defense     = corr_stl_win_resid_min + corr_blk_win_resid_min  (stocks)
rebounding is tracked (corr_reb_win) but, per the brief's ranking ask, the
headline leaders_by_driver ranks SCORING vs PLAYMAKING vs DEFENSE. The dominant
driver is the bucket with the largest residualized win-association (must be
positive; else "none/mixed"). We use the residualized corr for the label so the
ranking is not just "minutes ranking in disguise"; raw corrs are also emitted.

HEAVY CAVEATS (collinearity / confounds) — see JSON 'caveats'
-------------------------------------------------------------
* GOOD PLAYERS DO EVERYTHING. Box stats are mutually collinear within a player's
  games (a big scoring night is often also a big minutes/usage night), so a high
  scoring-win corr does NOT mean scoring CAUSED the win — only that it co-moves
  with winning. This is descriptive scouting, not a causal attribution.
* TEAM QUALITY CONFOUND. A player on a good team wins a lot regardless of his
  line; a player on a bad team can post a huge line in a loss. Within-player
  correlation partly controls for fixed team quality (each player is his own
  baseline), but opponent strength, rest, blowout garbage-time, and which games
  he sits are NOT controlled.
* MINUTES / GARBAGE-TIME. PLUS_MINUS and counting stats both inflate in
  blowouts; the resid_min guard flags this but cannot remove it fully.
* SCOUTING ONLY. Not a betting signal, not a player-value ranking.

DATA SOURCE (reconned, schema-checked)
--------------------------------------
data/cache/cv_fix/leaguegamelog_regular_season.parquet
  (2025-26 only, SEASON_ID 22025; 26,651 player-game rows; 582 players; one row
   per player-game; WL in {W,L}; PLUS_MINUS has no nulls.)

Run:  python scripts/intel/outcome/build_stat_outcome.py
"""
import os, sys, io, json, re
import numpy as np
import pandas as pd

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
def rp(*p): return os.path.join(ROOT, *p)

GAMELOG = rp('data', 'cache', 'cv_fix', 'leaguegamelog_regular_season.parquet')
OUT     = rp('data', 'cache', 'intel_outcome', 'player_stat_outcome.json')

SEASON = '2025-26'
MIN_GAMES = 30

# box stats we decompose vs outcome
STAT_COLS = ['PTS', 'AST', 'REB', 'STL', 'BLK', 'TOV', 'FG_PCT', 'MIN']
# stats that get a win-corr surfaced as a named field
WIN_CORR_STATS = ['PTS', 'AST', 'REB', 'STL', 'BLK']


def slugify(name):
    """Match the EXISTING vault note filenames exactly: lowercase, then collapse
    every run of non [a-z0-9] (accented chars NOT ascii-folded) to '_', strip.
    e.g. 'Nikola Jokic'->nikola_joki(c stripped), 'Luka Doncic'->luka_don_i."""
    s = str(name).lower()
    s = re.sub(r'[^a-z0-9]+', '_', s).strip('_')
    return s


def _corr(a, b):
    """Pearson corr; safe for zero-variance -> None."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size < 3:
        return None
    sa, sb = a.std(), b.std()
    if not np.isfinite(sa) or not np.isfinite(sb) or sa == 0 or sb == 0:
        return None
    c = np.corrcoef(a, b)[0, 1]
    return None if not np.isfinite(c) else float(c)


def _slope(x, y):
    """Univariate OLS slope of y on x (y ~ a + b*x). None if degenerate."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 3:
        return None
    vx = x.var()
    if not np.isfinite(vx) or vx == 0:
        return None
    b = np.cov(x, y, bias=True)[0, 1] / vx
    return None if not np.isfinite(b) else float(b)


def _residualize(y, x):
    """Return residuals of y after regressing out x (linear). If x degenerate,
    returns mean-centered y."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    vx = x.var()
    if not np.isfinite(vx) or vx == 0:
        return y - y.mean()
    b = np.cov(x, y, bias=True)[0, 1] / vx
    a = y.mean() - b * x.mean()
    return y - (a + b * x)


def _r3(v):
    return None if v is None else round(float(v), 3)


def main():
    print(f'[recon] loading gamelog {GAMELOG}')
    df = pd.read_parquet(GAMELOG)
    # campaign PRIMARY is 2025-26; source already is single-season 22025, but
    # filter defensively so the script stays correct if the corpus ever grows.
    df = df[df['SEASON_ID'].astype(str) == '22025'].copy()
    df = df[df['MIN'] > 0].copy()  # drop DNP-0min rows (no on-court signal)
    df['WIN'] = (df['WL'] == 'W').astype(int)
    # FG_PCT can be NaN on 0-FGA games; fill with player-game neutral (won't be
    # used for counting-stat corrs, only the FG_PCT context corr where we drop NaN).

    print(f'[recon] season rows={len(df)}  players={df["PLAYER_ID"].nunique()}')

    players = {}
    n_gate = 0
    driver_pool = {'scoring': [], 'playmaking': [], 'defense': []}

    for pid, g in df.groupby('PLAYER_ID'):
        n = int(g['GAME_ID'].nunique())
        if n < MIN_GAMES:
            continue
        n_gate += 1
        name = g['PLAYER_NAME'].iloc[0]
        # primary team = team with most games played
        team = (g.groupby('TEAM_ABBREVIATION')['GAME_ID'].nunique()
                .sort_values().index[-1])

        win = g['WIN'].values
        mins = g['MIN'].values

        rec = {
            'name': name,
            'team': team,
            'slug': slugify(name),
            'n': n,
            'win_pct': round(float(win.mean()), 3),
            'mpg': round(float(mins.mean()), 1),
        }

        # (a) raw point-biserial win-corrs + (c) minutes-residualized win-corrs
        win_resid = _residualize(win, mins)
        for col in WIN_CORR_STATS:
            x = g[col].values
            rec[f'corr_{col.lower()}_win'] = _r3(_corr(x, win))
            x_resid = _residualize(x, mins)
            rec[f'corr_{col.lower()}_win_resid_min'] = _r3(_corr(x_resid, win_resid))

        # context corrs (not headline drivers)
        rec['corr_tov_win'] = _r3(_corr(g['TOV'].values, win))
        # FG_PCT only meaningful where the player attempted shots
        fgmask = g['FGA'].values > 0
        if fgmask.sum() >= 3:
            rec['corr_fg_pct_win'] = _r3(_corr(g['FG_PCT'].values[fgmask], win[fgmask]))
        else:
            rec['corr_fg_pct_win'] = None
        rec['corr_min_win'] = _r3(_corr(mins, win))

        # (b) margin (PLUS_MINUS) slope per stat — descriptive
        pm = g['PLUS_MINUS'].values
        rec['plusminus_per_stat'] = {
            col.lower(): _r3(_slope(g[col].values, pm)) for col in WIN_CORR_STATS
        }
        rec['corr_plusminus_win'] = _r3(_corr(pm, win))  # sanity: should be ~ +1 sign

        # ---- dominant driver from MINUTES-RESIDUALIZED win-corrs ----
        sc = rec['corr_pts_win_resid_min']
        pl = rec['corr_ast_win_resid_min']
        st = rec['corr_stl_win_resid_min']
        bl = rec['corr_blk_win_resid_min']
        defense = None
        if st is not None or bl is not None:
            defense = (st or 0.0) + (bl or 0.0)
        bucket_vals = {
            'scoring': sc,
            'playmaking': pl,
            'defense': defense,
        }
        rec['driver_scores'] = {k: _r3(v) for k, v in bucket_vals.items()}
        # dominant = bucket with largest POSITIVE residualized association
        pos = {k: v for k, v in bucket_vals.items() if v is not None and v > 0}
        if pos:
            dom = max(pos, key=pos.get)
            rec['dominant_driver'] = dom
        else:
            rec['dominant_driver'] = 'none_or_mixed'

        # collinearity / minutes-artifact flag: raw scoring corr strong but
        # residualized collapses -> the raw signal was largely minutes/role.
        raw_pts = rec['corr_pts_win'] or 0.0
        res_pts = rec['corr_pts_win_resid_min'] or 0.0
        rec['minutes_artifact_flag'] = bool(abs(raw_pts) >= 0.20 and abs(res_pts) < 0.5 * abs(raw_pts))

        players[str(int(pid))] = rec

        # pool for leaders ranking (use residualized bucket scores)
        for bk, v in bucket_vals.items():
            if v is not None:
                driver_pool[bk].append((str(int(pid)), name, team, v, rec['dominant_driver']))

    # ---- leaders_by_driver: rank players by each win-driver bucket ----
    leaders = {}
    for bk, pool in driver_pool.items():
        pool_sorted = sorted(pool, key=lambda t: t[3], reverse=True)
        leaders[bk] = [
            {
                'player_id': pid, 'name': nm, 'team': tm,
                'score': _r3(v),
                'is_dominant': (dom == bk),
            }
            for (pid, nm, tm, v, dom) in pool_sorted[:25]
        ]

    meta = {
        'artifact': 'player_stat_outcome',
        'generated_for_campaign': 'intel/outcome (outcome-impact)',
        'scouting_only': True,
        'season': SEASON,
        'method': (
            'Per player (>=%d games), within-season decomposition of each per-game '
            'box stat vs the game OUTCOME: (a) point-biserial win-corr = Pearson(stat, '
            'W=1/L=0); (b) univariate OLS slope of game PLUS_MINUS on the stat '
            '(plusminus_per_stat); (c) minutes-residualized win-corr (resid_min) that '
            'regresses MIN out of both win and the stat as a collinearity/garbage-time '
            'guard. dominant_driver = bucket (scoring=PTS, playmaking=AST, '
            'defense=STL+BLK) with the largest POSITIVE residualized win-association.'
            % MIN_GAMES
        ),
        'min_games_gate': MIN_GAMES,
        'n_players': len(players),
        'units': {
            'corr_*_win': 'point-biserial (Pearson) corr of per-game stat with W=1/L=0, range -1..1',
            'corr_*_win_resid_min': 'same corr after regressing MIN out of BOTH win and the stat (collinearity guard)',
            'plusminus_per_stat.<stat>': 'OLS slope: change in on-court PLUS_MINUS per +1 unit of the stat',
            'driver_scores': 'residualized win-association per bucket; defense = stl+blk resid corrs summed',
        },
        'caveats': [
            'SCOUTING ONLY - descriptive association, NOT causation and NOT a betting signal.',
            'GOOD PLAYERS DO EVERYTHING: box stats are mutually collinear within a player\'s '
            'games, so a high scoring-win corr does NOT mean scoring caused the win - only that '
            'it co-moves with winning. Do not read dominant_driver as a causal attribution.',
            'TEAM-QUALITY CONFOUND: within-player corr controls for FIXED team quality (each '
            'player is his own baseline) but NOT opponent strength, rest, or which games he sits.',
            'MINUTES / GARBAGE-TIME: PLUS_MINUS and counting stats both inflate in blowouts; the '
            'resid_min fields and minutes_artifact_flag flag this but cannot fully remove it.',
            'POINT-BISERIAL is just Pearson with a dichotomous variable; with ~30-80 games per '
            'player these corrs have wide confidence intervals - treat small differences as noise.',
            'plusminus_per_stat is a UNIVARIATE slope (no teammate/opponent control); a positive '
            'slope is co-movement, not marginal value.',
            'dominant_driver uses the MINUTES-RESIDUALIZED bucket scores so the ranking is not '
            'merely a minutes/role ranking in disguise; raw corrs are emitted alongside.',
        ],
    }

    out = {'meta': meta, 'players': players, 'leaders_by_driver': leaders}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f'[write] {OUT}')
    print(f'        players(>= {MIN_GAMES}g) = {len(players)}')

    # console summary
    def _show(bk, label):
        print(f'\nTOP-8 {label} win-drivers (resid_min bucket score):')
        for d in leaders[bk][:8]:
            star = ' *DOM' if d['is_dominant'] else ''
            print(f"  {d['score']:+.3f}  {d['name']:<26} {d['team']}{star}")
    _show('scoring', 'SCORING')
    _show('playmaking', 'PLAYMAKING')
    _show('defense', 'DEFENSE (stl+blk)')

    # clearest scoring-drives vs playmaking-drives (dominant + clear separation)
    def _clearest(bk):
        rows = []
        for pid, r in players.items():
            if r['dominant_driver'] != bk:
                continue
            ds = r['driver_scores']
            own = ds.get(bk)
            if own is None or own <= 0:
                continue
            others = [v for k, v in ds.items() if k != bk and v is not None]
            sep = own - (max(others) if others else 0.0)
            rows.append((sep, own, r['name'], r['team'], pid))
        rows.sort(reverse=True)
        return rows[:5]

    print('\n5 CLEAREST scoring-drives-his-wins:')
    for sep, own, nm, tm, pid in _clearest('scoring'):
        print(f"  sep {sep:+.3f} (score {own:+.3f})  {nm:<26} {tm}")
    print('5 CLEAREST playmaking-drives-his-wins:')
    for sep, own, nm, tm, pid in _clearest('playmaking'):
        print(f"  sep {sep:+.3f} (score {own:+.3f})  {nm:<26} {tm}")


if __name__ == '__main__':
    main()
