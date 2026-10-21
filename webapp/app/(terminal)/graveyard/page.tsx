// app/graveyard/page.tsx -- killed signals at full prominence: nulls, REJECTs,
// and non-surviving mechanisms rendered as visibly as anything shipped.
// Static build-time read via showcase.server; no client fetch.
// The ledger-by-type table mixes two vocabularies: packet verdicts (VerdictLabel) and
// eval-gate ledger statuses (GateStatus, with its legend); neither is dressed as the other.

import { loadArtifact, receiptChip } from "@/lib/showcase.server";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo/meta";
import { GateStatus, GateStatusLegend, VerdictLabel, gateStatusesIn, isGateStatus, isPacketVerdict } from "@/components/evidence";

export const metadata: Metadata = pageMeta("/graveyard/", {
  title: "Graveyard",
  description:
    "Killed signals shown with the same prominence as shipped ones: nulls, " +
    "REJECT verdicts, and mechanisms that did not survive replication.",
});

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

// Plain-word labels; the raw artifact key stays in each header's title attribute.
const SPORT_NAME: Record<string, string> = { nba: "NBA", basketball_nba: "NBA", mlb: "MLB", soccer: "Soccer", tennis: "Tennis", interaction_factory: "Interaction factory (automated pairings)" };
const sportName = (k: string) => SPORT_NAME[k] ?? k;
const PACKET_URL = "https://github.com/neeljshah/court-vision/blob/master/docs/JOB_EVIDENCE_PACKET.md";
const GRAVEYARD_LEAD =
  "Every idea we tested is kept here, including the ones that failed. A 'confirmed' hypothesis held up in its own test; that is not the same as shipping, and none of the 60 candidate signal classes has passed the full market-relative gate.";

type Survival = { n: number; n_testable: number; n_confirmed: number; survival_rate: number };
/** nba and basketball_nba are the same sport under two ledger keys: one row, counts summed. */
function mergeSports(bySport: Record<string, Survival>): [string, Survival][] {
  const out = new Map<string, Survival>();
  for (const [k, v] of Object.entries(bySport)) {
    const name = sportName(k);
    const prev = out.get(name);
    if (!prev) { out.set(name, { ...v }); continue; }
    const m = { n: prev.n + v.n, n_testable: prev.n_testable + v.n_testable, n_confirmed: prev.n_confirmed + v.n_confirmed, survival_rate: 0 };
    m.survival_rate = m.n_testable ? m.n_confirmed / m.n_testable : 0;
    out.set(name, m);
  }
  return [...out.entries()];
}

function Th({ label, raw, right = true }: { label: string; raw: string; right?: boolean }) {
  return <th className={`microlabel px-3 py-1.5${right ? " text-right" : ""}`} title={raw}>{label}</th>;
}

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
  const asOf = [honestyChip.asOf, rejectChip.asOf, survivalChip.asOf].find(Boolean)?.slice(0, 10) ?? null;

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header>
        <p className="microlabel">honesty / graveyard</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          The graveyard
        </h1>
        <p className="mt-1 font-data text-[11px] text-faint" data-role="asof">as of {asOf ?? "not dated in the staged artifacts"}</p>
        <p className="mt-2 text-sm leading-relaxed text-foreground" data-role="lead">
          {GRAVEYARD_LEAD}{" "}
          <a href={PACKET_URL} className="underline">Source: evidence packet, section 4 (corrected 2026-09-03)</a>.
        </p>
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
                <Th label="Sport" raw="sport" right={false} />
                <Th label="Ideas tested" raw="total" />
                <Th label="Held up in its own test" raw="confirmed" />
                <Th label="No effect found" raw="null" />
                <Th label="Could not be tested" raw="not_testable" />
                <Th label="Did not hold up when re-run" raw="failed_replication" />
              </tr>
            </thead>
            <tbody>
              {(honesty?.sports ?? []).map((s) => (
                <tr key={s.sport} className="border-b border-border hover:bg-surface-2">
                  <td className="px-3 py-1.5 font-data" title={s.sport}>{sportName(s.sport)}</td>
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
        <PanelHead title="verdicts and gate statuses by type (full history)" />
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm" data-testid="ledger-by-type">
            <tbody>
              {verdictRows.map(([verdict, count]) => (
                <tr key={verdict} className="border-b border-border">
                  <td className="px-3 py-1.5 font-mono text-[11px] font-bold text-foreground">
                    {isGateStatus(verdict) ? <><GateStatus token={verdict} />{verdict === "SHIP" && (
                      <span data-role="ship-gloss" className="ml-2 font-sans font-normal text-muted-foreground">
                        ({count} = verdict rows across all reruns that passed every gate; not signals shipped)
                      </span>)}</>
                      : isPacketVerdict(verdict) ? <VerdictLabel verdict={verdict} qualifier={false} />
                      : verdict}
                  </td>
                  <td className="px-3 py-1.5 text-right"><Num>{count}</Num></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-3 py-2">
          <GateStatusLegend tokens={gateStatusesIn(verdictRows.map(([verdict]) => verdict))} />
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
                  <Th label="Sport" raw="sport" right={false} />
                  <Th label="Hypotheses" raw="n" />
                  <Th label="Could be tested" raw="n_testable" />
                  <Th label="Held up in its own test" raw="n_confirmed" />
                  <Th label="Share that held up" raw="survival_rate" />
                </tr>
              </thead>
              <tbody>
                {mergeSports(survival.by_sport).map(([sport, s]) => (
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
