"""GATE A-0 (QUEUE_2026-09-14 Q01): per-tick in-game score vs the contemporaneous
market price, from disk. Calibration language only.
CLI: python -m scripts.platformkit.ingame.gate_a0_ingame_vs_market
     --sports mlb_clean,soccer_intl --out docs/evidence/ingame/
Rows: data/cache/ingame_grade_joined/<sport>/*.jsonl (model_prob, market_prob,
outcome, ts, state_summary, close_ts, edge_claimed, ...). Writes one JSON per
sport plus one shared markdown summary under --out.
"""
import argparse
import glob
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

EPS = 1e-6
DATA_ROOT = 'data/cache/ingame_grade_joined'

# Thresholds below are byte-identical to QUEUE_2026-09-14 Q01.
N_BOOT = 2000
SEED = 13
N_MIN_GAMES = 30
ECE_BINS = 10
PRICE_ORDER = ['<0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '>0.8']
TTC_ORDER = ['>60', '30-60', '10-30', '3-10', '<3']

def load(sport_folder):
    rows = []
    for fp in sorted(glob.glob(f'{DATA_ROOT}/{sport_folder}/*.jsonl')):
        with open(fp, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df['ts'] = pd.to_datetime(df['ts'], errors='coerce', utc=True)
    if 'close_ts' in df.columns:
        df['close_ts'] = pd.to_datetime(df['close_ts'], errors='coerce', utc=True)
    df = df.dropna(subset=['model_prob', 'market_prob', 'outcome', 'ts'])
    return df.sort_values(['game_id', 'ts']).reset_index(drop=True)

def brier(p, y):
    return (p - y) ** 2

def logloss(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))

def ece(p, y, nbins=ECE_BINS):
    bins = np.linspace(0, 1, nbins + 1)
    idx = np.clip(np.digitize(p, bins) - 1, 0, nbins - 1)
    n = len(p)
    tot = 0.0
    for b in range(nbins):
        mask = idx == b
        c = mask.sum()
        if c == 0:
            continue
        tot += (c / n) * abs(p[mask].mean() - y[mask].mean())
    return float(tot)

def cluster_bootstrap(df, col_a, col_b, n_boot=N_BOOT, seed=SEED):
    """Game-clustered bootstrap CI on the paired tick-weighted mean(a - b)."""
    rng = np.random.default_rng(seed)
    g = df.groupby('game_id').agg(sa=(col_a, 'sum'), sb=(col_b, 'sum'), n=(col_a, 'size'))
    sa, sb, nn = g['sa'].to_numpy(), g['sb'].to_numpy(), g['n'].to_numpy()
    ng = len(g)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, ng, ng)
        diffs[i] = (sa[pick].sum() - sb[pick].sum()) / nn[pick].sum()
    point = (sa.sum() - sb.sum()) / nn.sum()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(point), float(lo), float(hi)

def verdict(lo, hi, n_games, n_min=N_MIN_GAMES):
    if n_games < n_min or (lo <= 0 <= hi):
        return 'UNDERPOWERED'
    return 'BEHIND' if lo > 0 else 'AHEAD'

def phase_mlb(state_summary):
    m = re.search(r'inning=(\d+)', str(state_summary))
    if not m:
        return None
    inn = int(m.group(1))
    return '1-3' if inn <= 3 else ('4-6' if inn <= 6 else '7-9+')

def phase_soccer(state_summary):
    m = re.search(r'minute=(\d+)', str(state_summary))
    if not m:
        return None
    mi = int(m.group(1))
    if mi <= 30:
        return '0-30'
    if mi <= 60:
        return '31-60'
    return '61-90+'

PHASE_FN = {'mlb_clean': phase_mlb, 'soccer_intl': phase_soccer}

def price_band(p):
    if p < 0.2:
        return '<0.2'
    if p < 0.4:
        return '0.2-0.4'
    if p < 0.6:
        return '0.4-0.6'
    if p < 0.8:
        return '0.6-0.8'
    return '>0.8'

def ttc_bucket(mins):
    if pd.isna(mins):
        return None
    if mins > 60:
        return '>60'
    if mins > 30:
        return '30-60'
    if mins > 10:
        return '10-30'
    if mins > 3:
        return '3-10'
    return '<3'

def compute_cell(sub):
    n_ticks = len(sub)
    n_games = int(sub['game_id'].nunique())
    bm, bk = float(sub['se_model'].mean()), float(sub['se_market'].mean())
    lm, lk = float(sub['ll_model'].mean()), float(sub['ll_market'].mean())
    bp, blo, bhi = cluster_bootstrap(sub, 'se_model', 'se_market')
    lp, llo, lhi = cluster_bootstrap(sub, 'll_model', 'll_market')
    ece_m = ece(sub['model_prob'].to_numpy(), sub['outcome'].to_numpy())
    ece_k = ece(sub['market_prob'].to_numpy(), sub['outcome'].to_numpy())
    return {
        'n_ticks': n_ticks, 'n_games': n_games,
        'brier_model': bm, 'brier_market': bk,
        'brier_delta': {'point': bp, 'ci95': [blo, bhi]},
        'logloss_model': lm, 'logloss_market': lk,
        'logloss_delta': {'point': lp, 'ci95': [llo, lhi]},
        'ece_model': ece_m, 'ece_market': ece_k,
        'verdict': verdict(blo, bhi, n_games),
    }

def change_rate(df):
    ds = df.sort_values(['game_id', 'ts']).copy()
    ds['pm'] = ds.groupby('game_id')['model_prob'].shift(1)
    ds['pk'] = ds.groupby('game_id')['market_prob'].shift(1)
    ds['ps'] = ds.groupby('game_id')['state_summary'].shift(1)
    has_prev = ds['pm'].notna()
    n_prev = int(has_prev.sum())
    if n_prev == 0:
        return {'n_with_prev': 0, 'model_changed_frac': None,
                'market_changed_frac': None, 'state_changed_frac': None}
    return {
        'n_with_prev': n_prev,
        'model_changed_frac': float(((ds['model_prob'] != ds['pm']) & has_prev).sum() / n_prev),
        'market_changed_frac': float(((ds['market_prob'] != ds['pk']) & has_prev).sum() / n_prev),
        'state_changed_frac': float(((ds['state_summary'] != ds['ps']) & has_prev).sum() / n_prev),
    }

NOT_VERIFIED = [
    'how model_prob was produced is not audited by this module',
    'the model updates only at parsed state transitions',
    'single capture window',
    'one venue',
]

def analyze_sport(sport, df):
    df = df.copy()
    df['se_model'] = brier(df['model_prob'], df['outcome'])
    df['se_market'] = brier(df['market_prob'], df['outcome'])
    df['ll_model'] = logloss(df['model_prob'], df['outcome'])
    df['ll_market'] = logloss(df['market_prob'], df['outcome'])
    overall = compute_cell(df)
    overall['date_range'] = [str(df['ts'].min().date()), str(df['ts'].max().date())]
    phase_fn = PHASE_FN.get(sport)
    phases = {}
    df['_phase'] = df['state_summary'].apply(phase_fn) if phase_fn else None
    if phase_fn is not None and df['_phase'].notna().any():
        for lab, sub in df.groupby('_phase'):
            if lab is not None and len(sub):
                phases[lab] = compute_cell(sub)
    else:
        phases = 'NO_DATA'
    df['_band'] = df['market_prob'].apply(price_band)
    bands = {lab: compute_cell(df[df['_band'] == lab])
             for lab in PRICE_ORDER if (df['_band'] == lab).any()}
    if 'close_ts' in df.columns and df['close_ts'].notna().any():
        d = df.dropna(subset=['close_ts']).copy()
        d['_ttc'] = ((d['close_ts'] - d['ts']).dt.total_seconds() / 60.0).apply(ttc_bucket)
        ttc = {lab: compute_cell(d[d['_ttc'] == lab])
               for lab in TTC_ORDER if (d['_ttc'] == lab).any()}
    else:
        ttc = 'NO_DATA'
    return {
        'sport': sport,
        'overall': overall,
        'by_phase': phases,
        'by_market_prob_band': bands,
        'by_minutes_to_close': ttc,
        'tick_change_rate': change_rate(df),
        'not_verified': NOT_VERIFIED,
    }

def _cellrow(lab, c):
    if c is None:
        return f'| {lab} | - | - | - | - | NO_DATA |'
    return '| {} | {} | {} | {:.5f} | [{:.5f}, {:.5f}] | {} |'.format(
        lab, c['n_ticks'], c['n_games'], c['brier_delta']['point'],
        c['brier_delta']['ci95'][0], c['brier_delta']['ci95'][1], c['verdict'])

def write_markdown(results, path):
    lines = ['# Gate A-0: in-game score vs market (overall)', '',
             '| sport | n_ticks | n_games | date_range | brier_model | brier_market | '
             'brier_delta | brier_CI95 | logloss_delta | logloss_CI95 | verdict |',
             '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in results:
        o = r['overall']
        lines.append('| {} | {} | {} | {} | {:.5f} | {:.5f} | {:.5f} | [{:.5f}, {:.5f}] | '
                      '{:.5f} | [{:.5f}, {:.5f}] | {} |'.format(
            r['sport'], o['n_ticks'], o['n_games'], '..'.join(o['date_range']),
            o['brier_model'], o['brier_market'], o['brier_delta']['point'],
            o['brier_delta']['ci95'][0], o['brier_delta']['ci95'][1],
            o['logloss_delta']['point'], o['logloss_delta']['ci95'][0],
            o['logloss_delta']['ci95'][1], o['verdict']))
    for r in results:
        lines += ['', f"## {r['sport']}: by phase (Brier delta, model-market)",
                   '| phase | n_ticks | n_games | brier_delta | CI95 | verdict |',
                   '|---|---|---|---|---|---|']
        ph = r['by_phase']
        if ph == 'NO_DATA':
            lines.append('| NO_DATA | - | - | - | - | - |')
        else:
            for lab, c in ph.items():
                lines.append(_cellrow(lab, c))
        lines += ['', f"## {r['sport']}: by market_prob band",
                   '| band | n_ticks | n_games | brier_delta | CI95 | verdict |',
                   '|---|---|---|---|---|---|']
        for lab in PRICE_ORDER:
            if lab in r['by_market_prob_band']:
                lines.append(_cellrow(lab, r['by_market_prob_band'][lab]))
        lines += ['', f"## {r['sport']}: by minutes_to_close",
                   '| bucket | n_ticks | n_games | brier_delta | CI95 | verdict |',
                   '|---|---|---|---|---|---|']
        ttc = r['by_minutes_to_close']
        if ttc == 'NO_DATA':
            lines.append('| NO_DATA | - | - | - | - | - |')
        else:
            for lab in TTC_ORDER:
                if lab in ttc:
                    lines.append(_cellrow(lab, ttc[lab]))
        cr = r['tick_change_rate']
        lines += ['', f"## {r['sport']}: tick change-rate",
                   '| n_with_prev | model_changed_frac | market_changed_frac | state_changed_frac |',
                   '|---|---|---|---|',
                   '| {} | {} | {} | {} |'.format(
                       cr['n_with_prev'], cr['model_changed_frac'],
                       cr['market_changed_frac'], cr['state_changed_frac'])]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sports', default='mlb_clean,soccer_intl')
    ap.add_argument('--out', default='docs/evidence/ingame/')
    args = ap.parse_args()
    sports = [s.strip() for s in args.sports.split(',') if s.strip()]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for sport in sports:
        df = load(sport)
        if df.empty:
            print(f'{sport}: NO_DATA (0 rows found)')
            continue
        res = analyze_sport(sport, df)
        results.append(res)
        with open(out_dir / f'gate_a0_{sport}.json', 'w', encoding='utf-8') as f:
            json.dump(res, f, indent=2)
        o = res['overall']
        print(f"{sport}: n_ticks={o['n_ticks']} n_games={o['n_games']} "
              f"date_range={'..'.join(o['date_range'])}")
        print(f"  Brier model={o['brier_model']:.5f} market={o['brier_market']:.5f} "
              f"delta={o['brier_delta']['point']:.5f} "
              f"CI95=[{o['brier_delta']['ci95'][0]:.5f}, {o['brier_delta']['ci95'][1]:.5f}] "
              f"verdict={o['verdict']}")

    if results:
        write_markdown(results, out_dir / 'gate_a0_summary.md')
        print(f'wrote {out_dir / "gate_a0_summary.md"}')
if __name__ == '__main__':
    main()
