// app/lab/counterfactual/page.tsx -- the counterfactual explorer (T4.2).
//
// Server component: reads state_conditioned_calibration.json at build time and
// hands pre-computed MLB in-game cells to the one client island (StateCellGrid)
// for click-to-inspect. No sim, no fetch. This surface measures calibration
// error only (edge_claimed:false); it makes no dollar/ROI/edge claim. The
// honest headline: in aggregate the MARKET is the better-calibrated forecaster
// here (lower n-weighted ECE) and the worst model cells are shown as the
// improvement backlog, not buried. Mirrors mockups/counterfactual.html. ASCII.

import { loadArtifact, receiptChip } from "@/lib/showcase.server";
import { LabShell } from "@/components/lab/LabShell";
import { StateCellGrid } from "@/components/lab/StateCellGrid";
import type { Cell, CellRow } from "@/components/lab/CellDetail";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";

export const metadata = {
  title: "Counterfactual explorer",
  description:
    "State-conditioned calibration: model vs. market error per game-state cell. " +
    "Calibration only, no edge claimed; the market is better-calibrated in aggregate.",
};

const ARTIFACT_ID = "state_conditioned_calibration";
const SOURCE_PATH =
  "scripts/platformkit/analytics_showcase/out/state_conditioned_calibration.json";

// MLB axes, in mockup order (high prob band on top, game-time left->right). We
// render MLB only: it is the sport with graded model+market cells across a full
// grid in this artifact.
const TIMES = ["early(inn1-3)", "mid(inn4-6)", "late(inn7+)"];
const TIME_LABELS = ["early", "mid", "late"];
const PROBS = [".8-1", ".6-.8", ".4-.6", ".2-.4", "0-.2"];

type Bucket = {
  time_bucket: string;
  prob_bucket: string;
  source: "model" | "market";
  n: number;
  mean_p: number;
  mean_y: number;
  calibration_error: number;
};

function toRow(b: Bucket): CellRow {
  return { n: b.n, meanP: b.mean_p, meanY: b.mean_y, calErr: b.calibration_error };
}

const d4 = (v: number) => v.toFixed(4);
const comma = (n: number) => n.toLocaleString("en-US");

export default function CounterfactualPage() {
  const art = loadArtifact(ARTIFACT_ID);
  const mlb = (art?.sports as Record<string, unknown> | undefined)?.mlb as
    | { buckets?: Bucket[]; model_ece_n_weighted?: number; market_ece_n_weighted?: number }
    | undefined;
  const buckets = mlb?.buckets ?? [];

  // Fold buckets into (time|prob) cells carrying model + market rows.
  const map = new Map<string, Cell>();
  for (const b of buckets) {
    const key = `${b.time_bucket}|${b.prob_bucket}`;
    const cell =
      map.get(key) ??
      {
        time: b.time_bucket,
        timeLabel: TIME_LABELS[TIMES.indexOf(b.time_bucket)] ?? b.time_bucket,
        prob: b.prob_bucket,
        model: null,
        market: null,
      };
    if (b.source === "model") cell.model = toRow(b);
    else cell.market = toRow(b);
    map.set(key, cell);
  }
  const cells = [...map.values()];

  // Worst model cells = the improvement backlog. Market cal err shown alongside.
  const worst = cells
    .filter((c) => c.model)
    .sort((a, b) => (b.model!.calErr - a.model!.calErr))
    .slice(0, 4);

  const modelEce = mlb?.model_ece_n_weighted ?? null;
  const marketEce = mlb?.market_ece_n_weighted ?? null;

  const chip = {
    ...receiptChip(art),
    sourceArtifact: SOURCE_PATH,
    verdict: "MARKET_SHARPER_PROVISIONAL",
  };

  // Pick the highest-error model cell to open on.
  const initial = worst[0] ? `${worst[0].time}|${worst[0].prob}` : `${TIMES[2]}|${PROBS[0]}`;

  return (
    <LabShell active="counterfactual">
      <div className="mb-6 max-w-[68ch]">
        <h2 className="text-lg font-semibold text-foreground">Counterfactual explorer</h2>
        <p className="mt-1 text-sm leading-relaxed text-faint">
          Pick a game-state cell -- probability band x game-time -- and see how well
          the model was calibrated there, next to the market. Reads committed cells;
          runs no new simulation.
        </p>
        <span className="mt-3 inline-flex items-center gap-2 border border-border px-2.5 py-1 text-xs text-faint">
          MEASURE <b className="text-foreground">calibration error only</b>
          <span className="text-border">|</span>
          <b className="text-foreground">edge_claimed: false</b> on this artifact
        </span>
      </div>

      <p className="microlabel mb-2 text-faint">State-conditioned calibration grid (MLB)</p>
      <Panel>
        <PanelHead
          title="Model calibration error per (band x game-time) cell -- click a cell"
          right={<span className="microlabel text-faint">mlb in-game</span>}
        />
        <div className="p-3.5">
          {cells.length > 0 ? (
            <StateCellGrid
              times={TIMES}
              timeLabels={TIME_LABELS}
              probs={PROBS}
              cells={cells}
              initialSelected={initial}
              chip={chip}
            />
          ) : (
            <p className="p-4 text-sm text-faint">
              state_conditioned_calibration.json was not staged on this clone, so the
              grid is empty. Regenerate the showcase artifacts to populate it.
            </p>
          )}
        </div>
      </Panel>

      <p className="microlabel mb-2 mt-8 text-faint">Worst buckets = the improvement backlog</p>
      <Panel>
        <PanelHead
          title="Ranked-worst model cells -- shown as a feature, not hidden"
          right={<span className="microlabel text-faint">mlb / n-weighted ECE</span>}
        />
        <div className="m-3 border-l-2 border-primary bg-card px-3.5 py-3 text-sm leading-relaxed text-faint">
          Straight from the artifact story:{" "}
          <b className="text-primary">
            ranked_worst_buckets is where the model is furthest from outcomes
            relative to the market -- the improvement backlog.
          </b>{" "}
          These are the cells to fix next, not numbers to bury.
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-left">
                <th className="microlabel px-3 py-1.5">cell</th>
                <th className="microlabel px-3 py-1.5 text-right">model n</th>
                <th className="microlabel px-3 py-1.5 text-right">model cal err</th>
                <th className="microlabel px-3 py-1.5 text-right">market cal err</th>
                <th className="microlabel px-3 py-1.5">read</th>
              </tr>
            </thead>
            <tbody>
              {worst.map((c) => {
                const trails = c.market ? c.model!.calErr > c.market.calErr : true;
                return (
                  <tr key={`${c.time}|${c.prob}`} className="border-t border-border hover:bg-surface-2">
                    <td className="px-3 py-1.5 font-data">{`${c.timeLabel}(${c.time.replace(/^[a-z]+/, "")}) x ${c.prob}`}</td>
                    <td className="px-3 py-1.5 text-right font-data tabular-nums">
                      <Num>{comma(c.model!.n)}</Num>
                    </td>
                    <td className="px-3 py-1.5 text-right font-data tabular-nums text-danger">{d4(c.model!.calErr)}</td>
                    <td className="px-3 py-1.5 text-right font-data tabular-nums text-s-market">
                      {c.market ? d4(c.market.calErr) : "n/a"}
                    </td>
                    <td className="px-3 py-1.5">
                      <span className="inline-block border border-danger/50 px-1.5 py-px font-data text-[10.5px] text-danger">
                        {trails ? "MODEL TRAILS" : "MODEL LEADS"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {modelEce != null && marketEce != null && (
          <>
            <div className="flex items-center justify-between border-t border-border px-3 py-2">
              <span className="microlabel text-faint">Aggregate, n-weighted across all mlb cells</span>
              <span className="font-data text-[13px]">
                model ECE <span className="text-s-model tabular-nums">{modelEce}</span>
                <ReceiptChip {...chip} verdict={null} />
                <span className="ml-3">vs market ECE</span>{" "}
                <span className="text-s-market tabular-nums">{marketEce}</span>
                <ReceiptChip {...chip} verdict={null} />
              </span>
            </div>
            <div className="m-3 border-l-2 border-primary bg-card px-3.5 py-3 text-sm leading-relaxed text-faint">
              Read this straight: in aggregate the{" "}
              <b className="text-primary">market is the better-calibrated forecaster here</b> --
              its n-weighted ECE ({marketEce}) is lower than the model's ({modelEce}). We are
              not spinning that. The value of this lab is the transparency about which cells the
              model trails in, not a claim that it wins.
            </div>
          </>
        )}
      </Panel>

      <p className="mt-8 border-t border-border pt-5 text-xs leading-relaxed text-faint">
        Every figure traces to a committed JSON under{" "}
        <span className="font-data">scripts/platformkit/analytics_showcase/out/</span>. Grid cells
        read verbatim from <span className="font-data">state_conditioned_calibration.json</span>.
        No ROI, profit, or betting-edge claim appears on this page -- calibration error only.
      </p>
    </LabShell>
  );
}
