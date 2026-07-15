"use client";

import { useEffect, useState } from "react";
import { api, isUnavailable, type ImproveStatus } from "@/lib/p5api";
import { Panel, Unavailable, Badge } from "./Primitives";
import { Num, Dot } from "@/components/ui/terminal";

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
        <p className="text-sm text-muted-foreground">loading…</p>
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
        <span className="text-muted-foreground">last decision</span>
        <span className="inline-flex items-center gap-1.5">
          <Dot state={decision === "SHIP" ? "ok" : decision === "REJECT" ? "warn" : "warn"} />
          <Badge tone={tone as "green" | "amber" | "slate"}>
            {decision || "none"}
          </Badge>
        </span>
        {data.ratchet?.shipped_version != null ? (
          <Num className="text-xs text-muted-foreground">
            v{data.ratchet.shipped_version}
          </Num>
        ) : null}
      </div>

      <div className="mt-3">
        <div className="microlabel">
          Calibration kinds (<Num>{data.n_promoted ?? 0}</Num>/
          <Num>{data.n_kinds ?? data.kinds.length}</Num> promoted)
        </div>
        <ul className="mt-2 space-y-1">
          {data.kinds.map((k) => (
            <li
              key={k.kind}
              className="flex items-center justify-between px-1 py-1 font-mono text-xs hover:bg-surface-2"
            >
              <span className="text-foreground">{k.kind}</span>
              <span className="text-muted-foreground">
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
        <p className="mt-3 text-[11px] text-faint">{data.honest_note}</p>
      ) : null}
    </Panel>
  );
}
