// Honest formatting helpers. Null -> "n/a" everywhere; we NEVER invent a number.

export function fmtPct(x: number | null | undefined, signed = false): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "n/a";
  const pct = (x * 100).toFixed(1) + "%";
  return signed && x >= 0 ? "+" + pct : pct;
}

export function fmtPrice(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "n/a";
  return x.toFixed(2); // decimal odds
}

export function edgeTone(e: number | null | undefined): "pos" | "neg" | "neutral" {
  if (e === null || e === undefined || Number.isNaN(e)) return "neutral";
  return e >= 0 ? "pos" : "neg";
}
