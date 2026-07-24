// app/graveyard/page.tsx -- killed signals at full prominence: nulls, REJECTs,
// and non-surviving mechanisms rendered as visibly as anything shipped.
// Static build-time read via showcase.server; no client fetch.

import { loadArtifact, receiptChip } from "@/lib/showcase.server";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";

export const metadata = {
  title: "Graveyard",
  description:
    "Killed signals shown with the same prominence as shipped ones: nulls, " +
    "REJECT verdicts, and mechanisms that did not survive replication.",
};

type HonestySport = {
  sport: string;
  source: string;
  total: number;
  confirmed: number;
  null: number;
  not_testable: number;
  failed_replication: number;
  other: number;
};
type HonestyExhibit = {
  generated_at?: string | null;
  headline?: string;
  sports?: HonestySport[];
};
type RejectGraveyard = {
  source?: string;
  note?: string;
  full_history_row_count?: number;
  latest_per_signal_graveyard_count?: number;
  reject_row_count?: number;
  history_vs_latest_disclosure?: string;
  verdicts_by_type?: Record<string, number>;
  rejects_by_reason_category?: Record<string, number>;
  history_rows_by_sport?: Record<string, number>;
};
type MechanismSurvival = {
  source?: string;
  note?: string;
  overall?: { n: number; n_testable: number; n_confirmed: number; survival_rate: number };
  by_sport?: Record<string, { n: number; n_testable: number; n_confirmed: number; survival_rate: number }>;
};

function Bar({ share }: { share: number }) {
  return (
    <div className="h-1.5 w-full bg-surface-2">
      <div className="h-full bg-danger" style={{ width: `${Math.round(share * 100)}%` }} />
    </div>
  );
}

export default function GraveyardPage() {
  const honesty = loadArtifact("honesty_exhibit") as HonestyExhibit | null;
  const rejects = loadArtifact("reject_graveyard") as RejectGraveyard | null;
  const survival = loadArtifact("mechanism_survival") as MechanismSurvival | null;

  const honestyChip = receiptChip(honesty as never);
  const rejectChip = receiptChip(rejects as never);
  const survivalChip = receiptChip(survival as never);

  const verdictRows = Object.entries(rejects?.verdicts_by_type ?? {}).sort((a, b) => b[1] - a[1]);
  const reasonRows = Object.entries(rejects?.rejects_by_reason_category ?? {}).sort((a, b) => b[1] - a[1]);
  const reasonMax = reasonRows.length ? reasonRows[0][1] : 1;

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header>
        <p className="microlabel">honesty / graveyard</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          The graveyard
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {honesty?.headline ??
            "Every killed signal is recorded here at the same size as anything shipped. A REJECT or NULL is honest market-efficiency evidence, not a failure."}
        </p>
      </header>

      <Panel>
        <PanelHead title="nulls by sport (validation ledgers)" asOf={honesty?.generated_at ?? null} right={<ReceiptChip {...honestyChip} />} />
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="microlabel px-3 py-1.5">sport</th>
                <th className="microlabel px-3 py-1.5 text-right">total</th>
                <th className="microlabel px-3 py-1.5 text-right">confirmed</th>
                <th className="microlabel px-3 py-1.5 text-right">null</th>
                <th className="microlabel px-3 py-1.5 text-right">not testable</th>
                <th className="microlabel px-3 py-1.5 text-right">failed replication</th>
              </tr>
            </thead>
            <tbody>
              {(honesty?.sports ?? []).map((s) => (
                <tr key={s.sport} className="border-b border-border hover:bg-surface-2">
                  <td className="px-3 py-1.5 font-data">{s.sport}</td>
                  <td className="px-3 py-1.5 text-right"><Num>{s.total}</Num></td>
                  <td className="px-3 py-1.5 text-right text-up"><Num>{s.confirmed}</Num></td>
                  <td className="px-3 py-1.5 text-right text-down"><Num>{s.null}</Num></td>
                  <td className="px-3 py-1.5 text-right text-faint"><Num>{s.not_testable}</Num></td>
                  <td className="px-3 py-1.5 text-right text-danger"><Num>{s.failed_replication}</Num></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Panel>
          <PanelHead title="reject ledger" right={<ReceiptChip {...rejectChip} />} />
          <div className="p-3 text-sm">
            <div className="flex items-baseline gap-2">
              <span className="text-lg font-semibold text-foreground"><Num>{rejects?.reject_row_count ?? "--"}</Num></span>
              <span className="text-muted-foreground">REJECT rows</span>
            </div>
            <div className="mt-1 font-data text-[11px] text-faint">
              <Num>{rejects?.full_history_row_count ?? "--"}</Num> total verdict rows across all reruns -- <Num>{rejects?.latest_per_signal_graveyard_count ?? "--"}</Num> distinct (sport, signal) currently on a REJECT-family verdict
            </div>
            {rejects?.history_vs_latest_disclosure && (
              <p className="mt-2 text-[11px] leading-relaxed text-faint">{rejects.history_vs_latest_disclosure}</p>
            )}
          </div>
        </Panel>
        <Panel>
          <PanelHead title="mechanism survival (testable hypotheses)" right={<ReceiptChip {...survivalChip} />} />
          <div className="p-3 text-sm">
            <div className="flex items-baseline gap-2">
              <span className="text-lg font-semibold text-foreground">
                {survival?.overall ? `${(survival.overall.survival_rate * 100).toFixed(1)}%` : "--"}
              </span>
              <span className="text-muted-foreground">survived (confirmed / testable)</span>
            </div>
            <div className="mt-1 font-data text-[11px] text-faint">
              <Num>{survival?.overall?.n_confirmed ?? "--"}</Num> confirmed of <Num>{survival?.overall?.n_testable ?? "--"}</Num> testable, <Num>{survival?.overall?.n ?? "--"}</Num> total hypotheses
            </div>
            {survival?.note && <p className="mt-2 text-[11px] leading-relaxed text-faint">{survival.note}</p>}
          </div>
        </Panel>
      </div>

      <Panel>
        <PanelHead title="verdicts by type (full history)" />
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <tbody>
              {verdictRows.map(([verdict, count]) => (
                <tr key={verdict} className="border-b border-border">
                  <td className="px-3 py-1.5 font-mono text-[11px] font-bold text-foreground">{verdict}</td>
                  <td className="px-3 py-1.5 text-right"><Num>{count}</Num></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel>
        <PanelHead title="reject reason categories" />
        <div className="flex flex-col gap-2 p-3">
          {reasonRows.map(([reason, count]) => (
            <div key={reason} className="grid grid-cols-[10rem_1fr_3rem] items-center gap-3 text-sm">
              <span className="truncate font-data text-[11px] text-muted-foreground">{reason}</span>
              <Bar share={count / reasonMax} />
              <span className="text-right"><Num>{count}</Num></span>
            </div>
          ))}
        </div>
      </Panel>

      {survival?.by_sport && (
        <Panel>
          <PanelHead title="survival rate by sport" />
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="microlabel px-3 py-1.5">sport</th>
                  <th className="microlabel px-3 py-1.5 text-right">n</th>
                  <th className="microlabel px-3 py-1.5 text-right">testable</th>
                  <th className="microlabel px-3 py-1.5 text-right">confirmed</th>
                  <th className="microlabel px-3 py-1.5 text-right">survival</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(survival.by_sport).map(([sport, s]) => (
                  <tr key={sport} className="border-b border-border hover:bg-surface-2">
                    <td className="px-3 py-1.5 font-data">{sport}</td>
                    <td className="px-3 py-1.5 text-right"><Num>{s.n}</Num></td>
                    <td className="px-3 py-1.5 text-right"><Num>{s.n_testable}</Num></td>
                    <td className="px-3 py-1.5 text-right text-up"><Num>{s.n_confirmed}</Num></td>
                    <td className="px-3 py-1.5 text-right"><Num>{(s.survival_rate * 100).toFixed(1)}%</Num></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </main>
  );
}
