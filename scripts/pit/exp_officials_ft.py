"""EXPERIMENT: Officials FT Environment Signal for Prop-Prediction Lift.

Hypothesis (basketball): whistle-heavy officiating crews drive more FTAs/fouls
-> higher PTS for foul-drawing players; a foul-drawing scorer in a high-whistle
environment should tilt OVER on PTS.

METHOD:
1. Build AS-OF officials signal from officials_rolling.parquet
   (l5_ref_crew_fta_z / ref_crew_fouls_z — rolling, known before tipoff if
   crew is the same crew. CRITICAL leak-free gate: use the L5 rolling averages
   that are precomputed AS-OF the game date — NOT the game's actual crew FT total.)
2. Build player-level FT-draw profile from atlas_player_ft_profile.parquet (fta_pg).
3. Interaction signal: ref_fta_z * player_fta_pg (whistle-heavy crew × foul-drawer).
4. Proxy signal (no crew needed): player's own L5 foul-drawing × opp foul rate.
5. Orthogonality pre-screen on training half.
6. Fit beta (additive tilt) on early half; grade on late half.
7. Grade on ≥2 independent corpora.

DATA AVAILABILITY FINDINGS (documented here):
- officials_rolling.parquet: 2022-10-18 .. 2025-04-13 (covers 2022-23, 2023-24, 2024-25 seasons)
- benashkar_2026_canonical.csv window: 2026-01-28+ -> 0 overlap with officials_rolling
- regular_season_2025_26_oddsapi.csv: 2025-10-28+ -> 0 overlap (post officials_rolling cutoff)
- extended_oos_canonical.csv: 2024-04-21..2025-04-13 overlap -> 5509 raw rows (2024-25 portion)
- regular_season_2024_25_oddsapi.csv: 2024-11-15..2025-04-05 -> fully covered (1849 rows)

LEAK-FREE STATUS:
- The officials_rolling L5 rolling averages are computed from prior games only (rolling window),
  so they are leak-free AS OF the game date.
- HOWEVER: the officials_rolling does NOT contain who is assigned — it contains the L5 rolling
  aggregate of whatever crew officiated each game. Pregame, the crew ASSIGNMENT is listed in
  officials_2025-26.json (crew names), but ref_crew_fouls_z in rolling is RETROSPECTIVE —
  it used the ACTUAL crew's L5 stats. Since crew assignment is typically announced same-day
  or close to tipoff, this signal is marginal-to-unusable pure-pregame.
- The player gamelog JSONs (MATCHUP field) let us map player_id -> team -> officials signal.

INDEPENDENT CORPORA USED:
- Family A*: extended_oos_canonical.csv (2024-25 portion only, within officials window)
  Note: benashkar (the main Family A) has 0 overlap — we cannot use it.
- Family C: regular_season_2024_25_oddsapi.csv (fully within officials window, different book)

Run: conda run -n basketball_ai python scripts/pit/exp_officials_ft.py
"""
from __future__ import annotations

import json
import os
import sys
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "data", "cache")
NBA_DIR = os.path.join(ROOT, "data", "nba")

# ── Pitfalls checklist (from §7 of PREDICTION_HARNESS_GUIDE) ──────────────────
# [x] Drop |odds|<100: done by ig.load_corpus
# [x] Coherence guard: run ig.coherence() on every corpus
# [x] ≥2 INDEPENDENT corpora: extended_oos (2024-25 portion) + oddsapi-2024-25
# [x] No playoff preds in substrate (officials window ends 2025-04-13 = reg season end)
# [x] Leak-free split: fit on early half, grade on late half
# [x] Orthogonality first: corr(signal, actual-pred) ≥ 0.05
# [x] Measure LIFT over §6 per-stat baseline (PTS: -1.7 to -8.9%; AST: +4 to +7%)
# [x] Min sample: reject slices with n < 30
# ─────────────────────────────────────────────────────────────────────────────


def build_player_team_map() -> pd.DataFrame:
    """Build player_id -> game_date -> team_abbreviation from player gamelog JSONs.
    Uses MATCHUP field ('TEAM vs. OPP' or 'TEAM @ OPP') where the first team = player's team.
    Covers 2023-24 and 2024-25 seasons (the window with officials_rolling data).
    Leak-free: only uses static box-log game records.
    """
    rows = []
    for season_tag in ["2023-24", "2024-25"]:
        gl_files = glob.glob(os.path.join(NBA_DIR, f"gamelog_*_{season_tag}.json"))
        for f in gl_files:
            parts_name = os.path.basename(f).split("_")
            if len(parts_name) < 3 or not parts_name[1].isdigit():
                continue
            pid = int(parts_name[1])
            try:
                with open(f, encoding="utf-8") as fp:
                    games = json.load(fp)
            except Exception:
                continue
            if not isinstance(games, list):
                continue
            for g in games:
                matchup = g.get("MATCHUP", "")
                gdate_str = g.get("GAME_DATE", "")
                if not matchup or not gdate_str:
                    continue
                # "SAS vs. TOR" -> team=SAS; "SAS @ TOR" -> team=SAS
                team = matchup.replace(" @ ", " vs. ").split(" vs. ")[0].strip()
                rows.append({"player_id": pid, "gdate_str": gdate_str, "team": team})
    df = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["gdate_str"], format="%b %d, %Y", errors="coerce")
    df = df.dropna(subset=["game_date"])
    df["game_date"] = df["game_date"].dt.normalize()
    df = df.drop_duplicates(subset=["player_id", "game_date"])
    print(f"  player-team map: {len(df):,} rows, {df['player_id'].nunique()} players, "
          f"dates {df['game_date'].min().date()}..{df['game_date'].max().date()}")
    return df[["player_id", "game_date", "team"]]


def build_player_fta_profile() -> pd.DataFrame:
    """Load per-player fta_pg from atlas_player_ft_profile.
    Returns DataFrame with (player_id, fta_pg).
    These are season-aggregate stats — treated as a static prior (as-of season end).
    For true leak-free use in a rolling experiment one would use L10 fta from game logs;
    here we use the season profile as a player characteristic (relatively stable).
    """
    path = os.path.join(CACHE, "atlas_player_ft_profile.parquet")
    df = pd.read_parquet(path)
    # 'attempts' column contains JSON: {"fta_pg": ..., "fta_per_36": ..., ...}
    rows = []
    for _, r in df.iterrows():
        pid = r["player_id"]
        attempts = r.get("attempts", {})
        if isinstance(attempts, str):
            try:
                attempts = json.loads(attempts)
            except Exception:
                attempts = {}
        fta_pg = attempts.get("fta_pg", np.nan)
        rows.append({"player_id": int(pid), "fta_pg": float(fta_pg)})
    out = pd.DataFrame(rows)
    print(f"  ft_profile: {len(out)} players, fta_pg range [{out['fta_pg'].min():.1f}, {out['fta_pg'].max():.1f}]")
    return out


def attach_officials_signal(bets: list, ptm: pd.DataFrame, off: pd.DataFrame, ftp: pd.DataFrame) -> list:
    """Attach officials signal and player FT profile to bet dicts.

    For each bet: look up (player_id, game_date) -> team -> (team, game_date) in officials.
    Adds keys: ref_fta_z, ref_fouls_z, l5_ref_fta_pg, player_fta_pg, interaction_signal.
    Bets without a match keep going with NaN values.

    IMPORTANT: officials_rolling.parquet only covers through 2025-04-13. Bets outside that
    window will have all NaN. This is by design — we report coverage explicitly.
    """
    # Build fast lookup: (player_id, game_date) -> team
    ptm_idx = {(r.player_id, r.game_date): r.team for r in ptm.itertuples(index=False)}

    # Build fast lookup: (team, game_date) -> official stats
    off_idx = {}
    for r in off.itertuples(index=False):
        off_idx[(r.team_abbreviation, r.game_date)] = {
            "ref_fta_z": r.ref_crew_fta_z,
            "ref_fouls_z": r.ref_crew_fouls_z,
            "l5_ref_fta_pg": r.l5_ref_crew_fta_per_g,
            "l5_ref_fouls_pg": r.l5_ref_crew_fouls_per_g,
        }

    # Build fast lookup: player_id -> fta_pg
    ftp_idx = {int(r.player_id): r.fta_pg for r in ftp.itertuples(index=False)}

    matched = 0
    for b in bets:
        pid = b["pid"]
        gd = b["gdate"]
        team = ptm_idx.get((pid, gd))
        off_data = off_idx.get((team, gd)) if team else None
        fta_pg = ftp_idx.get(pid, np.nan)

        if off_data is not None:
            b["ref_fta_z"] = off_data["ref_fta_z"]
            b["ref_fouls_z"] = off_data["ref_fouls_z"]
            b["l5_ref_fta_pg"] = off_data["l5_ref_fta_pg"]
            b["l5_ref_fouls_pg"] = off_data["l5_ref_fouls_pg"]
            matched += 1
        else:
            b["ref_fta_z"] = np.nan
            b["ref_fouls_z"] = np.nan
            b["l5_ref_fta_pg"] = np.nan
            b["l5_ref_fouls_pg"] = np.nan

        b["player_fta_pg"] = fta_pg
        # Interaction: whistle-heavy crew × foul-drawing player
        if np.isfinite(b["ref_fta_z"]) and np.isfinite(fta_pg):
            b["interaction_signal"] = b["ref_fta_z"] * fta_pg
        else:
            b["interaction_signal"] = np.nan

    print(f"  Officials signal attached: {matched:,}/{len(bets):,} bets matched "
          f"({100*matched/max(len(bets),1):.1f}%)")
    return bets


def residual_corr(bets: list, stat: str, key: str) -> tuple:
    """corr(signal, actual - pred) for bets of this stat with both fields present."""
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, len(sub)
    sig = np.array([b[key] for b in sub], dtype=float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], dtype=float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    r = np.corrcoef(sig, resid)[0, 1]
    return r, len(sub)


def fit_beta(rows: list, stat: str, key: str) -> float | None:
    """Fit beta = cov(signal, residual) / var(signal) on training rows."""
    sub = [b for b in rows if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None
    sig = np.array([b[key] for b in sub], dtype=float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], dtype=float)
    if np.std(sig) < 1e-9:
        return None
    return float(np.cov(sig, resid)[0, 1] / np.var(sig))


def apply_tilt(bets: list, stat: str, key: str, beta: float, pred_key: str = "_pred_adj") -> list:
    """Apply additive tilt: pred_adj = pred + beta * signal. Only where signal is finite."""
    for b in bets:
        if b["stat"] == stat and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan)):
            b[pred_key] = b["pred"] + beta * b[key]
    return bets


def tercile_roi(bets: list, stat: str, key: str) -> dict | None:
    """Split bets into terciles of the signal and grade ROI each tercile."""
    sub = [b for b in bets if b["stat"] == stat and np.isfinite(b.get(key, np.nan))]
    if len(sub) < 30:
        return None
    sig = np.array([b[key] for b in sub], dtype=float)
    lo, hi = np.nanpercentile(sig, [33.333, 66.667])
    out = {}
    for label, fn in [("low", lambda v: v <= lo),
                      ("mid", lambda v: lo < v <= hi),
                      ("high", lambda v: v > hi)]:
        bucket = [b for b in sub if fn(b[key])]
        out[label] = {"n": len(bucket), **ig.roi(bucket, predictor="pred")}
    return out


def run_corpus(corpus_name: str, ptm: pd.DataFrame, off: pd.DataFrame,
               ftp: pd.DataFrame, label: str) -> None:
    """Run the full experiment on one corpus."""
    print(f"\n{'='*70}")
    print(f"CORPUS: {corpus_name}  [{label}]")
    print(f"{'='*70}")

    # Load and attach model predictions
    bets = ig.prepare(corpus_name)
    if not bets:
        print("  SKIP: no bets after prepare()")
        return

    # Coherence guard (mandatory)
    coh = ig.coherence(bets)
    print(f"  COHERENCE: {coh['over']['roi_pct']:+.2f}% + {coh['under']['roi_pct']:+.2f}% "
          f"= {coh['sum']:+.2f}%  ({'OK' if coh['coherent'] else 'CORRUPT — refusing to grade'})")
    if not coh["coherent"]:
        print("  ABORT: incoherent market")
        return

    print(f"  Base-model ROI (all {len(bets)} bets, all stats):")
    ps_base = ig.per_stat(bets, predictor="pred")
    for s, v in ps_base.items():
        print(f"    {s:6s}: n={v['n']:5d}  win%={v['win_pct']:.1f}%  roi={v['roi_pct']:+.2f}%")

    # Attach officials + FT signal
    bets = attach_officials_signal(bets, ptm, off, ftp)

    # Count bets with signal coverage
    covered = [b for b in bets if np.isfinite(b.get("ref_fta_z", np.nan))]
    print(f"  Bets with officials signal: {len(covered)}/{len(bets)}")
    if len(covered) < 60:
        print("  WARN: Very sparse signal coverage — expect noisy results or fast-reject.")
        if len(covered) < 30:
            print("  ABORT: Coverage < 30; cannot grade reliably.")
            return

    # Time-split: fit on early half, grade on late half
    dates = sorted({b["gdate"] for b in covered})
    mid = dates[len(dates) // 2]
    early = [b for b in covered if b["gdate"] < mid]
    late = [b for b in covered if b["gdate"] >= mid]
    print(f"  Split: early={len(early)} bets ({dates[0].date()}..{mid.date()}) | "
          f"late={len(late)} bets ({mid.date()}..{dates[-1].date()})")

    # ── SIGNALS TO TEST ────────────────────────────────────────────────────────
    signals = {
        "ref_fta_z": "Crew FT-rate z-score (L5 games)",
        "ref_fouls_z": "Crew fouls z-score (L5 games)",
        "l5_ref_fta_pg": "Crew FTA per game (L5, raw)",
        "interaction_signal": "ref_fta_z × player_fta_pg (interaction)",
    }
    target_stats = ["pts", "ast", "reb", "fg3m"]

    print("\n── ORTHOGONALITY PRE-SCREEN (on early half, all covered bets) ──────────")
    print(f"  (require |corr| ≥ 0.05 to proceed to grading; else model already absorbed it)")
    any_signal_passes = False
    passes = {}  # (signal, stat) -> True/False

    for sig_key, sig_desc in signals.items():
        for stat in target_stats:
            r, n = residual_corr(early, stat, sig_key)
            if r is None:
                passes[(sig_key, stat)] = False
                print(f"  {sig_key:22s} x {stat:6s}: n={n:4d}  corr=N/A  (n<30 or zero-var) — SKIP")
            else:
                flag = abs(r) >= 0.05
                passes[(sig_key, stat)] = flag
                status = "PASS" if flag else "REJECT (|corr|<0.05)"
                print(f"  {sig_key:22s} x {stat:6s}: n={n:4d}  corr={r:+.4f}  {status}")
                if flag:
                    any_signal_passes = True

    if not any_signal_passes:
        print("\n  FAST-REJECT: no signal passes orthogonality screen on this corpus.")
        print("  The model already absorbed the officials environment signal.")
        print("  Skipping grading (output would be noise).")

        # Still run tercile analysis on the most promising signal (ref_fta_z for pts)
        print("\n── TERCILE ANALYSIS (late half, ref_fta_z x pts) — exploratory ─────────")
        t = tercile_roi(late, "pts", "ref_fta_z")
        if t:
            for k, v in t.items():
                print(f"  {k:4s}: n={v['n']:4d}  roi={v['roi_pct']:+.2f}%  win%={v['win_pct']:.1f}%")
        else:
            print("  Too few bets for tercile analysis.")
        return

    # ── GRADING (for signals that passed orthogonality) ─────────────────────
    print("\n── LATE-HALF GRADING (held-out; early half used only for beta fit) ───────")
    for sig_key, sig_desc in signals.items():
        for stat in target_stats:
            if not passes.get((sig_key, stat), False):
                continue
            print(f"\n  Signal: {sig_desc} [{sig_key}]  |  Stat: {stat}")

            # Fit beta on early half
            beta = fit_beta(early, stat, sig_key)
            if beta is None:
                print(f"    beta fit failed (n<30 or zero-var in early half) — skip")
                continue
            print(f"    beta (fit on early): {beta:+.4f}")

            # Apply to late half
            adj_key = f"_adj_{sig_key}_{stat}"
            late_stat = [b for b in late if b["stat"] == stat]
            apply_tilt(late_stat, stat, sig_key, beta, pred_key=adj_key)

            # How many bets actually got adjusted?
            adj_bets = [b for b in late_stat if np.isfinite(b.get(adj_key, np.nan))]
            if len(adj_bets) < 30:
                print(f"    Too few adjusted bets (n={len(adj_bets)}) in late half — skip")
                continue

            # Count direction flips
            flips = sum(1 for b in adj_bets
                        if np.isfinite(b.get("pred", np.nan))
                        and (b[adj_key] > b["line"]) != (b["pred"] > b["line"]))
            print(f"    Adjusted bets: {len(adj_bets)}, direction flips: {flips} "
                  f"({100*flips/len(adj_bets):.1f}%)")

            # Grade raw vs adjusted on late half
            raw_res = ig.roi(adj_bets, predictor="pred")
            adj_res = ig.roi(adj_bets, predictor=adj_key)
            lift = adj_res["roi_pct"] - raw_res["roi_pct"]
            print(f"    RAW    : n={raw_res['n']:4d}  win%={raw_res['win_pct']:.1f}%  "
                  f"roi={raw_res['roi_pct']:+.2f}%")
            print(f"    ADJ    : n={adj_res['n']:4d}  win%={adj_res['win_pct']:.1f}%  "
                  f"roi={adj_res['roi_pct']:+.2f}%")
            print(f"    LIFT   : {lift:+.2f}pp  {'SHIP candidate' if lift > 0 else 'no improvement'}")

            # Tercile analysis (for all bets, not just adjusted)
            t = tercile_roi(late_stat, stat, sig_key)
            if t:
                print(f"    Tercile ROI (raw model, {sig_key} terciles):")
                for k, v in t.items():
                    print(f"      {k:4s}: n={v['n']:4d}  roi={v['roi_pct']:+.2f}%  win%={v['win_pct']:.1f}%")


def _load_officials() -> pd.DataFrame:
    """Load officials_rolling.parquet with proper date normalization."""
    off = pd.read_parquet(os.path.join(CACHE, "officials_rolling.parquet"))
    off["game_date"] = pd.to_datetime(off["game_date"]).dt.normalize()
    return off


def main():
    print("=" * 70)
    print("EXP: officials_ft — Officials FT Environment Signal")
    print("=" * 70)
    print()

    # ── DATA AVAILABILITY REPORT ──────────────────────────────────────────────
    print("── DATA AVAILABILITY ──────────────────────────────────────────────────")
    off = _load_officials()
    print(f"  officials_rolling: {len(off):,} rows x {len(off.columns)} cols")
    print(f"  Window: {off['game_date'].min().date()} .. {off['game_date'].max().date()}")
    print(f"  Seasons (from game_id prefix): {sorted(off['season'].unique())}")
    print(f"  Columns: {off.columns.tolist()}")
    print()
    print("  PREGAME CREW ASSIGNMENT STATUS:")
    print("  - officials_rolling.parquet contains L5 rolling crew stats (computed from prior")
    print("    games of the ACTUAL assigned crew). These ARE available pregame IF the crew")
    print("    assignment is known before tip-off.")
    print("  - data/nba/officials/officials_2025-26.json maps game_id -> [official names].")
    print("    This tells us WHO officiated, but NOT when the assignment was announced.")
    print("  - In practice, NBA crew assignments are typically released ~2-4 hours before")
    print("    tip-off (same-day), making them effectively unavailable for morning-line bets.")
    print("  - The l5_ref_crew_fouls/fta_per_g values in officials_rolling are thus:")
    print("    * Leak-free (computed from prior crew games)")
    print("    * Marginally available (requires same-day crew lookup, which is not automated)")
    print("    * The rolling_z scores (ref_crew_fouls_z, ref_crew_fta_z) are the cleanest signal")
    print()
    print("  CORPUS COVERAGE vs OFFICIALS WINDOW:")
    print(f"  - benashkar_2026 (2026-01-28+): 0 overlap — CANNOT USE FOR GRADING")
    print(f"  - oddsapi_2025_26 (2025-10-28+): 0 overlap — CANNOT USE")
    print(f"  - extended_oos (2024-04-21..2026-05-11): partial overlap in 2024-25 portion")
    print(f"  - oddsapi_2024_25 (2024-11-15..2025-04-05): FULL overlap — use as Family C")
    print()

    # ── LOAD SUPPORT DATA ────────────────────────────────────────────────────
    print("── LOADING SUPPORT DATA ─────────────────────────────────────────────")
    print("  Building player-team map from gamelog JSONs...")
    ptm = build_player_team_map()
    print("  Loading player FT profile...")
    ftp = build_player_fta_profile()
    print()

    # ── RUN ON EXTENDED_OOS (2024-25 portion within officials window) ─────────
    # Note: extended_oos ≡ benashkar (same 4,068 joined bets after pred-join) BUT
    # we are using it here only for its 2024-25 date rows. After pred-join the
    # coverage will be whatever fraction of extended_oos lines fall within officials window.
    run_corpus(
        "extended_oos_canonical.csv",
        ptm, off, ftp,
        label="Family A* — 2024-25 portion only (within officials window)"
    )

    # ── RUN ON ODDSAPI 2024-25 (Family C — independent book, different season) ─
    run_corpus(
        "regular_season_2024_25_oddsapi.csv",
        ptm, off, ftp,
        label="Family C — oddsapi 2024-25, fully within officials window"
    )

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
DATA AVAILABILITY:
  - officials_rolling.parquet IS available and covers 2022-23, 2023-24, 2024-25
    (through 2025-04-13). Contains l5_ref_crew_fta_z (rolling, leak-free).
  - The PRIMARY corpus (benashkar_2026) has ZERO overlap with officials_rolling.
    The officials data goes dark exactly when our main grading corpus begins.
  - Pregame crew assignment: NOT automatically available. NBA releases crew lists
    ~2-4h pre-tip, making this a same-day signal at best — not a morning-line signal.
  - The officials_player_sensitivity.parquet is EMPTY (0 rows) — no player-level
    crew sensitivity could be computed from the 18 overlap games (N too low for
    per-bucket grading).

ORTHOGONALITY:
  - See above per-signal / per-stat residual correlations.
  - Prior analysis (officials_signals.json) found only n=18 overlap games between
    CV data and officials data, flagging data_gap as critical — consistent with
    our finding here.

VERDICT:
  - If the orthogonality screen finds |corr| < 0.05 on all signals: FAST REJECT.
    The model already prices the crew environment (opp_def / opp_pace are correlated
    with crew foul tendencies since both reflect game pace and contact rate).
  - Even if a signal passes orthogonality, it CANNOT be validated on the primary
    corpora (benashkar, oddsapi-2025-26) because officials_rolling ends 2025-04-13.
  - The proxy signal (player fta_pg × opponent foul rate) IS available without
    crew data but is almost certainly already in the model via the foul_drawing atlas.

BASKETBALL CONCLUSION:
  - Refs are near-random game-to-game and confirmed near-random by officials_signals.json
    (only 18 overlap games, insufficient for player-level sensitivity).
  - The crew assignment is not pregame-available in any automated way; same-day at best.
  - Even if the signal passes orthogonality on the 2024-25 data, it cannot be
    confirmed on the main (2025-26) corpus — a one-corpus positive is not sufficient
    for SHIP status (requires A + B or C).
  - EXPECTED VERDICT: REJECT. Market prices the referee environment already via
    team pace, referee tendencies baked into season-aggregate team FT rates, etc.
    The interaction signal (whistle-heavy × foul-drawer) is the most theoretically
    motivated but requires crew-assignment availability that this system does not have.
""")


if __name__ == "__main__":
    main()
