"""Print and write a compact tracking-quality scoreboard."""
import json
from pathlib import Path
from statistics import median


def report(root=Path("data/tracking_reports")):
    root = Path(root)
    rows = []
    ledger = root / "ledger.jsonl"
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            detail = item.get("report")
            if isinstance(detail, dict):
                rows.append({**item, **detail})
    for path in root.glob("*/*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            rows.append(item)
    scores = {}
    for item in rows:
        sport = item.get("sport")
        if not isinstance(sport, str):
            continue
        scores.setdefault(sport, []).append(item)
    result = {}
    for sport, items in sorted(scores.items()):
        result[sport] = {
            "n": len(items),
            "pass_rate": sum(bool(x.get("passed")) for x in items) / len(items),
            "median_ball_valid_pct": median([x["ball_valid_pct"] for x in items if isinstance(x.get("ball_valid_pct"), (int, float))]) if any(isinstance(x.get("ball_valid_pct"), (int, float)) for x in items) else None,
            "median_coverage_pct": median([x["coverage_pct"] for x in items if isinstance(x.get("coverage_pct"), (int, float))]) if any(isinstance(x.get("coverage_pct"), (int, float)) for x in items) else None,
        }
    (root / "scoreboard.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("SPORT       N  PASS_RATE  BALL_VALID  COVERAGE")
    for sport, score in result.items():
        print(f"{sport:<11} {score['n']:>2} {score['pass_rate']:>9.1%}  {score['median_ball_valid_pct']!s:>10}  {score['median_coverage_pct']!s:>8}")
    return result


if __name__ == "__main__":
    report()
