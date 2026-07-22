// app/receipts/page.tsx -- public Receipts / Scoreboard page.
//
// Static export: the RunPod pod that produced live forward measurements was
// stopped 2026-07-20, so a "yesterday's predictions" live feed is honestly
// unavailable right now. This renders the same rows as RECEIPTS.md (repo
// root) from a build-time JSON snapshot -- read straight off disk here (no
// client fetch, no live claim). Regenerate the snapshot with:
//   python -m scripts.platformkit.receipts.build_receipts --json
//
// Honesty rails: calibration/sharpness only, never $/ROI/edge; verdicts
// include losses (MARKET_SHARPER_PROVISIONAL, UNDERPOWERED) unfiltered.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { PRODUCT_NAME } from "@/lib/api";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

export const metadata = {
  title: "Receipts",
  description:
    "The calibration receipts ledger: model vs. market sharpness per sport/market, " +
    "as measured, losses included. No dollar edge claimed.",
};

type ReceiptRow = {
  sport_market: string;
  checkpoint: string;
  model: string;
  market: string;
  delta_ci: string;
  n: number | string;
  verdict: string;
  src: string;
};

type ReceiptsJson = {
  generated_at: string;
  batch_date: string;
  batch_hash: string;
  rows: ReceiptRow[];
  skipped: string[];
  honest_rejects: { count: number; as_of: string; source: string };
};

// ponytail: read the checked-in snapshot straight off disk at build time --
// this page is part of a static export, so there is no server to hit later.
function loadReceipts(): ReceiptsJson | null {
  try {
    const raw = readFileSync(join(process.cwd(), "public/receipts.json"), "utf-8");
    return JSON.parse(raw) as ReceiptsJson;
  } catch {
    return null;
  }
}

// Verdict -> ink. Honesty is the feature: losses (MARKET_SHARPER*) render
// red, not hidden or softened; UNDERPOWERED (most rows) is neutral amber,
// not green -- an underpowered result is not a win.
function verdictClass(verdict: string): string {
  if (verdict.startsWith("MODEL_SHARPER")) return "text-up";
  if (verdict.startsWith("MARKET_SHARPER")) return "text-down";
  if (verdict === "UNDERPOWERED") return "text-stale";
  return "text-muted-foreground";
}

export default function ReceiptsPage() {
  const data = loadReceipts();

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header>
        <p className="microlabel">receipts / scoreboard</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          {PRODUCT_NAME} receipts
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Every row below is read verbatim from a machine-readable artifact on disk
          (path cited per row) -- no number here is hand-typed. This ledger claims
          calibration/sharpness only, never a dollar edge, ROI, or bankroll result;
          verdicts include losses (MARKET_SHARPER_PROVISIONAL, UNDERPOWERED) exactly
          as measured. Full history:{" "}
          <span className="font-data text-foreground">RECEIPTS.md</span> in the repo
          root.
        </p>
        <p className="mt-3 text-[11px] font-mono uppercase tracking-wide text-stale">
          The live forward-measurement pod was stopped 2026-07-20 -- this is a static
          snapshot, not a live feed. Batch date and generation time are shown below.
        </p>
      </header>

      {!data ? (
        <Panel className="p-6 text-center text-sm text-muted-foreground">
          receipts.json unavailable -- run{" "}
          <code className="font-data">
            python -m scripts.platformkit.receipts.build_receipts --json
          </code>{" "}
          to regenerate.
        </Panel>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Panel>
              <PanelHead title="batch" asOf={data.generated_at} />
              <div className="p-3">
                <div className="text-lg font-semibold text-foreground">
                  {data.batch_date}
                </div>
                <div className="mt-1 font-data text-[11px] text-faint">
                  batch {data.batch_hash}
                </div>
              </div>
            </Panel>
            <Panel>
              <PanelHead title="honest rejects" asOf={data.honest_rejects.as_of} />
              <div className="p-3">
                <div className="text-lg font-semibold text-foreground">
                  <Num>{data.honest_rejects.count}</Num> recorded REJECT/DEFER verdicts
                </div>
                <div className="mt-1 font-data text-[11px] text-faint">
                  source: {data.honest_rejects.source}
                </div>
              </div>
            </Panel>
          </div>

          <Panel>
            <PanelHead title="calibration ledger" asOf={data.generated_at} />
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="microlabel px-3 py-1.5">sport/market</th>
                    <th className="microlabel px-3 py-1.5">checkpoint</th>
                    <th className="microlabel px-3 py-1.5">model</th>
                    <th className="microlabel px-3 py-1.5">market</th>
                    <th className="microlabel px-3 py-1.5">delta (95% ci)</th>
                    <th className="microlabel px-3 py-1.5 text-right">n</th>
                    <th className="microlabel px-3 py-1.5">verdict</th>
                    <th className="microlabel px-3 py-1.5">source</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={i} className="border-b border-border hover:bg-surface-2">
                      <td className="px-3 py-1.5">{r.sport_market}</td>
                      <td className="px-3 py-1.5">{r.checkpoint}</td>
                      <td className="px-3 py-1.5 font-data">{r.model}</td>
                      <td className="px-3 py-1.5 font-data">{r.market}</td>
                      <td className="px-3 py-1.5 font-data">{r.delta_ci}</td>
                      <td className="px-3 py-1.5 text-right">
                        <Num>{r.n}</Num>
                      </td>
                      <td className={`px-3 py-1.5 font-mono text-[11px] font-bold ${verdictClass(r.verdict)}`}>
                        {r.verdict}
                      </td>
                      <td className="px-3 py-1.5 font-data text-[11px] text-faint">{r.src}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.skipped.length > 0 && (
              <div className="border-t border-border px-3 py-2 text-[11px] text-faint">
                Skipped inputs (not found or unreadable, no row emitted): {data.skipped.join("; ")}
              </div>
            )}
          </Panel>
        </>
      )}
    </main>
  );
}
