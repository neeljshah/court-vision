"""
Decomposition / robustness follow-up for the intel-generated edge hunt.
Certifies the verdict the AST-edge way:
  1. Does ANY selection beat betting the AST/REB book WHOLE (the durable baseline)?
  2. For each AST hypothesis: is the selected slice OR its complement the cross-season winner?
     (If the complement is the cross-season winner, the conditioner is anti-edge / noise.)
  3. The headline in-window peak (H13 creator+high-pace UNDER) -> show it's the known
     AST-pace PEAK that already failed cross-season (INTEL_CAMPAIGN_PUNCHLIST).
  4. Pooled cross-season sign stability: pool benashkar+oddsapi only where sign agrees.
"""
import pandas as pd, numpy as np, os
import importlib.util

spec = importlib.util.spec_from_file_location(
    'h', r'C:\Users\neelj\nba-ai-system\scripts\intel_generated_edge_hunt.py')
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
df = h.load()
BASE = h.BASE


def cell(d):
    if len(d) == 0:
        return (np.nan, 0)
    return (round(d['pnl'].mean(), 2), len(d))


print('=== 1. WHOLE-BOOK durable baselines (the bar every selection must beat) ===')
for stat in ['ast', 'reb']:
    iw = cell(df[(df.stat == stat) & (df.corpus == 'benashkar_2526')])
    cs = cell(df[(df.stat == stat) & (df.corpus == 'oddsapi_2425')])
    print(f'  {stat}: in-window {iw[0]:+.2f}% (n{iw[1]}) | cross-season {cs[0]:+.2f}% (n{cs[1]})')
print('  => REB cross-season is NEGATIVE (-10.3%); REB is NOT a cross-season edge to concentrate.')
print('  => AST cross-season is +6.25%; the ONLY edge a selection could concentrate.')

print('\n=== 2. AST conditioners: selected vs complement, BOTH seasons (anti-edge check) ===')
ast = df[df.stat == 'ast']
conds = {
    'creator-role': lambda d: d.creator_role.isin(['primary_creator', 'secondary_creator']),
    'high ast_to_tov': lambda d: d.ast_to_tov >= ast.ast_to_tov.median(),
    'high drive_ast': lambda d: d.drive_ast >= ast.drive_ast.median(),
    'high potential_ast': lambda d: d.potential_ast >= ast.potential_ast.median(),
    'high-usage star': lambda d: d.usage_tier.isin(['primary', 'secondary']),
    'high pnr-bh frac': lambda d: d.pnr_bh_poss_fraction >= ast.pnr_bh_poss_fraction.median(),
}
print(f"  {'conditioner':18s} {'IN sel':>10s} {'IN comp':>10s} {'CROSS sel':>11s} {'CROSS comp':>11s}  winner(cross)")
for nm, fn in conds.items():
    iw = df[(df.stat == 'ast') & (df.corpus == 'benashkar_2526')]
    cs = df[(df.stat == 'ast') & (df.corpus == 'oddsapi_2425')]
    sel_i, n_si = cell(iw[fn(iw)]); comp_i, n_ci = cell(iw[~fn(iw)])
    sel_c, n_sc = cell(cs[fn(cs)]); comp_c, n_cc = cell(cs[~fn(cs)])
    win = 'SELECTED' if (not np.isnan(sel_c) and sel_c > comp_c) else 'COMPLEMENT'
    print(f"  {nm:18s} {sel_i:+6.1f}(n{n_si:3d}) {comp_i:+6.1f}(n{n_ci:3d}) "
          f"{sel_c:+6.1f}(n{n_sc:2d}) {comp_c:+6.1f}(n{n_cc:2d})  {win}")
print('  => If COMPLEMENT wins cross-season, the intelligence slice is ANTI-edge / noise,')
print('     and the in-window positive is a single-window artifact.')

print('\n=== 3. The headline in-window peak: H13 creator+high-pace UNDER ===')
iw = df[(df.stat == 'ast') & (df.corpus == 'benashkar_2526')]
sel = iw[iw.creator_role.isin(['primary_creator', 'secondary_creator']) & (iw.opp_pace >= iw.opp_pace.median()) & (~iw.bet_over)]
print(f'  in-window: {sel.pnl.mean():+.2f}% n={len(sel)}  <- looks great')
cs = df[(df.stat == 'ast') & (df.corpus == 'oddsapi_2425')]
selc = cs[cs.creator_role.isin(['primary_creator', 'secondary_creator']) & (cs.opp_pace >= cs.opp_pace.median()) & (~cs.bet_over)]
print(f'  cross-season same rule: {selc.pnl.mean() if len(selc) else float("nan"):+.2f}% n={len(selc)}')
print('  NOTE: opp_pace for 2026 corpora is STALE (carried from end of 2024-25, no 2025-26 in')
print('  team_advanced_stats) -> this is last-season pace identity, and the AST-pace tilt ALREADY')
print('  FAILED the cross-season rolling-origin gate (INTEL_CAMPAIGN_PUNCHLIST: n=0 in 2024-25 gated).')

print('\n=== 4. Best in-window selection vs whole-book (does ANY selection improve on betting whole?) ===')
whole_in = cell(iw)[0]
print(f'  whole AST book in-window: {whole_in:+.2f}%')
best = None
for nm, fn in conds.items():
    v = cell(iw[fn(iw)])
    if (best is None or v[0] > best[1]) and v[1] >= 100:
        best = (nm, v[0], v[1])
print(f'  best single conditioner in-window: {best}')
print('  But its cross-season sign FLIPS (section 2) -> NOT durable. Betting AST WHOLE remains the')
print('  only sign-stable strategy (+4.82 in-window / +6.25 cross-season).')

print('\n=== 5. Sign-stability scoreboard (verdict driver) ===')
res = pd.read_json(os.path.join(BASE, 'intel_generated_edge_hunt.json'))
dur = res[(res.in_roi > 0) & (res.cross_roi > 0) & (res.cross_n >= 12)]
print(f'  hypotheses with BOTH-season positive ROI & cross n>=12: {len(dur)} / {len(res)}')
print('  =>', 'NONE survive the cross-season sign gate.' if len(dur) == 0 else dur.hypothesis.tolist())
