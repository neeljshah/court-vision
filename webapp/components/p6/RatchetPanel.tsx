"use client";

import { useEffect, useState } from "react";
import { api, isUnavailable, type ImproveStatus } from "@/lib/p5api";
import { Panel, Unavailable, Badge } from "./Primitives";

// RatchetPanel -- self-improvement status from /api/improve/status. Surfaces
// the recalibration ratchet FSM state + which calibration kinds have a promoted
// version. No $ claim: the ratchet only ships when EVERY gate passes.
export function RatchetPanel() {
  const [data, setData] = useState<ImproveStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    api.improve(ac.signal).then((d) => {
      if (isUnavailable(d)) setErr(d.reason || "improve status unavailable");
      else setData(d as ImproveStatus);
    });
    return () => ac.abort();
  }, []);

  if (err) {
    return (
      <Panel title="Self-improve ratchet">
        <Unavailable reason={err} />
      </Panel>
    );
  }
  if (!data) {
    return (
      <Panel title="Self-improve ratchet">
        <p className="text-sm text-slate-500">loading…</p>
      </Panel>
    );
  }

  const state = data.ratchet?.state || "IDLE";
  const decision = data.ratchet?.last_decision;
  const tone =
    decision === "SHIP" ? "green" : decision === "REJECT" ? "amber" : "slate";

  return (
    <Panel
      title="Self-improve ratchet"
      right={<Badge tone="slate">{state}</Badge>}
    >
      <div className="flex items-center gap-2 text-sm">
        <span className="text-slate-400">last decision</span>
        <Badge tone={tone as "green" | "amber" | "slate"}>
          {decision || "none"}
        </Badge>
        {data.ratchet?.shipped_version != null ? (
          <span className="font-mono text-xs text-slate-500">
            v{data.ratchet.shipped_version}
          </span>
        ) : null}
      </div>

      <div className="mt-3">
        <div className="text-[10px] uppercase tracking-wide text-slate-500">
          Calibration kinds ({data.n_promoted ?? 0}/{data.n_kinds ?? data.kinds.length} promoted)
        </div>
        <ul className="mt-2 space-y-1">
          {data.kinds.map((k) => (
            <li
              key={k.kind}
              className="flex items-center justify-between font-mono text-xs"
            >
              <span className="text-slate-300">{k.kind}</span>
              <span className="text-slate-500">
                {k.current_version != null
                  ? `current v${k.current_version}`
                  : "no current"}
                {k.versions.length ? ` · ${k.versions.length} ver` : ""}
              </span>
            </li>
          ))}
        </ul>
      </div>
      {data.honest_note ? (
        <p className="mt-3 text-[11px] text-slate-600">{data.honest_note}</p>
      ) : null}
    </Panel>
  );
}
