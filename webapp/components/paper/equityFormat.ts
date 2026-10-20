// equityFormat.ts -- UNITS formatters shared by the equity panel and chart.
// Kept dependency-free in their own module so PaperEquityPanel can import them
// without pulling PaperEquityChart's recharts bundle into the page.

export function fmtUnits(v: number): string {
  return v.toFixed(2);
}

export function fmtSignedUnits(v: number): string {
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}`;
}
