// SelfImproveExplainer.tsx -- the self-improve ratchet, explained as READY-INERT.
//
// Client component. Explains the measurement-only self-improve loop and shows its
// LIVE mode from the real endpoint (getProductStatus -> selfImprove). The honest
// default is READY (not enabled): the loop is built and human-gated OFF. The mode
// pill degrades to "status unknown" if the endpoint is unreachable -- never
// green-on-missing. NO $ field; no edge claimed.

"use client";

import { useEffect, useState } from "react";
import { getProductStatus } from "@/lib/api";
import type { ProductStatus } from "@/lib/api";
import { Panel, PanelHead } from "@/components/ui/terminal";

const STEPS = [
  "Replay live games to grade each served prediction (CALIBRATION, not $).",
  "Run the candidate recalibration through the SAME leak-free eval gate.",
  "Only a gate PASS would ratchet the calibration forward -- a REJECT changes nothing.",
  "A human gate must be flipped ON for any change to take effect.",
];

function ModePill({ status }: { status: ProductStatus | null }) {
  const mode = status?.selfImprove ?? "READY_INERT";
  const unreachable = status === null;
  const label = unreachable
    ? "self-improve: status unknown (endpoint unreachable)"
    : mode === "ENABLED"
    ? "self-improve: ENABLED"
    : "self-improve: READY (not enabled)";
  // INERT/unknown read amber-neutral, never green; only an actual ENABLE reads green.
  const tone = mode === "ENABLED" ? "border-tier-a text-tier-a" : "border-warning text-warning";
  return (
    <span className={`border px-1.5 py-px font-data text-[10px] uppercase tracking-wider ${tone}`}>
      {label}
    </span>
  );
}

export function SelfImproveExplainer() {
  const [status, setStatus] = useState<ProductStatus | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getProductStatus(ctrl.signal)
      .then(setStatus)
      .catch(() => setStatus(null));
    return () => ctrl.abort();
  }, []);

  return (
    <section aria-label="self-improve ratchet">
    <Panel>
      <PanelHead title="the self-improve ratchet -- ready, not enabled" right={<ModePill status={status} />} />
      <div className="p-4">
        <p className="text-xs leading-relaxed text-muted-foreground">
          The system can grade its own predictions and propose a recalibration -- but the
          loop is a <span className="font-semibold text-foreground">measurement-only</span>{" "}
          ratchet that is built and READY yet INERT (the human gate is OFF). It can only
          ever move calibration forward through the same gate that rejects everything else,
          and a human must enable it. Nothing changes the served prediction until then.
        </p>
        <ol className="mt-3 flex flex-col gap-2">
          {STEPS.map((s, i) => (
            <li key={i} className="flex gap-3 text-[11px] leading-relaxed text-muted-foreground">
              <span className="font-data font-semibold text-muted-foreground">{`0${i + 1}`}</span>
              <span>{s}</span>
            </li>
          ))}
        </ol>
        <p className="mt-3 border border-warning/40 bg-warning/5 px-2.5 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
          Real-money execution is default-DENY (paper mode only). The ratchet only ever
          improves CALIBRATION -- it can never manufacture a market edge.
        </p>
      </div>
    </Panel>
    </section>
  );
}
