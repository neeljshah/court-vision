"use client";

import { useEffect, useState } from "react";
import { api, isUnavailable, type InGameGates, type GateSport } from "@/lib/p5api";
import { Panel, Unavailable, Badge } from "./Primitives";
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
        <p className="text-sm text-slate-500">loading...</p>
      ) : (
        <>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
                <th className="pb-2 font-medium">Sport</th>
                <th className="pb-2 font-medium">Verdict</th>
                <th className="pb-2 font-medium">vs close</th>
                <th className="pb-2 font-medium">Label</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {SPORT_ORDER.map((sport) => {
                const row = data.sports.find((s) => s.sport === sport);
                return <GateRow key={sport} sport={sport} row={row || null} />;
              })}
            </tbody>
          </table>

          {data.honest_note ? (
            <p className="mt-3 text-[11px] text-slate-600">{data.honest_note}</p>
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
      <tr className="text-slate-500">
        <td className="py-2 font-mono text-xs uppercase">{sport}</td>
        <td colSpan={3} className="py-2 text-[10px] text-slate-600">
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
    <tr className="text-slate-300">
      <td className="py-2 font-mono text-xs uppercase font-semibold text-slate-200">
        {sport}
      </td>
      <td className="py-2">
        <VerdictBadge verdict={verdict} passed={passed} rejected={rejected} />
      </td>
      <td className="py-2">
        <span className="font-mono text-[10px] text-amber-600/80">
          {row.vs_close || "UNPROVEN"}
        </span>
      </td>
      <td className="py-2">
        <span className="font-mono text-[10px] text-slate-600">
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
      <span className="inline-flex rounded border border-slate-700 px-1.5 py-0.5 text-[10px] font-mono text-slate-500">
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
