"use client";

import { useEffect, useState } from "react";
import { api, isUnavailable, type Parity } from "@/lib/p5api";
import { Panel, Unavailable, Badge } from "./Primitives";
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
        <p className="text-sm text-slate-500">loading…</p>
      </Panel>
    );
  }

  return (
    <Panel
      title="Parity / health grid"
      right={<Badge tone={data.green ? "green" : "red"}>{data.green ? "green" : "red"}</Badge>}
    >
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
            <th className="pb-2 font-medium">Sport</th>
            {data.dimensions.map((d) => (
              <th key={d} className="pb-2 font-medium">
                {d}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {data.sports.map((row) => (
            <tr key={row.sport} className="text-slate-200">
              <td className="py-2 font-mono text-xs">{row.sport}</td>
              {data.dimensions.map((d) => {
                const cell = row.cells[d];
                return (
                  <td key={d} className="py-2">
                    <Cell status={cell?.status} detail={cell?.detail} />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function Cell({ status, detail }: { status?: string; detail?: string }) {
  const tone =
    status === "green"
      ? "bg-tier-a/20 text-tier-a"
      : status === "red"
        ? "bg-red-950/40 text-red-400"
        : "bg-slate-800 text-slate-500";
  return (
    <span
      title={detail}
      className={cn(
        "inline-flex rounded px-1.5 py-0.5 text-[10px] font-mono",
        tone,
      )}
    >
      {status || "n/a"}
    </span>
  );
}
