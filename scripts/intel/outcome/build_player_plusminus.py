# -*- coding: utf-8 -*-
"""
build_player_plusminus.py  —  OUTCOME-IMPACT: player plus-minus (raw + adjusted)

CourtVision intel/outcome campaign deliverable.

WHAT THIS PRODUCES
------------------
data/cache/intel_outcome/player_plusminus.json

Two layers of player outcome-impact, each with an honestly-labelled method:

  PRIMARY block  -> season 2025-26 (campaign PRIMARY), per player:
      raw_pm_per_game   raw season +/- per game            (descriptive baseline)
      raw_pm_per100     raw season +/- per 100 possessions (descriptive baseline)
      adj_impact        on/off-adjusted impact per 100      (method = "onoff-adjusted")
      minutes, gp, confidence
    METHOD = "onoff-adjusted" for 2025-26 because TRUE stint-composition RAPM is
    NOT recoverable for 2025-26 in this repo: lineup_splits exists for only 2/30
    teams and carries 0 possessions for that season. So we fall back, as the
    campaign brief instructs, to an on/off-adjusted box-style estimate and label
    it clearly. The adjustment removes the team-strength component from a player's
    raw +/- (minute-weighted team baseline) and Bayes-shrinks toward 0 by minutes.

  rapm_2024_25 block -> a TRUE ridge-RAPM, fit on 2024-25 5-man lineup net-ratings
    (all 30 teams, ~146k possessions in lineup_splits), included as a validated
    demonstration of the genuine method. METHOD = "ridge-RAPM (lineup, offense-stint)".
    This is RAPM-lite: it regresses possession-weighted 5-man NET rating on player
    on-court indicators with an L2 (ridge) penalty, controlling for teammates.
    Variant note: NBA lineup_splits gives a lineup's own NET rating (not paired
    offense/defense stints vs a specific opponent unit), so this is the standard
    "single-side lineup RAPM" descriptive variant, leak-free within-season.

DATA SOURCES (reconned, schema-checked):
  - data/cache/cv_fix/leaguegamelog_regular_season.parquet  (2025-26 full season:
        1230 games, 582 players; per-game PLUS_MINUS + MIN + team + name + id)
  - data/team_advanced_stats.parquet  (per-game team PACE -> possessions estimate)
  - data/nba/lineups/lineup_splits_<TEAM>_<SEASON>.json  (5-man NET rating, poss,
        minutes, lineup names; 30 teams for 2024-25)
  - data/cache/on_off_features.parquet, data/intelligence/lineup_chemistry.parquet,
        data/intelligence/pair_chemistry.parquet  (id<->name<->team resolution)

LEAK / CONFOUND CAVEATS (documented in JSON 'caveats'):
  * Raw +/- is contaminated by teammate & opponent quality and by which lineups a
    coach deploys; it is a descriptive baseline, not skill.
  * onoff-adjusted removes only the *team-level* strength component + shrinks small
    samples; it does NOT control for specific teammates the way true RAPM does.
  * ridge-RAPM (2024-25) controls for teammates but is single-side (offense stint),
    has ridge bias toward 0 (regularized), and name->id resolution is ~97.7%.
  * SCOUTING ONLY. Not a betting signal.

Run:  python scripts/intel/outcome/build_player_plusminus.py
"""
import os, sys, io, json, glob, re, collections, unicodedata
import numpy as np
import pandas as pd

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
def rp(*p): return os.path.join(ROOT, *p)

GAMELOG  = rp('data', 'cache', 'cv_fix', 'leaguegamelog_regular_season.parquet')
TEAMADV  = rp('data', 'team_advanced_stats.parquet')
ONOFF    = rp('data', 'cache', 'on_off_features.parquet')
LINCHEM  = rp('data', 'intelligence', 'lineup_chemistry.parquet')
PAIRCHEM = rp('data', 'intelligence', 'pair_chemistry.parquet')
LINEDIR  = rp('data', 'nba', 'lineups')
OUT      = rp('data', 'cache', 'intel_outcome', 'player_plusminus.json')

PRIMARY_SEASON = '2025-26'
RAPM_SEASON    = '2024-25'

# ridge lambda for RAPM. League-typical RAPM ridge ~ several hundred-thousand on
# raw possession-weighted designs; on our scale (rows weighted by poss/100, target
# in NET points/100) lambda chosen by leave-out CV below, seeded near a sane prior.
RAPM_LAMBDA_GRID = [50.0, 100.0, 200.0, 400.0, 800.0, 1600.0, 3200.0, 6400.0, 12800.0]

# minutes shrink prior for onoff-adjusted (Bayes regress-to-0). ~ a full rotation
# player's minutes; smaller-sample players pulled harder to 0.
SHRINK_MIN = 600.0


# --------------------------------------------------------------------------- #
# id <-> name resolution
# --------------------------------------------------------------------------- #
def _ascii(s):
    return unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()

def _comma_to_full(nm):
    if isinstance(nm, str) and ',' in nm:
        last, first = [x.strip() for x in nm.split(',', 1)]
        return f"{first} {last}"
    return nm

def _abbr(full):
    """'LeBron James' -> 'L. James' (ascii)."""
    parts = str(full).split()
    if len(parts) < 2:
        return None
    return _ascii(f"{parts[0][0]}. {' '.join(parts[1:])}")

def build_id_name_maps():
    id2name = {}
    # gamelog (authoritative, full names, 2025-26)
    gl = pd.read_parquet(GAMELOG)[['PLAYER_ID', 'PLAYER_NAME']].drop_duplicates()
    for pid, nm in gl.itertuples(index=False):
        id2name.setdefault(int(pid), nm)
    # on_off
    oo = pd.read_parquet(ONOFF)[['player_id', 'player_name']].drop_duplicates()
    for pid, nm in oo.itertuples(index=False):
        id2name.setdefault(int(pid), _comma_to_full(nm))
    # lineup_chemistry
    lc = pd.read_parquet(LINCHEM)[['player_id', 'player_name']].drop_duplicates()
    for pid, nm in lc.itertuples(index=False):
        id2name.setdefault(int(pid), nm)
    # pair_chemistry
    pc = pd.read_parquet(PAIRCHEM)
    for cid, cnm in [('player_A_id', 'player_A_name'), ('player_B_id', 'player_B_name')]:
        for pid, nm in pc[[cid, cnm]].dropna().drop_duplicates().itertuples(index=False):
            id2name.setdefault(int(pid), nm)

    abbr2ids = collections.defaultdict(set)
    for pid, nm in id2name.items():
        a = _abbr(nm)
        if a:
            abbr2ids[a].add(pid)
    return id2name, abbr2ids


def team_roster_abbr(season):
    """team -> {'F. Last'(ascii): player_id} from on_off for the season."""
    oof = pd.read_parquet(ONOFF)
    sub = oof[oof['season'] == season]
    roster = collections.defaultdict(dict)
    for _, r in sub.iterrows():
        full = _comma_to_full(r['player_name'])
        a = _abbr(full)
        if a:
            roster[r['team_abbreviation']][a] = int(r['player_id'])
    return roster


# --------------------------------------------------------------------------- #
# season helpers
# --------------------------------------------------------------------------- #
def _sid_to_season(sid):
    s = str(sid); yr = int(s[1:])
    return f"{yr}-{str(yr+1)[2:]}"


# --------------------------------------------------------------------------- #
# RAW + ON/OFF-ADJUSTED  (2025-26, from gamelog)
# --------------------------------------------------------------------------- #
def build_primary_2025_26():
    gl = pd.read_parquet(GAMELOG)
    gl['season'] = gl['SEASON_ID'].map(_sid_to_season)
    gl = gl[gl['season'] == PRIMARY_SEASON].copy()
    gl['GAME_DATE'] = pd.to_datetime(gl['GAME_DATE'])

    # team possessions per game from team_advanced_stats pace (poss per 48).
    tadv = pd.read_parquet(TEAMADV)[['game_id', 'team_tricode', 'pace']].copy()
    tadv = tadv.rename(columns={'game_id': 'GAME_ID', 'team_tricode': 'TEAM_ABBREVIATION'})
    gl = gl.merge(tadv, on=['GAME_ID', 'TEAM_ABBREVIATION'], how='left')
    # player possessions in a game ~= team_pace * (player_min / 48)
    gl['player_poss'] = gl['pace'] * (gl['MIN'] / 48.0)

    # season aggregates
    agg = gl.groupby(['PLAYER_ID', 'PLAYER_NAME']).agg(
        pm=('PLUS_MINUS', 'sum'),
        mins=('MIN', 'sum'),
        gp=('GAME_ID', 'nunique'),
        poss=('player_poss', 'sum'),
    ).reset_index()

    # primary team = team with most games played
    tg = (gl.groupby(['PLAYER_ID', 'TEAM_ABBREVIATION'])['GAME_ID'].nunique()
          .reset_index().sort_values('GAME_ID').drop_duplicates('PLAYER_ID', keep='last'))
    team_of = dict(zip(tg['PLAYER_ID'], tg['TEAM_ABBREVIATION']))
    agg['team'] = agg['PLAYER_ID'].map(team_of)

    agg = agg[agg['mins'] > 0].copy()
    agg['raw_pm_per_game'] = agg['pm'] / agg['gp']
    # per-100 possessions (fall back to minute-based poss estimate if pace missing)
    poss_ok = agg['poss'].fillna(0) > 0
    agg['raw_pm_per100'] = np.where(
        poss_ok, agg['pm'] / agg['poss'].replace(0, np.nan) * 100.0,
        agg['pm'] / agg['mins'] * 100.0 * (48.0 / 100.0))  # crude fallback

    # ---- team-strength baseline (minute-weighted mean of player per100 on a team)
    have_team = agg.dropna(subset=['team']).copy()
    def _wmean(d):
        w = d['mins'].values
        return float(np.average(d['raw_pm_per100'].values, weights=w)) if w.sum() > 0 else 0.0
    team_base = have_team.groupby('team').apply(_wmean, include_groups=False)
    agg['team_base_per100'] = agg['team'].map(team_base).fillna(0.0)

    # on/off-adjusted impact:
    #   1) remove team-level strength so a player is not credited with team quality
    #   2) Bayes-shrink toward 0 by minutes (small samples -> regress to mean)
    rel = agg['raw_pm_per100'] - agg['team_base_per100']
    shrink = agg['mins'] / (agg['mins'] + SHRINK_MIN)
    agg['adj_impact'] = rel * shrink

    # confidence: minutes-driven, capped
    agg['confidence'] = (agg['mins'] / 1500.0).clip(0.0, 1.0).round(3)
    agg['low_minute_flag'] = agg['mins'] < 250

    return agg


# --------------------------------------------------------------------------- #
# TRUE RIDGE-RAPM  (2024-25, from lineup_splits, all 30 teams)
# --------------------------------------------------------------------------- #
def build_ridge_rapm(season, id2name, abbr2ids):
    roster = team_roster_abbr(season)
    files = sorted(glob.glob(os.path.join(LINEDIR, f'lineup_splits_*_{season}.json')))
    if not files:
        return None

    rows = []          # (resolved_player_ids tuple, net_rtg, poss)
    player_index = {}  # pid -> col
    unresolved = collections.Counter()
    n_lineups = 0
    teams = set()
    for f in files:
        tm = re.search(r'_([A-Z]{3})_', f).group(1); teams.add(tm)
        with open(f, encoding='utf-8') as fh:
            lus = json.load(fh)
        for lu in lus:
            names = lu.get('lineup') or []
            if len(names) != 5:
                continue
            net = lu.get('net_rtg', lu.get('net_rating'))
            poss = lu.get('poss') or lu.get('possessions') or 0
            if net is None or poss is None or poss <= 0:
                continue
            pids = []
            ok = True
            for n in names:
                na = _ascii(n)
                pid = roster.get(tm, {}).get(na)
                if pid is None:
                    cand = abbr2ids.get(na, set())
                    pid = next(iter(cand)) if len(cand) == 1 else None
                if pid is None:
                    unresolved[(tm, n)] += 1
                    ok = False
                    continue
                pids.append(pid)
            if not ok or len(pids) != 5:
                continue
            for pid in pids:
                if pid not in player_index:
                    player_index[pid] = len(player_index)
            rows.append((tuple(pids), float(net), float(poss)))
            n_lineups += 1

    if not rows or not player_index:
        return None

    P = len(player_index)
    N = len(rows)
    X = np.zeros((N, P), dtype=np.float32)
    y = np.zeros(N, dtype=np.float32)
    w = np.zeros(N, dtype=np.float32)
    for i, (pids, net, poss) in enumerate(rows):
        for pid in pids:
            X[i, player_index[pid]] = 1.0
        y[i] = net
        w[i] = poss

    # weighted ridge with CV over lambda grid (5-fold on lineups, weighted)
    rng = np.random.RandomState(17)
    order = rng.permutation(N)
    folds = np.array_split(order, 5)
    sw = np.sqrt(w)

    def fit_ridge(Xtr, ytr, wtr, lam):
        Xw = Xtr * np.sqrt(wtr)[:, None]
        yw = ytr * np.sqrt(wtr)
        A = Xw.T @ Xw + lam * np.eye(Xtr.shape[1], dtype=np.float64)
        b = Xw.T @ yw
        return np.linalg.solve(A, b)

    best_lam, best_err = None, np.inf
    for lam in RAPM_LAMBDA_GRID:
        errs = []
        for k in range(5):
            te = folds[k]
            tr = np.concatenate([folds[j] for j in range(5) if j != k])
            beta = fit_ridge(X[tr], y[tr], w[tr], lam)
            pred = X[te] @ beta
            err = np.average((pred - y[te]) ** 2, weights=w[te])
            errs.append(err)
        m = float(np.mean(errs))
        if m < best_err:
            best_err, best_lam = m, lam

    beta = fit_ridge(X, y, w, best_lam)

    # per-player on-court possessions (confidence)
    poss_on = collections.Counter()
    for (pids, net, poss) in rows:
        for pid in pids:
            poss_on[pid] += poss

    inv_index = {v: k for k, v in player_index.items()}
    players = {}
    for col, coef in enumerate(beta):
        pid = inv_index[col]
        pn = poss_on[pid]
        players[pid] = {
            'name': id2name.get(pid, f'id_{pid}'),
            'rapm_per100': round(float(coef), 3),
            'oncourt_poss': int(pn),
            'confidence': round(min(pn / 4000.0, 1.0), 3),
        }
    meta = {
        'method': 'ridge-RAPM (lineup, offense-stint, single-side; descriptive within-season)',
        'season': season,
        'lambda': best_lam,
        'lambda_grid': RAPM_LAMBDA_GRID,
        'cv_weighted_mse': round(best_err, 3),
        'n_lineups_used': n_lineups,
        'n_players': P,
        'teams_covered': len(teams),
        'n_unresolved_name_slots': len(unresolved),
    }
    return meta, players


# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #
def main():
    print('[recon] building id<->name maps ...')
    id2name, abbr2ids = build_id_name_maps()
    print(f'        union id->name = {len(id2name)}')

    print(f'[primary] computing raw + onoff-adjusted for {PRIMARY_SEASON} ...')
    prim = build_primary_2025_26()
    print(f'          players = {len(prim)}')

    # assemble primary players block
    players = {}
    for _, r in prim.iterrows():
        pid = int(r['PLAYER_ID'])
        players[str(pid)] = {
            'name': r['PLAYER_NAME'],
            'team': (None if pd.isna(r['team']) else r['team']),
            'raw_pm_per_game': round(float(r['raw_pm_per_game']), 3),
            'raw_pm_per100': round(float(r['raw_pm_per100']), 3),
            'adj_impact': round(float(r['adj_impact']), 3),
            'minutes': round(float(r['mins']), 1),
            'gp': int(r['gp']),
            'confidence': float(r['confidence']),
            'low_minute_flag': bool(r['low_minute_flag']),
        }

    # leaders / laggards by adjusted impact (min minutes gate for credibility)
    GATE = 500.0
    elig = prim[prim['mins'] >= GATE].copy()
    elig = elig.sort_values('adj_impact', ascending=False)
    def _row(r):
        return {
            'player_id': str(int(r['PLAYER_ID'])),
            'name': r['PLAYER_NAME'],
            'team': (None if pd.isna(r['team']) else r['team']),
            'adj_impact': round(float(r['adj_impact']), 3),
            'raw_pm_per100': round(float(r['raw_pm_per100']), 3),
            'minutes': round(float(r['mins']), 1),
        }
    leaders = [_row(r) for _, r in elig.head(15).iterrows()]
    laggards = [_row(r) for _, r in elig.tail(5).iterrows()]

    print(f'[rapm] fitting TRUE ridge-RAPM on {RAPM_SEASON} lineup_splits ...')
    rapm = build_ridge_rapm(RAPM_SEASON, id2name, abbr2ids)
    rapm_block = None
    if rapm is not None:
        rmeta, rplayers = rapm
        print(f"       lambda={rmeta['lambda']} teams={rmeta['teams_covered']} "
              f"lineups={rmeta['n_lineups_used']} players={rmeta['n_players']}")
        rapm_sorted = sorted(rplayers.items(),
                             key=lambda kv: kv[1]['rapm_per100'], reverse=True)
        # credible RAPM leaders (>= 2000 on-court possessions)
        cred = [(pid, d) for pid, d in rapm_sorted if d['oncourt_poss'] >= 2000]
        rapm_block = {
            **rmeta,
            'players': {str(pid): d for pid, d in rplayers.items()},
            'leaders': [{'player_id': str(pid), **d} for pid, d in cred[:15]],
            'laggards': [{'player_id': str(pid), **d} for pid, d in cred[-5:]],
        }

    out = {
        'artifact': 'player_plusminus',
        'generated_for_campaign': 'intel/outcome (outcome-impact)',
        'scouting_only': True,
        'method': 'onoff-adjusted',   # the method actually used for the PRIMARY block
        'method_rationale': (
            'True teammate-controlled RAPM is NOT recoverable for 2025-26 in this repo '
            '(lineup_splits covers only 2/30 teams with 0 possessions for that season), '
            'so the PRIMARY 2025-26 adjusted impact falls back to an on/off-adjusted '
            'box-style estimate: raw +/-100 minus minute-weighted team baseline, '
            'Bayes-shrunk toward 0 by minutes. A genuine ridge-RAPM IS provided for '
            '2024-25 (all 30 teams) in the rapm_2024_25 block as method validation.'),
        'lambda': None,  # not applicable to onoff-adjusted; ridge lambda lives in rapm_2024_25
        'primary_season': PRIMARY_SEASON,
        'shrink_min_prior': SHRINK_MIN,
        'units': {
            'raw_pm_per_game': 'point differential while on court, per game (descriptive)',
            'raw_pm_per100': 'point differential per 100 possessions (descriptive baseline)',
            'adj_impact': 'onoff-adjusted points per 100 poss vs team baseline, minute-shrunk',
            'minutes': 'total regular-season minutes',
            'confidence': '0..1, minutes/1500 capped',
            'rapm_per100': 'ridge-regularized adjusted +/- per 100 poss (2024-25 block)',
        },
        'n_players_primary': len(players),
        'leaders': leaders,
        'laggards': laggards,
        'players': players,
        'rapm_2024_25': rapm_block,
        'caveats': [
            'SCOUTING ONLY - not a betting signal.',
            'raw_pm_* are descriptive and contaminated by teammate/opponent quality and coach deployment.',
            'onoff-adjusted removes only TEAM-level strength + shrinks small samples; '
            'it does NOT control for specific teammates the way true RAPM does. Labelled accordingly.',
            '2025-26 possessions are ESTIMATED from team pace x (player_min/48); '
            'per100 is an estimate, not box-exact.',
            'rapm_2024_25 is a TRUE ridge-RAPM but single-side (lineup own NET rating, not '
            'opponent-paired stints), ridge-biased toward 0, with ~97.7% name->id resolution.',
            'Leaders gated to >=500 min (primary) / >=2000 on-court poss (RAPM) for credibility.',
        ],
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f'[write] {OUT}')
    print(f'        primary players={len(players)}  '
          f'rapm_players={0 if rapm_block is None else rapm_block["n_players"]}')

    # console summary
    print('\nTOP-15 onoff-adjusted impact (2025-26, >=500 min):')
    for d in leaders:
        print(f"  {d['adj_impact']:+6.2f}  {d['name']:<26} {d['team']}  "
              f"(raw100 {d['raw_pm_per100']:+5.1f}, {d['minutes']:.0f} min)")
    print('BOTTOM-5:')
    for d in laggards:
        print(f"  {d['adj_impact']:+6.2f}  {d['name']:<26} {d['team']}")
    if rapm_block:
        print(f"\nTRUE ridge-RAPM 2024-25 (lambda={rapm_block['lambda']}), top-10 (>=2000 poss):")
        for d in rapm_block['leaders'][:10]:
            print(f"  {d['rapm_per100']:+6.2f}  {d['name']:<26} ({d['oncourt_poss']} poss)")


if __name__ == '__main__':
    main()
