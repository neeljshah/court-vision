"use client";

// CompletenessStrip -- the COMPLETENESS + ENGINE-READINESS row of honest
// progress: parity matrix (now GREEN), the improvement ENGINE (proven-READY but
// INERT), and the model-static fact. These are NOT accuracy numbers. The engine
// is proven on a SEALED fold (Brier 0.2025 -> 0.0958 WHEN enabled) but is
// human-gated OFF (engine_enabled=false), so the model never moves. NO $ field.

import { Badge } from "@/components/p6/Primitives";
import { InfoTip } from "@/components/depth";

function Cell({
  label,
  value,
  tone,
  tip,
}: {
  label: string;
  value: string;
  tone: "green" | "amber" | "slate";
  tip: string;
}) {
  const t =
    tone === "green"
      ? "border-tier-a/40 bg-tier-a/5 text-tier-a"
      : tone === "amber"
        ? "border-amber-900/50 bg-amber-950/20 text-amber-400"
        : "border-slate-800 bg-bg-panel/40 text-foreground";
  return (
    <div className={`flex flex-col gap-1 rounded-lg border p-3 ${t}`}>
      <div className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
        <InfoTip text={tip} ariaLabel={`what is ${label}?`} />
      </div>
      <div className="font-mono text-sm font-semibold">{value}</div>
    </div>
  );
}

export function CompletenessStrip({
  parityGreen,
  engineReady,
  engineEnabled,
}: {
  parityGreen: boolean | null;
  engineReady: boolean;
  engineEnabled: boolean;
}) {
  const parityVal =
    parityGreen === null ? "UNAVAILABLE" : parityGreen ? "GREEN" : "RED";
  const parityTone: "green" | "amber" | "slate" =
    parityGreen === null ? "amber" : parityGreen ? "green" : "amber";

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Cell
        label="parity matrix"
        value={parityVal}
        tone={parityTone}
        tip="The cross-sport coverage / loop-health grid. FULLY GREEN means every present cell passes -- it is a COMPLETENESS check, not an accuracy or $ result. A present-but-broken cell would be RED and fail the gate."
      />
      <Cell
        label="improve engine"
        value={engineReady ? "READY" : "NOT READY"}
        tone={engineReady ? "green" : "amber"}
        tip="The self-improve ratchet is PROVEN-ready on a sealed held-out fold (Brier 0.2025 -> 0.0958 WHEN enabled). 'Ready' means it can recalibrate if a human turns it on -- it does NOT mean the model is currently improving."
      />
      <Cell
        label="engine enabled"
        value={engineEnabled ? "ON" : "INERT (OFF)"}
        tone={engineEnabled ? "green" : "amber"}
        tip="The PIPELINE_ENABLED sentinel is a human gate and is ABSENT here, so the engine is INERT: it measures only and ships NOTHING. The model is STATIC until a human enables it. Real money is default-DENY."
      />
    </div>
  );
}
