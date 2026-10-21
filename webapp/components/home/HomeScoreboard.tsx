// HomeScoreboard -- below the fold: the cross-sport in-game scoreboard (paired model minus
// market, 95% CI, verdict), largest n first so small-sample rows (the n = 55 CRPS row)
// never sit above larger-n ones (P2.3). Verdict pills are neutral (P4.7). Read verbatim
// from webapp/public/data/showcase/cross_sport_scoreboard.json.
import Link from "next/link";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import { DeltaBars } from "@/components/charts/DeltaBars";
import { modelMinusMarket, DELTA_LEGEND } from "@/lib/scoreboardDelta";

export type ScoreRow = {
  sport: string; market: string; checkpoint: string; n: number;
  paired_delta_mean: number; paired_delta_95ci: [number, number]; verdict: string; source: string;
};
export type Scoreboard = { generated_at: string; n_rows: number; rows: ScoreRow[] };

const fmt = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(4);
export const SMALL_SAMPLE_NOTE =
  "small-sample retrospective diagnostic (n under 60 games); not a claim about the market";

/** Stable sort by n, largest first (evidence weight, not flattery). */
export const byEvidenceWeight = (rows: ScoreRow[]) => [...rows].sort((a, b) => b.n - a.n);

export function HomeScoreboard({ board }: { board: Scoreboard | null }) {
  if (!board) return <p className="mt-6 text-sm text-stale">Scoreboard artifact not staged on this clone.</p>;
  const asOf = board.generated_at;
  const day = asOf.slice(0, 10);
  const rows = byEvidenceWeight(board.rows);
  return (
    <section aria-labelledby="scoreboard-h" className="mt-10">
      <h2 id="scoreboard-h" className="microlabel">In-game scoreboard: model minus market</h2>
      <Panel className="mt-2">
        <PanelHead title="paired Brier / CRPS difference, 95% CI, verdict (lower is better)" asOf={day} />
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr className="text-left">
                <th className="microlabel px-3 py-2">sport</th>
                <th className="microlabel px-3 py-2">market</th>
                <th className="microlabel px-3 py-2">checkpoint</th>
                <th className="microlabel px-3 py-2 text-right">n</th>
                <th className="microlabel px-3 py-2">model &minus; market</th>
                <th className="microlabel px-3 py-2 text-right">95% CI</th>
                <th className="microlabel px-3 py-2">verdict</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const d = modelMinusMarket(r.paired_delta_mean, r.paired_delta_95ci);
                const small = r.verdict.startsWith("MODEL_SHARPER");
                return (
                  <tr key={`${r.sport}|${r.checkpoint}`} className="border-t border-border hover:bg-surface-2">
                    <td className="px-3 py-2 font-data">{r.sport}</td>
                    <td className="px-3 py-2">{r.market}</td>
                    <td className="px-3 py-2 font-data text-xs">{r.checkpoint}</td>
                    <td className="px-3 py-2 text-right font-data tabular whitespace-nowrap">{r.n}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <DeltaBars delta={d.delta} ci={d.ci} verdict={r.verdict} />
                        <span className="font-data tabular whitespace-nowrap text-foreground">{fmt(d.delta)}</span>
                        <ReceiptChip sourceArtifact={r.source} asOf={asOf} verified="edge_claimed:false"
                          verdict={r.verdict} n={r.n} ci={d.ci} />
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right font-data tabular whitespace-nowrap text-muted-foreground">
                      [{fmt(d.ci[0])}, {fmt(d.ci[1])}]
                    </td>
                    <td className="px-3 py-2">
                      <span className="inline-block whitespace-nowrap border border-border px-1.5 py-px font-data text-xs text-foreground">
                        {r.verdict}
                      </span>
                      {small && <div className="mt-0.5 text-xs text-muted-foreground">{SMALL_SAMPLE_NOTE}</div>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="border-t border-border px-3 py-2 text-xs text-muted-foreground" data-testid="delta-legend">
          {DELTA_LEGEND} (lower CRPS is better too).
        </p>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-3 py-2">
          <span className="microlabel">
            {board.n_rows} rows, sorted by n. Losses and underpowered rows are shown, not filtered.
          </span>
          <Link href="/receipts/" className="microlabel text-primary hover:underline">full receipts ledger</Link>
        </div>
      </Panel>
    </section>
  );
}
