// app/lab/page.tsx -- /lab landing: links into the two instrument surfaces.
// T4.2 (counterfactual) and T4.3 (microstructure) land the real content;
// this page just orients and links, using the shared LabShell chrome.
import { LabShell } from "@/components/lab/LabShell";
import { Panel, PanelHead } from "@/components/ui/terminal";
import Link from "next/link";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

export default function LabPage() {
  return (
    <LabShell active={null}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Panel>
          <PanelHead title="Counterfactual explorer" />
          <div className="p-3 text-sm text-faint">
            <p className="mb-3 max-w-[60ch]">
              A score-margin x game-time heatmap of calibration error, per
              state cell, model vs. market vs. realized outcome.
            </p>
            <Link
              href={`${BASE_PATH}/lab/counterfactual`}
              className="microlabel text-primary hover:underline"
            >
              Open counterfactual --&gt;
            </Link>
          </div>
        </Panel>
        <Panel>
          <PanelHead title="Microstructure lab" />
          <div className="p-3 text-sm text-faint">
            <p className="mb-3 max-w-[60ch]">
              Tick-level instruments: gap/entropy over game-time, info
              arrival, market convergence, residual autocorrelation.
            </p>
            <Link
              href={`${BASE_PATH}/lab/microstructure`}
              className="microlabel text-primary hover:underline"
            >
              Open microstructure --&gt;
            </Link>
          </div>
        </Panel>
      </div>
    </LabShell>
  );
}
