// HonestFindings.tsx -- the recorded honest findings from the deep-data gates.
//
// Surfaces the on-disk verdict snapshot (gateVerdicts.ts, transcribed from
// data/frontend/funnel/*.json): the depth plateau (deeper data rejects for the
// close across every sport/tier), the ONE confirmed soccer corners CALIBRATION
// survivor (passed all controls; vs_close UNPROVEN), and the parity-green frame.
//
// HONESTY RAILS: exactly one SHIP and it is CALIBRATION not edge; every other
// layer is a recorded REJECT/BLOCKED (a success). NO $ field; no edge claimed.

import { GATE_VERDICTS, SURVIVOR, countByVerdict } from "./gateVerdicts";
import type { Verdict } from "./gateVerdicts";
import { SignalVerdictBadge } from "@/components/depth";
import type { SignalVerdict } from "@/components/depth";
import { Panel, PanelHead } from "@/components/ui/terminal";

// Map the on-disk verdict snapshot onto the shared depth SignalVerdict vocab so
// the page reuses the canonical badge (SHIP always reads "calibration-only,
// vs_close UNPROVEN"; BLOCKED is the Tier-3 acquisition gate).
function toSignalVerdict(v: Verdict): SignalVerdict {
  return v === "BLOCKED" ? "TIER3_BLOCKED" : v;
}

function PlateauHeadline() {
  const rejects = countByVerdict("REJECT");
  const blocked = countByVerdict("BLOCKED");
  return (
    <Panel>
      <PanelHead title="the depth plateau (the honest finding)" />
      <p className="p-4 text-xs leading-relaxed text-muted-foreground">
        Adding deeper data does not beat the devigged close. Across every sport and
        tier, the next layer of depth rejects under the gate:{" "}
        <span className="font-semibold text-foreground font-data">{rejects} recorded REJECTs</span>{" "}
        and <span className="font-semibold text-foreground font-data">{blocked} TIER-3 BLOCKED</span>{" "}
        (data off-disk), against{" "}
        <span className="font-semibold text-tier-a font-data">1 CALIBRATION survivor</span>. The
        cross-sport meta-finding -- coarse in-game micro-state rejects vs (margin, time)
        -- is confirmed in NBA, MLB and soccer. Recording these rejects IS the deliverable.
      </p>
    </Panel>
  );
}

function SurvivorCard() {
  return (
    <Panel className="border-tier-a/60">
      <PanelHead
        title="soccer corners -- CALIBRATION, not a market edge"
        right={
          <SignalVerdictBadge
            verdict="SHIP"
            stat="diff_corners_asof -- clustered-DM p ~= 0.0015, replicated E0/E1 + SP1/I1"
          />
        }
      />
      <div className="p-4">
        <p className="text-xs leading-relaxed text-muted-foreground">
          One signal cleared all six controls: the as-of corners differential
          (<span className="font-data text-foreground/80">diff_corners_asof</span>) improved
          held-out home-win Brier in BOTH disjoint league pairs (E0/E1 and SP1/I1),
          clustered-DM p ~= 0.0015, the base was skillful, and the planted-null rejected.
          It is kept as a PROPOSAL / scouting prior and is never force-fed into a prediction.
        </p>
        <dl className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            { k: "deciding stat", v: "diff_corners_asof" },
            { k: "clustered-DM p", v: "~= 0.0015" },
            { k: "replicated on", v: "E0/E1 + SP1/I1" },
            { k: "planted-null", v: "rejected (good)" },
          ].map((s) => (
            <div key={s.k} className="border border-border bg-surface-2 px-2 py-1.5">
              <dt className="microlabel">{s.k}</dt>
              <dd className="m-0 mt-0.5 font-data text-[11px] text-foreground">{s.v}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 border border-warning/40 bg-warning/5 px-2.5 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
          <span className="font-semibold uppercase tracking-wider text-warning">vs_close: </span>
          {SURVIVOR.vsClose}
        </p>
      </div>
    </Panel>
  );
}

function VerdictTable() {
  return (
    <Panel>
      <PanelHead title="gate verdicts by sport" />
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[11px]">
          <thead>
            <tr>
              <th className="microlabel px-3 py-1.5">sport</th>
              <th className="microlabel px-3 py-1.5">deep-data layer gated</th>
              <th className="microlabel px-3 py-1.5">verdict</th>
            </tr>
          </thead>
          <tbody>
            {GATE_VERDICTS.map((g) => (
              <tr key={g.layer} className="border-t border-border align-top hover:bg-surface-2">
                <td className="px-3 py-1.5 font-data uppercase text-muted-foreground">{g.sport}</td>
                <td className="px-3 py-1.5">
                  <div className="text-foreground">{g.what}</div>
                  <div className="mt-0.5 text-muted-foreground">{g.reason}</div>
                </td>
                <td className="px-3 py-1.5">
                  <SignalVerdictBadge
                    verdict={toSignalVerdict(g.verdict)}
                    stat={g.reason}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function HonestFindings() {
  return (
    <section aria-label="honest findings" className="flex flex-col gap-3">
      <h2 className="microlabel">honest findings -- the recorded gate verdicts</h2>
      <PlateauHeadline />
      <SurvivorCard />
      <VerdictTable />
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Source: the on-disk deep-data gate artifacts. Parity across all four sports is
        FULLY GREEN -- see the System page for the live grid.
      </p>
    </section>
  );
}
