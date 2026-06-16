"""
cost_ledger.py -- append total_cost_usd per headless claude -p run to a parquet.

Usage:
  claude -p "your prompt" --output-format json > /tmp/run.json
  python scripts/platformkit/cost_ledger.py --input /tmp/run.json [--tag nightly_eval]

Or pipe directly:
  claude -p "your prompt" --output-format json | python scripts/platformkit/cost_ledger.py

Output parquet: data/ops/cost_ledger.parquet
Columns: ts, tag, model, total_cost_usd, input_tokens, output_tokens, duration_ms

NOTE: --max-turns and --max-budget-usd do NOT exist as claude CLI flags.
      Cap turns via subagent maxTurns frontmatter. Read cost post-hoc from JSON output.
"""
import argparse
import json
import os
import sys
import time

LEDGER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "ops", "cost_ledger.parquet"
)


def parse_run_json(data: dict) -> dict:
    """Extract cost fields from claude -p --output-format json output."""
    return {
        "ts": time.time(),
        "total_cost_usd": data.get("total_cost_usd", 0.0),
        "model": data.get("model", ""),
        "input_tokens": data.get("usage", {}).get("input_tokens", 0),
        "output_tokens": data.get("usage", {}).get("output_tokens", 0),
        "duration_ms": data.get("duration_ms", 0),
    }


def append_to_parquet(record: dict, tag: str, path: str) -> None:
    """Append one record row to the parquet ledger (create if absent)."""
    try:
        import pandas as pd
    except ImportError:
        sys.stderr.write("[cost_ledger] pandas not available; writing JSONL fallback\n")
        jsonl_path = path.replace(".parquet", ".jsonl")
        os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
        record["tag"] = tag
        with open(jsonl_path, "a", encoding="ascii", errors="replace") as f:
            f.write(json.dumps(record) + "\n")
        return

    record["tag"] = tag
    new_row = pd.DataFrame([record])

    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, new_row], ignore_index=True)
    else:
        combined = new_row

    combined.to_parquet(path, index=False)


def main():
    parser = argparse.ArgumentParser(description="Append claude -p cost to ledger parquet")
    parser.add_argument("--input", "-i", help="Path to claude -p JSON output (default: stdin)")
    parser.add_argument("--tag", "-t", default="manual", help="Label for this run")
    parser.add_argument("--ledger", default=LEDGER_PATH, help="Output parquet path")
    args = parser.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            raw = f.read()
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        sys.stderr.write("[cost_ledger] empty input; nothing written\n")
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"[cost_ledger] JSON parse error: {exc}\n")
        sys.exit(1)

    record = parse_run_json(data)
    append_to_parquet(record, tag=args.tag, path=args.ledger)

    cost = record["total_cost_usd"]
    print(
        f"[cost_ledger] appended: tag={args.tag} cost=${cost:.6f} "
        f"model={record['model']} -> {args.ledger}"
    )


if __name__ == "__main__":
    main()
