// app/lab/microstructure/page.tsx -- microstructure lab (T4.3).
//
// Descriptive market-microstructure instruments read from staged showcase JSON
// at build time (the /receipts on-disk pattern -- no client fetch, no /api).
// Every instrument is STANDARD_INSTRUMENT + edge_claimed:false: these measure
// forecaster agreement, entropy decay, tick cadence and disagreement; none
// claim an edge, ROI, or dollar result. Missing artifact -> VALIDATION_PENDING
// chip via receiptChip(null), never a fabricated number. ASCII only.

import { LabShell } from "@/components/lab/LabShell";
import { InstrumentPanel } from "@/components/lab/InstrumentPanel";
import { GapEntropyChart, type GapEntropyPoint } from "@/components/charts/GapEntropyChart";
import { Num } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import { loadArtifact, receiptChip } from "@/lib/showcase.server";

export const metadata = {
  title: "Microstructure lab",
  description:
    "Descriptive tick-level instruments -- gap/entropy over game-time, tick " +
    "cadence, market disagreement. STANDARD_INSTRUMENT, edge_claimed:false throughout.",
};

// market_convergence.checkpoints[sport] is a { checkpoint: {mean_gap, ...} } map.
type ConvCheckpoint = {
  mean_gap?: number;
  mean_entropy_market_bits?: number;
};

function convSeries(art: Record<string, unknown> | null, sport: string): GapEntropyPoint[] {
  const checkpoints = (art?.checkpoints as Record<string, Record<string, ConvCheckpoint>> | undefined)?.[sport];
  if (!checkpoints) return [];
  return Object.entries(checkpoints)
    .map(([k, v]) => ({
      t: Number(k),
      gap: v.mean_gap ?? 0,
      entropy: v.mean_entropy_market_bits ?? 0,
    }))
    .filter((p) => Number.isFinite(p.t));
}

type DisagreeBucket = {
  bucket: string;
  n: number;
  model_brier: number;
  market_brier: number;
  model_closer_rate: number;
};

export default function MicrostructurePage() {
  const conv = loadArtifact("market_convergence") as Record<string, unknown> | null;
  const disagree = loadArtifact("market_disagreement_profile") as Record<string, unknown> | null;
  const convNovelty = ((conv?.novelty as { verdict?: string } | undefined)?.verdict) ?? "STANDARD_INSTRUMENT";
  const disagreeRows = (disagree?.sports as Record<string, DisagreeBucket[]> | undefined)?.mlb ?? [];

  // Compact roster: one honest headline stat + receipt chip per remaining instrument.
  const roster = ["tick_microstructure", "info_arrival_curve", "residual_autocorrelation", "micro_absorption", "micro_closing_decay"].map(
    (id) => {
      const art = loadArtifact(id) as Record<string, unknown> | null;
      return { id, art, chip: receiptChip(art) };
    }
  );

  return (
    <LabShell active="microstructure">
      <p className="mb-6 max-w-[68ch] text-sm leading-relaxed text-faint">
        Outcome-free descriptive instruments over the joined in-game corpora. They
        track whether the two forecasters agree more and whether predictive
        uncertainty collapses as a game resolves. Entropy decay late in a game is
        expected as probabilities move toward 0 or 1; it is not a finding. Every
        panel is a textbook measure applied to our corpus, not a new method, and
        claims no edge.
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        <InstrumentPanel
          title="Gap + entropy over game-time (MLB)"
          novelty={convNovelty}
          asOf={(conv?.generated_at as string) ?? null}
          receipt={receiptChip(conv)}
          caption="Mean |model-market| probability gap (amber) and mean market Bernoulli entropy in bits (blue) per inning checkpoint, MLB. Source: market_convergence.json."
        >
          <GapEntropyChart series={convSeries(conv, "mlb")} />
        </InstrumentPanel>

        <InstrumentPanel
          title="Gap + entropy over game-time (soccer)"
          novelty={convNovelty}
          asOf={(conv?.generated_at as string) ?? null}
          receipt={receiptChip(conv)}
          caption="Same instrument on international soccer, per 5-minute checkpoint. Market entropy falls from 0.82 to 0.44 bits as matches resolve. Source: market_convergence.json."
        >
          <GapEntropyChart series={convSeries(conv, "soccer_intl")} />
        </InstrumentPanel>
      </div>

      <div className="mt-4">
        <InstrumentPanel
          title="Market-disagreement profile (MLB)"
          novelty="STANDARD_INSTRUMENT"
          receipt={receiptChip(disagree)}
          caption="Rows bucketed by |model-market| prob gap; per-bucket Brier and the share where our model lands closer to the outcome. Where the two forecasters disagree most (>=.10), the market is sharper (model_closer_rate 0.38) -- shown, not hidden. Source: market_disagreement_profile.json."
        >
          {disagreeRows.length === 0 ? (
            <p className="text-[11px] text-faint">Not staged on this clone (VALIDATION_PENDING).</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="microlabel px-3 py-1.5">gap bucket</th>
                    <th className="microlabel px-3 py-1.5 text-right">n</th>
                    <th className="microlabel px-3 py-1.5 text-right">model brier</th>
                    <th className="microlabel px-3 py-1.5 text-right">market brier</th>
                    <th className="microlabel px-3 py-1.5 text-right">model closer</th>
                  </tr>
                </thead>
                <tbody>
                  {disagreeRows.map((r) => (
                    <tr key={r.bucket} className="border-b border-border hover:bg-surface-2">
                      <td className="px-3 py-1.5 font-data">{r.bucket}</td>
                      <td className="px-3 py-1.5 text-right"><Num>{r.n}</Num></td>
                      <td className="px-3 py-1.5 text-right font-data tabular">{r.model_brier.toFixed(3)}</td>
                      <td className="px-3 py-1.5 text-right font-data tabular">{r.market_brier.toFixed(3)}</td>
                      <td className="px-3 py-1.5 text-right font-data tabular">{r.model_closer_rate.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </InstrumentPanel>
      </div>

      <div className="mt-4">
        <InstrumentPanel
          title="Other staged instruments"
          novelty="STANDARD_INSTRUMENT"
          caption="Each links to its raw artifact; a VALIDATION_PENDING chip means the file was not staged on this clone."
        >
          <ul className="flex flex-col gap-1.5">
            {roster.map(({ id, art, chip }) => (
              <li key={id} className="flex items-baseline gap-2 text-sm">
                <span className="font-data text-foreground">{id}</span>
                <span className="text-faint">
                  {(art?.method as string) ?? (art?.label as string) ?? "not staged on this clone"}
                </span>
                <span className="ml-auto shrink-0">
                  <ReceiptChip {...chip} />
                </span>
              </li>
            ))}
          </ul>
        </InstrumentPanel>
      </div>
    </LabShell>
  );
}
