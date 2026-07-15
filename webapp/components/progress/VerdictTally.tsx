"use client";

// VerdictTally -- the aggregate gate-verdict tally across all sports
// (n_ship / n_reject / n_insufficient), with the lone calibration SHIPs (the
// "corners" survivor in soccer + the tennis survivor) highlighted as the only
// surviving signals. A REJECT is the dominant outcome BY DESIGN -- markets are
// efficient, and a recorded reject is a SUCCESS. SHIP is CALIBRATION only,
// vs_close UNPROVEN -- never a market/$ edge. NO $ field anywhere.

import { Panel, Badge } from "@/components/p6/Primitives";
import { InfoTip, SignalVerdictBadge } from "@/components/depth";
import type { ProgressPerSport } from "@/lib/api";

function Stat({
  label,
  value,
  tone,
  tip,
}: {
  label: string;
  value: number;
  tone: "green" | "slate" | "amber";
  tip: string;
}) {
  const ring =
    tone === "green"
      ? "border-tier-a/40"
      : tone === "amber"
        ? "border-amber-900/50"
        : "border-slate-800";
  return (
    <div className={`rounded-lg border ${ring} bg-bg-panel/40 px-3 py-2`}>
      <div className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
        <InfoTip text={tip} ariaLabel={`what is ${label}?`} />
      </div>
      <div className="mt-0.5 font-mono text-lg tabular-nums text-foreground">
        {value}
      </div>
    </div>
  );
}

export function VerdictTally({
  perSport,
}: {
  perSport: Record<string, ProgressPerSport> | null;
}) {
  const sports = perSport ? Object.entries(perSport) : [];
  const totals = sports.reduce(
    (acc, [, s]) => {
      acc.ship += s.n_ship ?? 0;
      acc.reject += s.n_reject ?? 0;
      acc.insufficient += s.n_insufficient ?? 0;
      return acc;
    },
    { ship: 0, reject: 0, insufficient: 0 },
  );
  // The sports carrying the lone calibration SHIP survivors.
  const shippers = sports.filter(([, s]) => (s.n_ship ?? 0) > 0).map(([sp]) => sp);

  return (
    <Panel
      title="gate-verdict tally (calibration, not $)"
      right={
        <span className="inline-flex items-center gap-1.5">
          <Badge tone="slate">
            {totals.ship + totals.reject + totals.insufficient} verdicts
          </Badge>
          <InfoTip
            text="Every signal run through the leak-free gate lands here. REJECT dominating is the HONEST outcome -- the market already prices the signal. A REJECT is a SUCCESS. SHIP means a CALIBRATION survivor only (vs_close UNPROVEN), never a market or $ edge."
            ariaLabel="what is the verdict tally?"
          />
        </span>
      }
    >
      {sports.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          no verdicts recorded yet -- honest empty, never a fabricated tally.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-3 gap-3">
            <Stat
              label="ship"
              value={totals.ship}
              tone="green"
              tip="Calibration survivors only -- they pass the leak-free gate but vs_close is UNPROVEN. NOT a market or $ edge."
            />
            <Stat
              label="reject"
              value={totals.reject}
              tone="slate"
              tip="The dominant, HONEST outcome -- the market already prices the signal. A recorded REJECT is a SUCCESS, not a failure."
            />
            <Stat
              label="insufficient"
              value={totals.insufficient}
              tone="amber"
              tip="Not enough settled data to decide yet -- an honest empty verdict, never forced to a result."
            />
          </div>
          <div className="rounded-lg border border-tier-a/30 bg-tier-a/5 p-3">
            <div className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold text-foreground">
              surviving signals
              <InfoTip
                text="The only signals that cleared the leak-free gate. Each is a CALIBRATION improvement (e.g. soccer corners), not a profit edge -- vs_close stays UNPROVEN."
                ariaLabel="what are the surviving signals?"
              />
            </div>
            {totals.ship === 0 ? (
              <p className="text-[11px] text-muted-foreground">
                none surviving -- the honest state when the close is efficient.
              </p>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                {shippers.map((sp) => (
                  <span key={sp} className="inline-flex items-center gap-1.5">
                    <span className="font-mono text-[11px] uppercase text-foreground">
                      {sp}
                    </span>
                    <SignalVerdictBadge
                      verdict="SHIP"
                      stat="leak-free calibration survivor"
                    />
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}
