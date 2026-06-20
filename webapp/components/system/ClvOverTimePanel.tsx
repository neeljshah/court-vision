"use client";

import { useEffect, useState } from "react";
import { Panel, Unavailable, Badge } from "@/components/p6/Primitives";
import { InfoTip } from "@/components/depth";
import { systemApi, isUnavailable, type ClvOverTime } from "./systemApi";

// ClvOverTimePanel -- the MULTI-GAME aggregate CLV-over-time read from
// /api/clv/over-time. MEASUREMENT-ONLY: CLV lives in PROBABILITY space, never $.
// One/few games is variance, so the honest default is INSUFFICIENT_DATA and
// vs_close stays UNPROVEN. No edge is claimed; this is calibration observability.

function verdictTone(v: string): "green" | "amber" | "slate" {
  if (v === "BEAT") return "green";
  if (v === "BEHIND") return "amber";
  return "slate"; // MATCH / INSUFFICIENT_DATA
}

export function ClvOverTimePanel() {
  const [data, setData] = useState<ClvOverTime | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    systemApi.clvOverTime(ac.signal).then((d) => {
      if (isUnavailable(d)) {
        setErr((d as { reason?: string }).reason || "clv-over-time unavailable");
      } else {
        setData(d as ClvOverTime);
        setErr(null);
      }
    });
    return () => ac.abort();
  }, []);

  const verdict = data?.pool_verdict || "INSUFFICIENT_DATA";

  return (
    <Panel
      title="CLV over time (measurement-only, probability)"
      right={
        <span className="inline-flex items-center gap-1.5">
          {data ? <Badge tone={verdictTone(verdict)}>{verdict}</Badge> : null}
          <InfoTip term="clv" ariaLabel="what is CLV?" />
        </span>
      }
    >
      {err ? (
        <Unavailable reason={err} />
      ) : !data ? (
        <p className="text-sm text-slate-500">loading...</p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-3 gap-3 text-xs">
            <Stat label="games" value={String(data.n_games ?? 0)} />
            <Stat label="settled" value={String(data.n_settled_games ?? 0)} />
            <Stat
              label="pooled CLV (prob)"
              tip="Mean closing-line value in PROBABILITY space (not dollars). Positive = our recorded number beat the close. One/few games is variance, not a result."
              value={
                typeof data.pooled_mean_clv === "number"
                  ? data.pooled_mean_clv.toFixed(4)
                  : "n/a"
              }
            />
          </div>
          <p className="text-[11px] leading-relaxed text-slate-600">
            {data.label ||
              "CLV / calibration in probability space, no currency."}{" "}
            vs close:{" "}
            <span className="font-mono text-amber-600/80">
              {data.vs_close?.startsWith("UNPROVEN") ? "UNPROVEN" : data.vs_close || "UNPROVEN"}
            </span>
            . One game is variance -- the honest default is INSUFFICIENT_DATA.
          </p>
        </div>
      )}
    </Panel>
  );
}

function Stat({ label, value, tip }: { label: string; value: string; tip?: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-bg-panel/40 px-3 py-2">
      <div className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-slate-500">
        {label}
        {tip ? <InfoTip text={tip} ariaLabel={`what is ${label}?`} /> : null}
      </div>
      <div className="mt-0.5 font-mono text-sm text-slate-200">{value}</div>
    </div>
  );
}
