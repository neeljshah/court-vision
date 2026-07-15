"use client";

import { useEffect, useState } from "react";
import { api, isUnavailable, type Parity } from "@/lib/p5api";
import { Panel, Unavailable, Badge } from "./Primitives";
import { Dot } from "@/components/ui/terminal";
import { cn } from "@/lib/utils";

// ParityGrid -- cross-sport coverage / loop-health grid from /api/parity.
// Fail-closed: a red cell fails the gate; n/a does not. Read-only.
export function ParityGrid() {
  const [data, setData] = useState<Parity | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    api.parity(ac.signal).then((d) => {
      if (isUnavailable(d)) setErr(d.reason || "parity unavailable");
      else setData(d as Parity);
    });
    return () => ac.abort();
  }, []);

  if (err || (data && data.status === "unavailable")) {
    return (
      <Panel title="Parity / health grid">
        <Unavailable reason={err || data?.reason} />
      </Panel>
    );
  }
  if (!data) {
    return (
      <Panel title="Parity / health grid">
        <p className="text-sm text-muted-foreground">loading…</p>
      </Panel>
    );
  }

  return (
    <Panel
      title="Parity / health grid"
      right={<Badge tone={data.green ? "green" : "red"}>{data.green ? "green" : "red"}</Badge>}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="microlabel py-1.5 px-3">Sport</th>
              {data.dimensions.map((d) => (
                <th key={d} className="microlabel py-1.5 px-3">
                  {d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.sports.map((row) => (
              <tr key={row.sport} className="text-foreground hover:bg-surface-2">
                <td className="py-1.5 px-3 font-mono text-xs">{row.sport}</td>
                {data.dimensions.map((d) => {
                  const cell = row.cells[d];
                  return (
                    <td key={d} className="py-1.5 px-3">
                      <Cell status={cell?.status} detail={cell?.detail} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function Cell({ status, detail }: { status?: string; detail?: string }) {
  const dotState = status === "green" ? "ok" : status === "red" ? "bad" : "warn";
  const tone =
    status === "green"
      ? "text-tier-a"
      : status === "red"
        ? "text-red-400"
        : "text-muted-foreground";
  return (
    <span title={detail} className="inline-flex items-center gap-1.5">
      <Dot state={dotState} />
      <span className={cn("font-mono text-[10px]", tone)}>{status || "n/a"}</span>
    </span>
  );
}
