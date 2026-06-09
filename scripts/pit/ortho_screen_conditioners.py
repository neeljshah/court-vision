"""ortho_screen_conditioners.py — cheap orthogonality screen.

For each stat and each as-of conditioner already present in calibration_frame_v2,
compute corr(signal, actual - pred). A signal can ONLY add edge if the model did
NOT already absorb it => |corr| >~ 0.05 is the bar to even bother grading.

Read-only. Prints a per-stat table. This grounds the missing-feature audit:
conditioners with ~0 residual corr are ABSORBED (rejecting them cheaply); any with
|corr|>=0.05 are candidates worth a leak-free tilt grade.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
CAL = ROOT / "data" / "cache" / "calibration_frame_v2.parquet"

df = pd.read_parquet(CAL)
df["resid"] = df["actual"] - df["pred"]

# candidate as-of conditioners (already in the frame; leak-free)
CANDS = ["opp_pace", "opp_def", "rest_days", "is_b2b", "is_home", "l10_min",
         "l5_min", "l3_min", "std_min", "min_trend", "prev_min", "vac_min",
         "vac_pts", "n_out", "l5_pts_pm", "l5_reb_pm", "days_into_season"]
CANDS = [c for c in CANDS if c in df.columns]

stats = sorted(df["stat"].unique())
print(f"rows={len(df)}  stats={stats}")
print(f"conditioners present: {CANDS}\n")

hdr = f"{'cond':16s}" + "".join(f"{s:>9s}" for s in stats)
print(hdr)
print("-" * len(hdr))
flagged = []
for c in CANDS:
    row = f"{c:16s}"
    for s in stats:
        sub = df[df["stat"] == s]
        x = pd.to_numeric(sub[c], errors="coerce").to_numpy(float)
        r = sub["resid"].to_numpy(float)
        m = np.isfinite(x) & np.isfinite(r)
        if m.sum() < 200 or np.std(x[m]) < 1e-9:
            row += f"{'--':>9s}"
            continue
        cc = float(np.corrcoef(x[m], r[m])[0, 1])
        row += f"{cc:>+9.3f}"
        if abs(cc) >= 0.05:
            flagged.append((c, s, cc, int(m.sum())))
    print(row)

print("\n|corr(signal, actual-pred)| >= 0.05 (candidates NOT fully absorbed):")
if not flagged:
    print("  (none — every conditioner is absorbed; the model already prices them)")
for c, s, cc, n in sorted(flagged, key=lambda t: -abs(t[2])):
    print(f"  {c:16s} stat={s:5s} corr={cc:+.3f}  n={n}")
