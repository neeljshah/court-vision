"""Is jump_p95 measuring tracker error, or player movement across emission gaps?

The harness diffs consecutive EMITTED rows of the same track_id with no
frame-gap normalisation. The tennis adapter labels players 1 and 2 for the
entire video and never issues new ids, so a 30-second cutaway becomes ONE step
containing whatever distance the player really covered.

This recomputes jump_p95 on real tracking output two ways:
  as-is            -- what the harness sees today
  gap-split        -- identity reset when the emission gap exceeds a threshold,
                      which is the honest statement (identity across a long gap
                      is unknown, not continuous)
Run: python jump_gap_probe.py <tracking_data.csv> [max_gap_frames]
"""
import sys
import pandas as pd


def main(argv):
    df = pd.read_csv(argv[1])
    max_gap = int(argv[2]) if len(argv) > 2 else 30
    players = df[df["cls"] == "player"].copy() if "cls" in df else df.copy()
    if players.empty:
        print("no player rows")
        return 1

    def p95(frame):
        g = frame.sort_values(["seg", "frame"]).groupby("seg")
        jump = ((g["x"].diff() ** 2 + g["y"].diff() ** 2) ** 0.5).dropna()
        return float(jump.quantile(0.95)) if len(jump) else 0.0, len(jump)

    players = players.sort_values(["track_id", "frame"])
    players["seg"] = players["track_id"].astype(str)
    asis, n_asis = p95(players)

    gaps = players.groupby("track_id")["frame"].diff()
    breaks = (gaps > max_gap).groupby(players["track_id"]).cumsum().fillna(0)
    players["seg"] = players["track_id"].astype(str) + "_" + breaks.astype(int).astype(str)
    split, n_split = p95(players)

    print("file        %s" % argv[1])
    print("player rows %d, distinct track_ids %d" % (len(players), players["track_id"].nunique()))
    print("max emission gap observed: %d frames" % int(gaps.max() if len(gaps.dropna()) else 0))
    print()
    print("jump_p95 as-is       %8.3f ft   (steps %d)" % (asis, n_asis))
    print("jump_p95 gap-split   %8.3f ft   (steps %d)  gap > %d frames" % (split, n_split, max_gap))
    print("tennis gate is 8.0 ft")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
