"""
INTEL-GENERATED EDGE HUNT (leak-free, cross-season gated)
=========================================================
Mission: use the intelligence vault (player playstyle/archetype/quarter/rebound
atlases) to GENERATE specific conditional betting hypotheses, then let the
leak-free real-odds harness JUDGE each one. Intelligence generates the rule;
numbers decide.

DISCIPLINE
- Reuse the existing leak-free real-odds bet table: data/cache/edge_mining_bets.parquet
  (prod-stack walk-forward OOF; bet side = sign(pred-line); won at ACTUAL odds; |odds|>=100).
- Each hypothesis is a SELECTION FILTER or SIZING TILT on an EXISTING bet (AST/REB),
  NOT a new point feature (point-feature wiring already rejected, see INTEL_CAMPAIGN_PUNCHLIST).
- Corpora: benashkar_2526 = IN-WINDOW (2025-26). oddsapi_2425 = INDEPENDENT cross-season gate (2024-25).
- The intelligence atlases (usage_role/scoring/playmaking/quarter/reb) are PLAYER-IDENTITY
  fixed priors (as_of 2025-26 mostly). For the 2024-25 corpus they are a future-built trait
  prior -> the genuine test is whether a STABLE player-identity conditioner concentrates the
  edge cross-season (trait-stability gate). For benashkar they are same-season (descriptive).
- MANDATORY: cross-season SIGN gate. In-window peaks that flip/vanish cross-season = PEAK (reject).
- NO in-sample threshold tuning: splits use the atlas's own categorical labels or pre-registered
  median/tercile cut points (chosen from the atlas distribution, not from ROI).
- Decompose survivors AST-style: OVER vs UNDER balance (selection not tilt); complement-slice check.
"""
import pandas as pd, numpy as np, json, os, sys

np.random.seed(7)
BASE = r'C:\Users\neelj\nba-ai-system\data\cache'


def load():
    bets = pd.read_parquet(os.path.join(BASE, 'edge_mining_bets.parquet'))
    bets = bets[bets.odds.abs() >= 100].copy()
    # ---- join player-identity atlas conditioners (one row per player) ----
    ur = pd.read_parquet(os.path.join(BASE, 'atlas_player_usage_role.parquet'))
    ur = ur[['player_id', 'creator_role', 'usage_tier', 'ast_pct', 'iso_poss_pg',
             'pnr_handler_pg', 'transition_poss_pg', 'on_off_impact_z', 'usage_rate']]
    sc = pd.read_parquet(os.path.join(BASE, 'atlas_player_scoring_creation.parquet'))
    sc = sc[['player_id', 'catch_shoot_3pa_per_g', 'drive_ast_rate', 'pts_paint_share',
             'pts_3pt_share', 'drives_per_game', 'assisted_share_3pm', 'unassisted_share_2pm']]
    pn = pd.read_parquet(os.path.join(BASE, 'atlas_player_playmaking_network.parquet'))
    pn = pn[['player_id', 'ast_to_tov', 'potential_ast', 'pnr_bh_poss_fraction', 'drive_ast']]
    for c in ['ast_to_tov', 'potential_ast', 'pnr_bh_poss_fraction', 'drive_ast']:
        pn[c] = pd.to_numeric(pn[c], errors='coerce')
    qs = pd.read_parquet(os.path.join(BASE, 'atlas_player_quarter_shape_fatigue.parquet'))
    qs = qs[['player_id', 'q4_fade_abs', 'q4_vs_early_ratio', 'b2b_pts_delta']]
    for c in ['q4_fade_abs', 'q4_vs_early_ratio', 'b2b_pts_delta']:
        qs[c] = pd.to_numeric(qs[c], errors='coerce')
    rb = pd.read_parquet(os.path.join(BASE, 'atlas_player_rebounding_profile.parquet'))
    rb = rb[['player_id', 'oreb_dreb_ratio', 'reb_consistency_cv', 'oreb_rate_mean',
             'dreb_rate_mean', 'total_reb_rate_mean']].drop_duplicates('player_id')
    for c in ['oreb_dreb_ratio', 'reb_consistency_cv', 'oreb_rate_mean', 'dreb_rate_mean',
              'total_reb_rate_mean']:
        rb[c] = pd.to_numeric(rb[c], errors='coerce')

    for atl in (ur, sc, pn, qs, rb):
        atl.drop_duplicates('player_id', inplace=True)
    m = bets.merge(ur, left_on='pid', right_on='player_id', how='left').drop(columns='player_id')
    m = m.merge(sc, left_on='pid', right_on='player_id', how='left').drop(columns='player_id')
    m = m.merge(pn, left_on='pid', right_on='player_id', how='left').drop(columns='player_id')
    m = m.merge(qs, left_on='pid', right_on='player_id', how='left').drop(columns='player_id')
    m = m.merge(rb, left_on='pid', right_on='player_id', how='left').drop(columns='player_id')
    return m


def roi(df):
    """ROI% per $100 unit on the model-side bets in df (already settled: 'pnl')."""
    if len(df) == 0:
        return np.nan, 0, np.nan
    r = df['pnl'].mean()
    w = (df['won'] == 1).mean() * 100
    return r, len(df), w


def boot_ci(df, n_boot=2000):
    if len(df) < 5:
        return (np.nan, np.nan)
    pnl = df['pnl'].values
    idx = np.random.randint(0, len(pnl), size=(n_boot, len(pnl)))
    means = pnl[idx].mean(axis=1)
    return (np.percentile(means, 2.5), np.percentile(means, 97.5))


def coherence(df):
    """blind OVER roi + blind UNDER roi at the SAME odds; healthy ~ -2*vig (<0).
    The bet table only stores the model-side outcome, so we recompute both blind sides
    from won/bet_over: a blind-OVER win iff actual>line; payout uses stored odds with
    the convention that 'odds' is the side actually bet. We approximate using model rows:
    blind side ROI is not exactly recoverable per-side here, so we report the model-side
    pnl sum as a sanity scalar instead. (Coherence already validated on this table upstream.)"""
    return df['pnl'].mean()


def grade(df_all, stat, mask_fn, label, note):
    """Grade a selection on AST/REB model-side bets, in-window vs cross-season."""
    out = {'hypothesis': label, 'note': note, 'stat': stat}
    base = df_all[df_all.stat == stat]
    for corp, key in [('benashkar_2526', 'in'), ('oddsapi_2425', 'cross')]:
        d = base[base.corpus == corp].copy()
        sel = d[mask_fn(d)]
        comp = d[~mask_fn(d)]
        r, n, w = roi(sel)
        rc, nc, wc = roi(comp)
        lo, hi = boot_ci(sel)
        out[f'{key}_roi'] = round(r, 2) if not np.isnan(r) else None
        out[f'{key}_n'] = n
        out[f'{key}_win'] = round(w, 1) if not np.isnan(w) else None
        out[f'{key}_ci'] = (round(lo, 1), round(hi, 1)) if not np.isnan(lo) else None
        out[f'{key}_comp_roi'] = round(rc, 2) if not np.isnan(rc) else None
        out[f'{key}_comp_n'] = nc
        # over/under balance within the selection (selection-vs-tilt signature)
        if n > 0:
            ov = sel[sel.bet_over]
            un = sel[~sel.bet_over]
            out[f'{key}_over_roi'] = round(ov['pnl'].mean(), 2) if len(ov) else None
            out[f'{key}_over_n'] = len(ov)
            out[f'{key}_under_roi'] = round(un['pnl'].mean(), 2) if len(un) else None
            out[f'{key}_under_n'] = len(un)
    return out


def verdict(row):
    iw = row.get('in_roi'); cs = row.get('cross_roi')
    inn = row.get('in_n', 0); cn = row.get('cross_n', 0)
    if iw is None or cs is None:
        return 'NULL (no coverage)'
    if cn < 12:
        # cross-season too thin to gate sign reliably
        if iw > 1.0:
            return f'PEAK? (cross n={cn} too thin to gate)'
        return 'NULL'
    if iw > 0 and cs > 0:
        return 'DURABLE-CANDIDATE'  # both seasons positive -> decompose further
    if iw > 1.0 and cs <= 0:
        return 'PEAK (in-window only, flips cross-season)'
    return 'NULL'


def main():
    df = load()
    print('joined bets (|odds|>=100):', len(df))
    # baseline reference per stat per corpus (whole-stat model-side)
    print('\n=== BASELINE (whole-stat, model side) ===')
    for stat in ['ast', 'reb', 'pts']:
        for corp in ['benashkar_2526', 'oddsapi_2425']:
            r, n, w = roi(df[(df.stat == stat) & (df.corpus == corp)])
            print(f'  {stat:4s} {corp:16s} ROI {r:+6.2f}% n={n:4d} win={w:.1f}%')

    # median/tercile cut points computed on benashkar AST/REB rows (pre-registered, not ROI-tuned)
    ast_in = df[(df.stat == 'ast') & (df.corpus == 'benashkar_2526')]
    reb_in = df[(df.stat == 'reb') & (df.corpus == 'benashkar_2526')]
    cut = {
        'ast_pct_hi': df.loc[df.stat == 'ast', 'ast_pct'].median(),
        'ast_to_tov_hi': df.loc[df.stat == 'ast', 'ast_to_tov'].median(),
        'pnr_frac_hi': df.loc[df.stat == 'ast', 'pnr_bh_poss_fraction'].median(),
        'drive_ast_hi': df.loc[df.stat == 'ast', 'drive_ast'].median(),
        'potential_ast_hi': df.loc[df.stat == 'ast', 'potential_ast'].median(),
        'oreb_ratio_hi': df.loc[df.stat == 'reb', 'oreb_dreb_ratio'].median(),
        'reb_cv_hi': df.loc[df.stat == 'reb', 'reb_consistency_cv'].median(),
        'cs3pa_hi': df.loc[df.stat == 'fg3m', 'catch_shoot_3pa_per_g'].median(),
        'q4fade_hi': df.loc[:, 'q4_fade_abs'].median(),
    }
    print('\ncut points (pre-registered medians):', {k: round(v, 3) for k, v in cut.items() if pd.notna(v)})

    H = []
    # ---------- AST selection/sizing hypotheses ----------
    # H1: creator role -> AST. Primary/secondary creators carry "real" AST; spot-up AST is noise.
    H.append(grade(df, 'ast', lambda d: d.creator_role.isin(['primary_creator', 'secondary_creator']),
                    'H1 AST | creator-role (primary/secondary)',
                    'Creators own the assist; spot-up AST lines are role-noise -> concentrate AST on real playmakers.'))
    # H2: high ast_to_tov -> AST (efficient distributors hit their AST lines more reliably)
    H.append(grade(df, 'ast', lambda d: d.ast_to_tov >= cut['ast_to_tov_hi'],
                    'H2 AST | high ast_to_tov',
                    'High AST:TOV = controlled distributor; cleaner AST realization vs turnover-prone handlers.'))
    # H3: high pnr-ballhandler fraction -> AST (PnR creators generate assists at volume)
    H.append(grade(df, 'ast', lambda d: d.pnr_bh_poss_fraction >= cut['pnr_frac_hi'],
                    'H3 AST | high PnR-ballhandler fraction',
                    'PnR ball-handlers manufacture assists; drop-coverage opponents feed it -> AST edge concentrates.'))
    # H4: high drive_ast (drive-and-kick playmakers)
    H.append(grade(df, 'ast', lambda d: d.drive_ast >= cut['drive_ast_hi'],
                    'H4 AST | high drive-and-kick (drive_ast)',
                    'Drive-and-kick creators (unpriced per playstyle-corr finding) -> AST over-realization.'))
    # H5: high potential_ast (creation volume floor)
    H.append(grade(df, 'ast', lambda d: d.potential_ast >= cut['potential_ast_hi'],
                    'H5 AST | high potential-assist volume',
                    'High potential-AST = high assist-opportunity floor; lines lag opportunity.'))
    # H6: high usage star (primary/secondary usage tier) -> AST
    H.append(grade(df, 'ast', lambda d: d.usage_tier.isin(['primary', 'secondary']),
                    'H6 AST | high-usage tier (star)',
                    'Star ball-dominant players control AST production; role players assist sporadically.'))

    # ---------- REB selection/sizing hypotheses ----------
    # H7: high oreb_dreb_ratio = crasher -> REB (volume crashers beat REB lines)
    H.append(grade(df, 'reb', lambda d: d.oreb_dreb_ratio >= cut['oreb_ratio_hi'],
                    'H7 REB | offensive-crasher (high OREB:DREB)',
                    'Crashers add boards opportunistically; lines anchor on positional baseline -> REB over.'))
    # H8: LOW reb consistency CV = steady rebounder -> REB (consistent => line-beatable)
    H.append(grade(df, 'reb', lambda d: d.reb_consistency_cv <= cut['reb_cv_hi'],
                    'H8 REB | low rebound-CV (steady boards)',
                    'Low CV = reliable rebounder; high-variance bigs are coin-flips. Steady = selection edge.'))
    # H9: high total_reb_rate (true bigs) -> REB
    H.append(grade(df, 'reb', lambda d: d.total_reb_rate_mean >= df.loc[df.stat=='reb','total_reb_rate_mean'].median(),
                    'H9 REB | high total-rebound-rate (true bigs)',
                    'Rate-dominant bigs own the glass; guard REB lines are minutes/garbage noise.'))

    # ---------- PTS / cross-stat (expected to reject, included for completeness) ----------
    # H10: high catch-shoot volume -> FG3M (spot-up shooters live on 3s; but FG3M is variance-y)
    H.append(grade(df, 'fg3m', lambda d: d.catch_shoot_3pa_per_g >= cut['cs3pa_hi'],
                    'H10 FG3M | high catch-shoot 3PA volume',
                    'Spot-up high-volume 3PT shooters have a 3-made floor; test if it beats the FG3M line.'))
    # H11: low Q4-fade players -> PTS (no fatigue collapse => PTS line holds)
    H.append(grade(df, 'pts', lambda d: d.q4_fade_abs <= cut['q4fade_hi'],
                    'H11 PTS | low Q4-fade (no late collapse)',
                    'Players who do not fade in Q4 sustain scoring; faders bust PTS overs in blowouts.'))
    # H12: paint-scorers (high pts_paint_share) -> PTS (rim pressure = stable, foul-drawing)
    H.append(grade(df, 'pts', lambda d: d.pts_paint_share >= df.loc[df.stat=='pts','pts_paint_share'].median(),
                    'H12 PTS | paint-dominant scorer',
                    'Paint scoring is high-percentage/foul-drawing = lower variance vs jump-shooters.'))

    # ---------- AST x context interactions (intelligence x situation) ----------
    # H13: creator AST x high opp pace (the EX-9/H1 pace concentration, but on creator-only)
    H.append(grade(df, 'ast',
                   lambda d: d.creator_role.isin(['primary_creator', 'secondary_creator']) & (d.opp_pace >= d.opp_pace.median()),
                    'H13 AST | creator AND high opp-pace',
                    'Stack the role identity with possession volume: creator on a fast opponent = max assist chances.'))
    # H14: creator AST x home (creators distribute more comfortably at home? selection probe)
    H.append(grade(df, 'ast',
                   lambda d: d.creator_role.isin(['primary_creator', 'secondary_creator']) & (d.is_home == 1),
                    'H14 AST | creator AND home',
                    'Probe whether creator AST edge concentrates at home (comfort/pace control).'))

    # flatten to a simple table view
    rows = []
    for h in H:
        rows.append({
            'hypothesis': h['hypothesis'],
            'stat': h['stat'],
            'in_roi': h.get('in_roi'), 'in_n': h.get('in_n'), 'in_win': h.get('in_win'),
            'in_ci': h.get('in_ci'), 'in_comp_roi': h.get('in_comp_roi'), 'in_comp_n': h.get('in_comp_n'),
            'cross_roi': h.get('cross_roi'), 'cross_n': h.get('cross_n'),
            'cross_comp_roi': h.get('cross_comp_roi'), 'cross_comp_n': h.get('cross_comp_n'),
            'in_over_roi': h.get('in_over_roi'), 'in_over_n': h.get('in_over_n'),
            'in_under_roi': h.get('in_under_roi'), 'in_under_n': h.get('in_under_n'),
            'note': h['note'],
        })
    res = pd.DataFrame(rows)
    res['verdict'] = res.apply(verdict, axis=1)

    pd.set_option('display.width', 240); pd.set_option('display.max_columns', 40)
    print('\n=== HYPOTHESIS RESULTS ===')
    show = res[['hypothesis', 'stat', 'in_roi', 'in_n', 'cross_roi', 'cross_n',
                'in_comp_roi', 'cross_comp_roi', 'verdict']]
    print(show.to_string(index=False))

    print('\n=== DECOMPOSITION (OVER/UNDER balance in-window; selection-vs-tilt) ===')
    for _, r in res.iterrows():
        print(f"  {r['hypothesis'][:46]:46s} OVER {str(r['in_over_roi']):>7s}(n{r['in_over_n']}) "
              f"UNDER {str(r['in_under_roi']):>7s}(n{r['in_under_n']})  ci{r['in_ci']}")

    res.to_json(os.path.join(BASE, 'intel_generated_edge_hunt.json'), orient='records', indent=2)
    print('\nsaved -> data/cache/intel_generated_edge_hunt.json')
    return res


if __name__ == '__main__':
    main()
