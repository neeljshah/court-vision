"use client";

import { useEffect, useState } from "react";
import { api, isUnavailable, type InGameGates, type GateSport } from "@/lib/p5api";
import { Panel, Unavailable, Badge } from "./Primitives";
import { Dot } from "@/components/ui/terminal";
import { cn } from "@/lib/utils";

// GateMatrix -- 4-sport in-game calibration gate verdict matrix.
// Reads GET /api/ingame/gates (added by this session).
// Shows: sport | verdict | vs_close | CALIBRATION label.
// REPLICATED/SHIP = model passed OOS calibration gate.
// REJECT = gate failed; vs_close is always UNPROVEN (no in-play odds).
// No $ claim; this is CALIBRATION observability only.

const SPORT_ORDER = ["nba", "mlb", "soccer", "tennis"] as const;

export function GateMatrix() {
  const [data, setData] = useState<InGameGates | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    api.ingameGates(ac.signal).then((d) => {
      if (isUnavailable(d)) {
        setErr((d as {reason?: string}).reason || "gate data unavailable");
      } else {
        setData(d as InGameGates);
        setErr(null);
      }
    });
    return () => ac.abort();
  }, []);

  const allGreen =
    data?.sports.every((s) =>
      s.verdict === "REPLICATED" || s.verdict === "SHIP_PRIOR_LAYER",
    ) ?? false;

  return (
    <Panel
      title="4-sport gate matrix (calibration)"
      right={
        data ? (
          <Badge tone={allGreen ? "green" : "amber"}>
            {allGreen ? "all calibrated" : "mixed"}
          </Badge>
        ) : null
      }
    >
      {err ? (
        <Unavailable reason={err} />
      ) : !data ? (
        <p className="text-sm text-muted-foreground">loading...</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="microlabel py-1.5 px-3">Sport</th>
                  <th className="microlabel py-1.5 px-3">Verdict</th>
                  <th className="microlabel py-1.5 px-3">vs close</th>
                  <th className="microlabel py-1.5 px-3">Label</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {SPORT_ORDER.map((sport) => {
                  const row = data.sports.find((s) => s.sport === sport);
                  return <GateRow key={sport} sport={sport} row={row || null} />;
                })}
              </tbody>
            </table>
          </div>

          {data.honest_note ? (
            <p className="mt-3 text-[11px] text-faint">{data.honest_note}</p>
          ) : null}
        </>
      )}
    </Panel>
  );
}

function GateRow({
  sport,
  row,
}: {
  sport: string;
  row: GateSport | null;
}) {
  if (!row) {
    return (
      <tr className="text-muted-foreground">
        <td className="py-1.5 px-3 font-mono text-xs uppercase">{sport}</td>
        <td colSpan={3} className="py-1.5 px-3 text-[10px] text-faint">
          no gate data
        </td>
      </tr>
    );
  }

  const verdict = row.verdict;
  const passed =
    verdict === "REPLICATED" ||
    verdict === "SHIP_PRIOR_LAYER" ||
    verdict === "SHIP";
  const rejected = verdict === "REJECT";

  return (
    <tr className="text-foreground hover:bg-surface-2">
      <td className="py-1.5 px-3 font-mono text-xs uppercase font-semibold text-foreground">
        {sport}
      </td>
      <td className="py-1.5 px-3">
        <span className="inline-flex items-center gap-1.5">
          <Dot state={passed ? "ok" : rejected ? "warn" : "warn"} />
          <VerdictBadge verdict={verdict} passed={passed} rejected={rejected} />
        </span>
      </td>
      <td className="py-1.5 px-3">
        <span className="font-mono text-[10px] text-amber-600/80">
          {row.vs_close || "UNPROVEN"}
        </span>
      </td>
      <td className="py-1.5 px-3">
        <span className="font-mono text-[10px] text-faint">
          {row.honest_label || "CALIBRATION"}
        </span>
      </td>
    </tr>
  );
}

function VerdictBadge({
  verdict,
  passed,
  rejected,
}: {
  verdict: string | null;
  passed: boolean;
  rejected: boolean;
}) {
  if (!verdict) {
    return (
      <span className="inline-flex rounded border border-slate-700 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
        n/a
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex rounded border px-1.5 py-0.5 text-[10px] font-mono uppercase",
        passed
          ? "border-tier-a/40 bg-tier-a/10 text-tier-a"
          : rejected
            ? "border-amber-900/50 bg-amber-950/30 text-amber-400"
            : "border-slate-700 bg-slate-800 text-slate-400",
      )}
    >
      {verdict}
    </span>
  );
}
