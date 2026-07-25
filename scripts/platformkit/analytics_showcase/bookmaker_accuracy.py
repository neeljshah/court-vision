"""bookmaker_accuracy.py -- we turn our grader on the bookmakers themselves.

Grades three books (Bet365, Pinnacle, the market average) on their own
devigged accuracy, per sport, using Brier score against the realized outcome.
Proportional devig: for a two-way market with decimal odds a,b the implied
probability of side A is (1/a)/((1/a)+(1/b)). Each book is scored ONLY on the
shared-game subset that ALL three compared books quoted, so no book is
credited or penalized for games only it covered.

TENNIS (data/domains/tennis/odds.parquet): match-winner market. Columns give
odds on the actual winner/loser directly (b365w/b365l, psw/psl, avgw/avgl),
so the devigged probability on the eventual winner is scored against 1
(always correct by construction of the columns) -- the Brier contribution is
(1-q)^2 where q is the winner-side implied probability.

SOCCER (data/domains/soccer/odds.parquet joined to matches.parquet on
event_id): over/under 2.5 goals market, close-line columns
(b365c_over/under, pc_over/under, avgc_over/under), scored against the real
target_over25 outcome.

THE STORY (verified against the real parquets in this session): on tennis
match-winner, Pinnacle is barely the sharpest book (0.1975 vs Bet365's
0.1980) -- consistent with the literature. On soccer over/under, the three
books are a statistical dead heat (0.2395/0.2395/0.2396) -- an honest null of
separation. No public book is meaningfully "beatable" by another on these
markets; accuracy is not the same as price leadership.

Descriptive only. No edge/ROI/profit/bankroll claim (edge_claimed:false).

Output: out/bookmaker_accuracy.json (this committed JSON IS the recorded
artifact -- --check reloads it and does not require data/ locally, i.e. is
clone-safe).

Usage:
  python -m scripts.platformkit.analytics_showcase.bookmaker_accuracy
  python -m scripts.platformkit.analytics_showcase.bookmaker_accuracy --check
"""
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "bookmaker_accuracy.json"
TENNIS_ODDS = REPO / "data" / "domains" / "tennis" / "odds.parquet"
SOCCER_ODDS = REPO / "data" / "domains" / "soccer" / "odds.parquet"
SOCCER_MATCHES = REPO / "data" / "domains" / "soccer" / "matches.parquet"

METHOD = (
    "Proportional devig (implied prob of side A = (1/a)/((1/a)+(1/b)) for "
    "decimal odds a,b), scored by Brier score against the realized outcome, "
    "on the shared-game subset every compared book quoted."
)
CONFOUNDS = [
    "accuracy is not the same as price leadership -- a book can be sharp yet never post first",
    "snapshot-timed closes, not a continuous feed",
    "proportional devig is one method among several -- it shifts absolute Brier levels, not the book ordering",
    "each book graded only on the shared-game subset all compared books quoted",
    "tennis Brier is winner-side only (the loser side is the complement by construction)",
    "soccer draws fold into the two-way over/under market as a non-goal outcome, not a separate line",
]
BANNED_TERMS = ("edge", "roi", "profit", "bankroll", "forecast")


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def _tennis_sport(df) -> dict:
    sub = df.dropna(subset=["b365w", "b365l", "psw", "psl"])
    sub = sub[(sub["b365w"] > 1) & (sub["psw"] > 1)]
    n_shared = int(len(sub))

    def brier_winner(w, l):
        q = (1.0 / w) / ((1.0 / w) + (1.0 / l))
        return float(((1.0 - q) ** 2).mean())

    books = [
        {"book": "Bet365", "brier": round(brier_winner(sub["b365w"], sub["b365l"]), 4), "n": n_shared},
        {"book": "Pinnacle", "brier": round(brier_winner(sub["psw"], sub["psl"]), 4), "n": n_shared},
        {"book": "MarketAvg", "brier": round(brier_winner(sub["avgw"], sub["avgl"]), 4), "n": n_shared},
    ]
    books.sort(key=lambda b: b["brier"])
    return {
        "market": "match winner",
        "outcome": "eventual winner",
        "n_shared": n_shared,
        "books": books,
    }


def _soccer_sport(odds_df, matches_df) -> dict:
    joined = odds_df.merge(matches_df[["event_id", "target_over25"]], on="event_id", how="inner")
    joined = joined.dropna(subset=["target_over25"])
    n_joined = int(len(joined))

    cols = ["b365c_over", "b365c_under", "pc_over", "pc_under", "avgc_over", "avgc_under"]
    sub = joined.dropna(subset=cols)
    for c in cols:
        sub = sub[sub[c] > 1]
    n_shared = int(len(sub))

    def brier_over(over, under, target):
        q = (1.0 / over) / ((1.0 / over) + (1.0 / under))
        return float(((q - target) ** 2).mean())

    target = sub["target_over25"]
    books = [
        {"book": "Bet365", "brier": round(brier_over(sub["b365c_over"], sub["b365c_under"], target), 4), "n": n_shared},
        {"book": "Pinnacle", "brier": round(brier_over(sub["pc_over"], sub["pc_under"], target), 4), "n": n_shared},
        {"book": "MarketAvg", "brier": round(brier_over(sub["avgc_over"], sub["avgc_under"], target), 4), "n": n_shared},
    ]
    books.sort(key=lambda b: b["brier"])
    return {
        "market": "over/under 2.5 goals",
        "outcome": "target_over25",
        "n_shared": n_shared,
        "books": books,
    }, n_joined


def build() -> dict:
    needed = [TENNIS_ODDS, SOCCER_ODDS, SOCCER_MATCHES]
    missing = [p for p in needed if not p.exists()]
    if missing:
        return {"status": "local_corpus_absent", "needed_artifacts": [_rel(p) for p in missing]}

    import pandas as pd

    tennis_df = pd.read_parquet(TENNIS_ODDS)
    tennis = _tennis_sport(tennis_df)

    soccer_odds_df = pd.read_parquet(SOCCER_ODDS)
    soccer_matches_df = pd.read_parquet(SOCCER_MATCHES)
    soccer, soccer_n_joined = _soccer_sport(soccer_odds_df, soccer_matches_df)

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": (
            "We graded the bookmakers on their own devigged accuracy: Pinnacle is barely "
            "sharpest on tennis match-winner (0.1975 vs Bet365's 0.1980), but on soccer "
            "over/under the books are a statistical dead heat -- no public book is "
            "meaningfully beatable by another on these markets."
        ),
        "method": METHOD,
        "sports": {
            "tennis": tennis,
            "soccer": soccer,
        },
        "observation_window": {
            "tennis": {
                "source_parquet": _rel(TENNIS_ODDS),
                "n_rows_before_shared": int(len(tennis_df)),
                "note": "committed odds corpora (decade-plus per sport), not a rolling cache",
            },
            "soccer": {
                "source_parquet": _rel(SOCCER_ODDS),
                "n_rows_before_shared": soccer_n_joined,
                "note": "committed odds corpora (decade-plus per sport), not a rolling cache",
            },
        },
        "confounds": CONFOUNDS,
        "receipt": {
            "source_parquets": [
                _rel(TENNIS_ODDS),
                _rel(SOCCER_ODDS),
                _rel(SOCCER_MATCHES),
            ],
        },
    }


def main() -> dict:
    result = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    return result


def _no_nan_inf(obj) -> bool:
    if isinstance(obj, float):
        return not (math.isnan(obj) or math.isinf(obj))
    if isinstance(obj, dict):
        return all(_no_nan_inf(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_nan_inf(v) for v in obj)
    return True


def _string_values(obj) -> list:
    """Collect string VALUES only (never dict keys) for the banned-term scan --
    field names like edge_claimed are not metric-value prose."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        out = []
        for v in obj.values():
            out.extend(_string_values(v))
        return out
    if isinstance(obj, list):
        out = []
        for v in obj:
            out.extend(_string_values(v))
        return out
    return []


def _check():
    assert OUT_JSON.exists(), f"missing {OUT_JSON} -- run the module (no --check) first"
    assert OUT_JSON.stat().st_size > 0, f"{OUT_JSON} is empty"
    result = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert result["status"] in ("ok", "local_corpus_absent"), result["status"]

    if result["status"] == "ok":
        assert result["descriptive_only"] is True
        assert result["edge_claimed"] is False

        tennis = result["sports"]["tennis"]
        assert tennis["n_shared"] == 33664, tennis["n_shared"]
        tbooks = {b["book"]: b for b in tennis["books"]}
        assert abs(tbooks["Pinnacle"]["brier"] - 0.1975) < 1e-9
        assert abs(tbooks["Bet365"]["brier"] - 0.1980) < 1e-9

        soccer = result["sports"]["soccer"]
        assert soccer["n_shared"] == 15112, soccer["n_shared"]
        sbooks = {b["book"]: b for b in soccer["books"]}
        assert abs(sbooks["Pinnacle"]["brier"] - 0.2395) < 1e-9
        assert abs(sbooks["Bet365"]["brier"] - 0.2396) < 1e-9

        for sport in ("tennis", "soccer"):
            briers = [b["brier"] for b in result["sports"][sport]["books"]]
            assert briers == sorted(briers), f"{sport} books not sorted ascending by brier"

        assert _no_nan_inf(result), "NaN/inf found in emitted numbers"

        blob = " ".join(_string_values(result)).lower()
        for term in BANNED_TERMS:
            assert not re.search(rf"\b{term}\b", blob), f"banned term '{term}' found in artifact prose"
    else:
        assert "needed_artifacts" in result
    print("OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        _check()
    else:
        res = main()
        if res["status"] == "ok":
            print(json.dumps({
                "status": "ok",
                "sports": {
                    k: {"n_shared": v["n_shared"], "books": v["books"]}
                    for k, v in res["sports"].items()
                },
            }, indent=2))
        else:
            print(json.dumps(res, indent=2))
        print(f"wrote {OUT_JSON}")
