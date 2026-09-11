"""G388 real-pass scoring: pairing, per-context accounting, audit skeleton."""
import csv, json, pathlib, sys
from scripts.platformkit.tracking import g387_tiles as T
from scripts.platformkit.tracking import g388_score as S

D = pathlib.Path("docs/evidence/tracking/g388_paint_band_protocol_2026-09-11")
TR = pathlib.Path("C:/Users/neelj/nba-track-a12/.g388_out/real_terra")
SO = pathlib.Path("C:/Users/neelj/nba-track-a12/.g388_out/real_sol")
G387 = pathlib.Path("docs/evidence/tracking/g387_paint_localization_controls_2026-09-11")

vis = {r["context_id"]: r["claude_visibility"] for r in T.read_csv(D / "visibility.csv")}
contexts = sorted({r["opaque_id"].replace("G387_", "G388_") for r in T.read_csv(G387 / "transforms.csv")})
results = S.pair_contexts(contexts, {"terra": TR, "sol": SO})
pairs, frames = S.real_tables(results, vis)
T.write_csv(D / "pairing.csv", pairs) if pairs else None
T.write_csv(D / "per_frame.csv", frames)
summary = {
    "contexts": len(frames),
    "contexts_with_at_least_one_candidate_pair": sum(f["pairs"] != "0" for f in frames),
    "candidate_pairs": len(pairs),
    "family_disagreement_contexts": sum(f["family_disagreement"] == "YES" for f in frames),
    "terra_missing_or_malformed": sum(f["terra_state"] in ("MISSING", "MALFORMED") for f in frames),
    "sol_missing_or_malformed": sum(f["sol_state"] in ("MISSING", "MALFORMED") for f in frames),
    "terra_absent_or_unknown": sum(f["terra_state"] in ("ABSENT", "UNKNOWN") for f in frames),
    "sol_absent_or_unknown": sum(f["sol_state"] in ("ABSENT", "UNKNOWN") for f in frames),
    "claude_visible_yes": sum(f["claude_visibility"] == "YES" for f in frames),
}
print(json.dumps(summary, indent=2, sort_keys=True))
(D / "input" / "real_pairing_receipt.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
