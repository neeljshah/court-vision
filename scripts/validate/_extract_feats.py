"""Extract _ALL_FEATS list from player_props.py source without importing the module."""
import ast, os, re

src_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "src", "prediction", "player_props.py"
)
src = open(src_path, encoding="utf-8").read()

# Find _ALL_FEATS = [ ... ]
m = re.search(r"_ALL_FEATS\s*=\s*(\[.*?\])", src, re.DOTALL)
if not m:
    print("Could not find _ALL_FEATS")
else:
    feats = ast.literal_eval(m.group(1))
    print(f"_ALL_FEATS: {len(feats)} features")
    # Write to a simple JSON for use by prop_holdout.py
    import json
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_all_feats.json")
    json.dump(feats, open(out, "w"))
    print(f"Written to {out}")

# Also check _PROP_STATS
m2 = re.search(r'_PROP_STATS\s*=\s*\((.*?)\)', src, re.DOTALL)
if m2:
    print(f"_PROP_STATS: {m2.group(1)[:80]}")
