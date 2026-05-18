// Deterministic seeded LCG equity curve generator
export interface EquityPoint { pick: number; cumRoi: number }

export function generateEquityCurve(seed = 42, n = 312, targetRoi = 3.8): EquityPoint[] {
  let s = seed
  const lcg = () => { s = (1664525 * s + 1013904223) & 0xffffffff; return (s >>> 0) / 0xffffffff }
  const results: EquityPoint[] = []
  let cumPnl = 0
  const drift = targetRoi / n / 100
  const std = 0.012
  for (let i = 1; i <= n; i++) {
    const u1 = lcg(), u2 = lcg()
    const z = Math.sqrt(-2 * Math.log(u1 + 1e-10)) * Math.cos(2 * Math.PI * u2)
    cumPnl += drift + std * z / Math.sqrt(n)
    results.push({ pick: i, cumRoi: Math.round(cumPnl * 10000) / 100 })
  }
  // normalize end to exactly targetRoi
  const actual = results[n - 1].cumRoi
  return results.map(p => ({ pick: p.pick, cumRoi: Math.round((p.cumRoi - actual + targetRoi) * 100) / 100 }))
}
