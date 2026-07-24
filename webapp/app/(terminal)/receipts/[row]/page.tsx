// app/receipts/[row]/page.tsx -- drill on one receipts row.
//
// Static export: reads the same on-disk snapshot as the ledger (public/
// receipts.json) plus three staged showcase artifacts -- Murphy decomposition,
// bootstrap-CI calibration stability, and Brier skill scores -- straight off
// disk at build time (the /receipts pattern). No client fetch, no /api route.
//
// Honesty rails: calibration/sharpness only, never $/ROI/edge. Only mlb and
// soccer_intl have staged decompositions; any other surface (nba) renders an
// honest "not measured on this clone" chip rather than a fabricated figure.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import Link from "next/link";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import { MurphyBars } from "@/components/charts/MurphyBars";
import { ReliabilityBins } from "@/components/charts/ReliabilityBins";
import { loadArtifact, receiptChip, type Artifact } from "@/lib/showcase.server";

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

function loadRows(): ReceiptRow[] {
  try {
    const raw = readFileSync(join(process.cwd(), "public/receipts.json"), "utf-8");
    return (JSON.parse(raw).rows ?? []) as ReceiptRow[];
  } catch {
    return [];
  }
}

// output:'export' pre-renders one page per ledger row (index = id).
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";
export async function generateStaticParams() {
  const rows = loadRows();
  return (rows.length ? rows.map((_, i) => String(i)) : ["0"]).map((row) => ({ row }));
}

// The receipt row's sport_market maps to a staged artifact sport key only for
// the two corpora that carry a decomposition; everything else is honestly null.
function sportKey(sm: string): "mlb" | "soccer_intl" | null {
  if (sm.startsWith("soccer_intl")) return "soccer_intl";
  if (sm.startsWith("mlb")) return "mlb";
  return null;
}

type Side = {
  brier?: number;
  brier_model?: number;
  brier_market?: number;
  bss_model_vs_clim?: number;
  bss_model_vs_market?: number;
  reliability?: number;
  resolution?: number;
  uncertainty?: number;
  n_eligible_bins?: number;
  n_significant_bins?: number;
  n_within_noise_bins?: number;
  bins?: {
    bin_lo: number;
    bin_hi: number;
    n: number;
    mean_p: number;
    mean_y: number;
    gap?: number;
    gap_ci?: [number, number];
    significant?: boolean;
  }[];
};

function side(a: Artifact | null, sport: string, path: string[]): Side | null {
  let node: unknown = (a?.sports as Record<string, unknown> | undefined)?.[sport];
  for (const k of path) node = (node as Record<string, unknown> | undefined)?.[k];
  return (node as Side) ?? null;
}

export default function ReceiptDrillPage({ params }: { params: { row: string } }) {
  const rows = loadRows();
  const idx = Number(params.row);
  const r = Number.isInteger(idx) ? rows[idx] : undefined;

  if (!r) {
    return (
      <main className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
        <Link href="/receipts" className="microlabel text-primary hover:underline">
          &larr; receipts
        </Link>
        <Panel className="p-6 text-center text-sm text-muted-foreground">
          No ledger row with id <span className="font-data">{params.row}</span>.
        </Panel>
      </main>
    );
  }

  const sport = sportKey(r.sport_market);
  const murphy = sport ? loadArtifact("murphy_decomposition") : null;
  const calib = sport ? loadArtifact("calibration_stability") : null;
  const brier = sport ? loadArtifact("brier_skill_scores") : null;

  const mModel = sport ? side(murphy, sport, ["model_prob"]) : null;
  const cModel = sport ? side(calib, sport, ["sides", "model_prob"]) : null;
  const cMarket = sport ? side(calib, sport, ["sides", "market_prob"]) : null;
  const bAll = sport ? side(brier, sport, ["grains", "all"]) : null;

  const bins = [
    ...(cModel?.bins ?? []).map((b) => ({ p: b.mean_p, y: b.mean_y, n: b.n, source: "model" as const })),
    ...(cMarket?.bins ?? []).map((b) => ({ p: b.mean_p, y: b.mean_y, n: b.n, source: "market" as const })),
  ];

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
      <header>
        <Link href="/receipts" className="microlabel text-primary hover:underline">
          &larr; receipts / scoreboard
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          {r.sport_market}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          The ledger row, decomposed. Every figure below is read from a staged
          artifact on disk (cited per panel); this drill describes calibration
          and sharpness only -- no dollar edge, ROI, or bankroll is claimed.
        </p>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 font-data text-[12px] sm:grid-cols-4">
          <div><dt className="microlabel">model</dt><dd className="tabular">{r.model}</dd></div>
          <div><dt className="microlabel">market</dt><dd className="tabular">{r.market}</dd></div>
          <div><dt className="microlabel">delta (95% ci)</dt><dd className="tabular">{r.delta_ci}</dd></div>
          <div><dt className="microlabel">n</dt><dd className="tabular"><Num>{r.n}</Num></dd></div>
        </dl>
        <p className="mt-2 text-[11px] font-mono uppercase tracking-wide text-stale">
          verdict {r.verdict} -- source {r.src}
        </p>
      </header>

      {!sport || !mModel ? (
        <Panel className="flex items-center justify-between gap-3 p-6 text-sm text-muted-foreground">
          <span>
            No Murphy decomposition or bootstrap-CI stability is staged for this
            surface on this clone. Only the mlb and soccer_intl in-game corpora
            carry one; this row is shown from the ledger figures above.
          </span>
          <ReceiptChip {...receiptChip(null)} />
        </Panel>
      ) : (
        <>
          <Panel>
            <PanelHead
              title="Murphy decomposition (model)"
              asOf={murphy?.generated_at as string ?? null}
              right={<ReceiptChip {...receiptChip(murphy)} />}
            />
            <div className="p-3">
              <MurphyBars
                reliability={mModel.reliability ?? 0}
                resolution={mModel.resolution ?? 0}
                uncertainty={mModel.uncertainty ?? 0}
              />
              <p className="mt-2 text-[11px] leading-snug text-faint">
                Brier = reliability - resolution + uncertainty (10-bin). Lower
                reliability and higher resolution are better; uncertainty is the
                irreducible base-rate floor. Descriptive, not an edge claim.
                Source: murphy_decomposition.json.
              </p>
            </div>
          </Panel>

          <Panel>
            <PanelHead
              title="reliability curve (model vs market)"
              asOf={calib?.as_of as string ?? null}
              right={<ReceiptChip {...receiptChip(calib)} />}
            />
            <div className="flex flex-col items-start gap-3 p-3 sm:flex-row sm:items-center">
              <ReliabilityBins bins={bins} />
              <p className="text-[11px] leading-snug text-faint">
                Predicted probability (x) vs observed frequency (y) against the
                perfect-calibration ideal (dashed). Amber = model, blue = market.
                Hover a point for its bin count. Source: calibration_stability.json.
              </p>
            </div>
          </Panel>

          <Panel>
            <PanelHead
              title="bootstrap CI per bin (model)"
              asOf={calib?.as_of as string ?? null}
              right={<ReceiptChip {...receiptChip(calib)} />}
            />
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="microlabel px-3 py-1.5">bin</th>
                    <th className="microlabel px-3 py-1.5 text-right">n</th>
                    <th className="microlabel px-3 py-1.5 text-right">gap</th>
                    <th className="microlabel px-3 py-1.5">gap 95% ci</th>
                    <th className="microlabel px-3 py-1.5">excludes 0?</th>
                  </tr>
                </thead>
                <tbody>
                  {(cModel?.bins ?? []).map((b, i) => (
                    <tr key={i} className="border-b border-border">
                      <td className="px-3 py-1.5 font-data tabular">
                        {b.bin_lo.toFixed(1)}-{b.bin_hi.toFixed(1)}
                      </td>
                      <td className="px-3 py-1.5 text-right font-data tabular"><Num>{b.n}</Num></td>
                      <td className="px-3 py-1.5 text-right font-data tabular">
                        {b.gap != null ? b.gap.toFixed(4) : "--"}
                      </td>
                      <td className="px-3 py-1.5 font-data tabular text-faint">
                        {b.gap_ci ? `[${b.gap_ci[0].toFixed(3)}, ${b.gap_ci[1].toFixed(3)}]` : "--"}
                      </td>
                      <td className={`px-3 py-1.5 font-mono text-[11px] ${b.significant ? "text-down" : "text-faint"}`}>
                        {b.significant ? "yes -- gap real" : "no -- within noise"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-border px-3 py-2 text-[11px] leading-snug text-faint">
              {cModel?.n_significant_bins ?? 0}/{cModel?.n_eligible_bins ?? 0} eligible
              bins have a calibration-gap 95% CI (cluster bootstrap on game_id)
              that excludes 0; the rest are within noise.
              {cModel?.brier != null && <> Model Brier {cModel.brier.toFixed(4)}.</>}
              {bAll?.bss_model_vs_clim != null && (
                <> Brier skill vs climatology {bAll.bss_model_vs_clim.toFixed(3)}
                  {bAll.bss_model_vs_market != null && (
                    <>, vs market {bAll.bss_model_vs_market.toFixed(3)} (at or below 0 -- the model does not beat the market Brier; that null is the point)</>
                  )}.</>
              )}
              {" "}Source: calibration_stability.json + brier_skill_scores.json.
            </div>
          </Panel>
        </>
      )}
    </main>
  );
}
