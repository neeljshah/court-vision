"""domains.tennis.mcp_2026 -- Match Charting Project 2026 point-level parser.

Source (already on disk, no network): data/domains/tennis/_raw/sackmann_pbp_repos/
tennis_MatchChartingProject/charting-{m,w}-points-2020s.csv (+ matches CSVs).
LICENSE: CC BY-NC-SA 4.0 -- private research only; outputs under data/ (gitignored).

POPULATION WARNING (binding): the MCP corpus is CROWDSOURCED CHARTED MATCHES --
overwhelmingly elite / televised matches, NOT a representative tour sample. Every
output row carries population="mcp_charted_nonrepresentative". NEVER mix these
serve/return aggregates unlabeled with Sackmann-derived attrs (match_stats.parquet
is a full-tour census; this is not).

OUTPUTS (data/domains/tennis/mcp_2026/):
  points.parquet             one row per served point, point-engine sequence format
                             (match_id/set_no/game_no/point_number/point_server/
                             point_winner/p1_score/p2_score) -- NOTE: p1/p2_score are
                             the PRE-point game score (MCP `Pts` is pre-point; the
                             slam corpus in point_engine/corpus.py is post-point and
                             shifts -- consumers of THIS file must not re-shift).
  match_serve_return.parquet one row per (match, player): serve/return aggregates
                             parsed from the shot notation (aces/dfs/1st-in/1st-won...).
  matches.parquet            one row per match: metadata + winner derived from the
                             real point sequence (winner_derivation column says how).

Score orientation (verified empirically, Rome 2026 final): MCP `Pts` is SERVER-first
pre-point; Set1/Set2/Gm1/Gm2 are Player1/Player2-oriented ("Player 1" served first).

Tests: python -m pytest domains/tennis/test_mcp_2026.py -q
ASCII only. <=300 LOC. No src/kernel imports. CALIBRATION only -- no $ edge.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
RAW_DIR = (_REPO / "data" / "domains" / "tennis" / "_raw" / "sackmann_pbp_repos"
           / "tennis_MatchChartingProject")
OUT_DIR = _REPO / "data" / "domains" / "tennis" / "mcp_2026"
POPULATION = "mcp_charted_nonrepresentative"

# MCP shot-notation alphabet (Instructions tab of the MatchChart spreadsheet).
RALLY_SHOTS = frozenset("fbrsvzopuylmhijktq")   # any = ball was in play past serve
FAULT_CODES = frozenset("nwdxge!")               # serve-error direction codes
REGULAR = frozenset(("0", "15", "30", "40", "AD"))

POINTS_COLS = ["match_id", "date", "tour", "year", "tourney", "set_no", "game_no",
               "point_number", "point_server", "point_winner", "p1_score", "p2_score",
               "is_tiebreak", "score_state", "serve_1st", "serve_2nd", "first_in",
               "is_ace", "is_double_fault", "rally", "population"]
SR_COLS = ["match_id", "date", "tour", "player_no", "player_name", "serve_pts",
           "serve_pts_won", "first_in", "first_won", "second_pts", "second_won",
           "aces", "dfs", "unreturned", "bp_faced", "bp_saved", "return_pts",
           "return_pts_won", "population"]
MATCHES_COLS = ["match_id", "date", "tour", "tourney", "round", "surface", "best_of",
                "player1", "player2", "winner", "winner_derivation", "n_points",
                "population"]


def classify_serve(token: str) -> str:
    """One serve-column string -> ace | svc_winner | fault | in_play | unknown."""
    if not isinstance(token, str) or not token.strip():
        return "unknown"
    chars = set(token)
    if chars & RALLY_SHOTS:
        return "in_play"           # returner put a racket on it (incl. return errors)
    if "*" in chars:
        return "ace"
    if "#" in chars:
        return "svc_winner"        # unreturnable serve, no return attempt charted
    if chars & FAULT_CODES:
        return "fault"
    return "unknown"               # penalty codes (S/R/P/Q) etc.


def rally_count(token: str) -> "int | None":
    """MCP convention: shots incl. serve, EXCL. the final errored shot.
    Double fault -> 0 handled by caller (token here is the effective serve)."""
    if not isinstance(token, str) or not token.strip():
        return None
    cls = classify_serve(token)
    if cls == "unknown":
        return None
    if cls == "fault":
        return 0
    n = 1 + sum(1 for ch in token if ch in RALLY_SHOTS)
    if token.rstrip().endswith(("#", "@")):
        n -= 1                     # last shot was an error -> excluded
    return max(n, 0)


def _read_matches_meta(raw_dir: Path, gender: str) -> pd.DataFrame:
    m = pd.read_csv(raw_dir / f"charting-{gender}-matches.csv", dtype=str,
                    low_memory=False)
    m = m.drop_duplicates(subset="match_id", keep="first")
    return pd.DataFrame({
        "match_id": m["match_id"],
        "tourney": m["Tournament"],
        "round": m["Round"],
        "surface": m["Surface"],
        "best_of": pd.to_numeric(m["Best of"], errors="coerce"),
        "player1": m["Player 1"],
        "player2": m["Player 2"],
    }).set_index("match_id")


def parse_points(raw_dir: Path = RAW_DIR, year_prefix: str = "2026") -> pd.DataFrame:
    """All charted points whose match_id date starts with year_prefix, both tours,
    in the point-engine sequence format (see module docstring)."""
    frames = []
    for gender in ("m", "w"):
        pts = pd.read_csv(raw_dir / f"charting-{gender}-points-2020s.csv",
                          dtype=str, low_memory=False)
        pts = pts[pts["match_id"].str.startswith(year_prefix)].copy()
        if pts.empty:
            continue
        meta = _read_matches_meta(raw_dir, gender)

        svr = pd.to_numeric(pts["Svr"], errors="coerce")
        winner = pd.to_numeric(pts["PtWinner"], errors="coerce")
        split = pts["Pts"].fillna("").str.split("-", n=1, expand=True)
        s_score, r_score = split[0].fillna(""), split[1].fillna("")
        is_tb = ~(s_score.isin(REGULAR) & r_score.isin(REGULAR))
        p1 = s_score.where(svr == 1, r_score)          # server-first -> P1/P2
        p2 = r_score.where(svr == 1, s_score)
        game_no = pts["Gm#"].str.extract(r"^(\d+)", expand=False)

        first = pts["1st"].fillna("")
        second = pts["2nd"].fillna("")
        cls1 = first.map(classify_serve)
        cls2 = second.map(classify_serve)
        effective = second.where(cls1 == "fault", first)
        first_in = ~cls1.isin(("fault", "unknown"))
        is_df = (cls1 == "fault") & (cls2 == "fault")
        is_ace = (cls1 == "ace") | ((cls1 == "fault") & (cls2 == "ace"))
        rally = effective.map(rally_count)
        rally = rally.mask(is_df, 0)

        frames.append(pd.DataFrame({
            "match_id": pts["match_id"],
            "date": pd.to_datetime(pts["match_id"].str[:8], format="%Y%m%d",
                                   errors="coerce").dt.date,
            "tour": gender,
            "year": int(year_prefix[:4]),
            "tourney": pts["match_id"].map(meta["tourney"]),
            "set_no": (pd.to_numeric(pts["Set1"], errors="coerce").fillna(0)
                       + pd.to_numeric(pts["Set2"], errors="coerce").fillna(0)
                       + 1).astype("int64"),
            "game_no": pd.to_numeric(game_no, errors="coerce").astype("Int64"),
            "point_number": pd.to_numeric(pts["Pt"], errors="coerce").astype("Int64"),
            "point_server": svr.astype("Int64"),
            "point_winner": winner.astype("Int64"),
            "p1_score": p1,
            "p2_score": p2,
            "is_tiebreak": is_tb,
            "score_state": pts["Pts"].fillna(""),
            "serve_1st": first,
            "serve_2nd": second,
            "first_in": first_in,
            "is_ace": is_ace,
            "is_double_fault": is_df,
            "rally": pd.array(rally, dtype="Int64"),
            "population": POPULATION,
        }))
    if not frames:
        raise FileNotFoundError(f"no {year_prefix} charting rows under {raw_dir}")
    out = pd.concat(frames, ignore_index=True)
    return out[POINTS_COLS].sort_values(["match_id", "point_number"],
                                        ignore_index=True)


def _bp_mask(points: pd.DataFrame) -> pd.Series:
    """Server faces break point: returner one point from the game (regular games
    only; tiebreak set points are NOT counted -- matches Sackmann bpFaced scope)."""
    svr_is_p1 = points["point_server"] == 1
    s = points["p1_score"].where(svr_is_p1, points["p2_score"])
    r = points["p2_score"].where(svr_is_p1, points["p1_score"])
    reg = ~points["is_tiebreak"]
    return reg & ((r == "AD") | ((r == "40") & s.isin(("0", "15", "30"))))


def build_serve_return(points: pd.DataFrame, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """One row per (match, player): serve/return aggregates from the notation."""
    meta = pd.concat([_read_matches_meta(raw_dir, g) for g in ("m", "w")])
    meta = meta[~meta.index.duplicated(keep="first")]
    bp = _bp_mask(points)
    rows = []
    for mid, g in points.groupby("match_id", sort=True):
        gbp = bp.loc[g.index]
        names = meta["player1"].get(mid), meta["player2"].get(mid)
        for p in (1, 2):
            served = g["point_server"] == p
            won = g["point_winner"] == p
            second = served & (g["serve_2nd"].str.strip() != "")
            faced = served & gbp
            rows.append({
                "match_id": mid,
                "date": g["date"].iloc[0],
                "tour": g["tour"].iloc[0],
                "player_no": p,
                "player_name": names[p - 1],
                "serve_pts": int(served.sum()),
                "serve_pts_won": int((served & won).sum()),
                "first_in": int((served & g["first_in"]).sum()),
                "first_won": int((served & g["first_in"] & won).sum()),
                "second_pts": int(second.sum()),
                "second_won": int((second & won).sum()),
                "aces": int((served & g["is_ace"]).sum()),
                "dfs": int((served & g["is_double_fault"]).sum()),
                "unreturned": int((served & g["rally"].le(1) & won).sum()),
                "bp_faced": int(faced.sum()),
                "bp_saved": int((faced & won).sum()),
                "return_pts": int((~served).sum()),
                "return_pts_won": int((~served & won).sum()),
                "population": POPULATION,
            })
    return pd.DataFrame(rows)[SR_COLS]


def build_matches(points: pd.DataFrame, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """One row per match; winner derived from the point sequence: last point's
    winner takes the final game -> final set -> most sets wins. Retirements can
    leave sets tied -> winner is None (honest, not fabricated)."""
    meta = pd.concat([_read_matches_meta(raw_dir, g) for g in ("m", "w")])
    meta = meta[~meta.index.duplicated(keep="first")]
    rows = []
    for mid, g in points.groupby("match_id", sort=True):
        g = g.sort_values("point_number")
        # Same convention as point_engine/corpus.py: the last recorded point of a
        # (set, game) decides the game; games decide the set; sets the match.
        s1 = s2 = 0
        for _, sg in g.groupby("set_no"):
            gw = {gn: int(gg.iloc[-1]["point_winner"])
                  for gn, gg in sg.groupby("game_no")}
            g1 = sum(1 for w in gw.values() if w == 1)
            g2 = len(gw) - g1
            if g1 > g2:
                s1 += 1
            elif g2 > g1:
                s2 += 1
        m = meta.loc[mid] if mid in meta.index else None
        if s1 > s2:
            winner = m["player1"] if m is not None else "player1"
        elif s2 > s1:
            winner = m["player2"] if m is not None else "player2"
        else:
            winner = None
        rows.append({
            "match_id": mid,
            "date": g["date"].iloc[0],
            "tour": g["tour"].iloc[0],
            "tourney": None if m is None else m["tourney"],
            "round": None if m is None else m["round"],
            "surface": None if m is None else m["surface"],
            "best_of": None if m is None else m["best_of"],
            "player1": None if m is None else m["player1"],
            "player2": None if m is None else m["player2"],
            "winner": winner,
            "winner_derivation": "point_sequence_sets" if winner else "TIED_UNRESOLVED",
            "n_points": int(len(g)),
            "population": POPULATION,
        })
    return pd.DataFrame(rows)[MATCHES_COLS]


def build_all(raw_dir: Path = RAW_DIR, out_dir: Path = OUT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    points = parse_points(raw_dir)
    sr = build_serve_return(points, raw_dir)
    matches = build_matches(points, raw_dir)
    points.to_parquet(out_dir / "points.parquet", index=False)
    sr.to_parquet(out_dir / "match_serve_return.parquet", index=False)
    matches.to_parquet(out_dir / "matches.parquet", index=False)
    return {"points": points, "match_serve_return": sr, "matches": matches}


if __name__ == "__main__":
    res = build_all()
    for name, df in res.items():
        print(f"{name}: rows={len(df)} matches={df['match_id'].nunique()}")
