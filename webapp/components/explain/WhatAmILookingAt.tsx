"use client";

// WhatAmILookingAt.tsx -- the short "what am I looking at?" orientation intro.
//
// Sets the reader up before the funnel: a one-paragraph plain-language framing of
// what this product IS (a calibrated predictor, NOT a betting-edge product), a
// glossary Legend of the load-bearing terms so every later number is decodable,
// and a LIVE parity-green snapshot pulled from the real endpoint (the honest
// cross-sport health bit) -- degrading to an honest "unknown" when unreachable,
// never green-on-missing.
//
// HONESTY RAILS: calibration not edge; vs_close UNPROVEN; UNITS / probability
// only, NO $ field; no fabricated number -- the parity bit is the live API's.

import { useEffect, useState } from "react";
import { getParityHeadline } from "@/lib/api";
import type { ParityHeadline } from "@/lib/api";
import { Legend, InfoTip } from "@/components/depth";
import { Panel, PanelHead } from "@/components/ui/terminal";

function ParitySnapshot({ parity }: { parity: ParityHeadline | null }) {
  const green = parity?.green ?? null;
  const label =
    green === null
      ? "parity: status unknown (endpoint unreachable)"
      : green
      ? `parity: FULLY GREEN across ${parity?.nSports ?? 0} sports`
      : "parity: not green -- see the System page";
  // unknown/not-green read amber (stale); only an actual GREEN reads positive.
  const tone = green === true ? "border-success text-success" : "border-warning text-warning";
  return (
    <span className={`border px-1.5 py-px font-data text-[10px] uppercase tracking-wider ${tone}`}>
      {label}
    </span>
  );
}

export function WhatAmILookingAt() {
  const [parity, setParity] = useState<ParityHeadline | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getParityHeadline(ctrl.signal)
      .then(setParity)
      .catch(() => setParity(null));
    return () => ctrl.abort();
  }, []);

  return (
    <section aria-label="what am I looking at?">
    <Panel>
      <PanelHead title="what am I looking at?" right={<ParitySnapshot parity={parity} />} />
      <div className="flex flex-col gap-3 p-4">
        <p className="text-xs leading-relaxed text-muted-foreground">
          This page walks the whole pipeline from raw game data to a single
          calibrated{" "}
          <span className="inline-flex items-center gap-1">
            probability
            <InfoTip term="probability" />
          </span>{" "}
          per market. It is a{" "}
          <span className="font-semibold text-foreground">calibrated predictor</span>,
          not a betting-edge product: the honest, defensible win is matching the
          devigged close within noise (good{" "}
          <span className="inline-flex items-center gap-1">
            calibration
            <InfoTip term="calibration" />
          </span>
          ), plus one measured in-game conditioning improvement. Every figure is in{" "}
          <span className="inline-flex items-center gap-1">
            units
            <InfoTip term="units" />
          </span>{" "}
          or probability -- there is no dollar figure anywhere, and{" "}
          <span className="inline-flex items-center gap-1">
            vs_close
            <InfoTip term="vs_close" />
          </span>{" "}
          stays UNPROVEN.
        </p>
        <Legend
          title="key terms in this walkthrough"
          terms={[
            "calibration",
            "edge",
            "brier",
            "devig",
            "vs_close",
            "provenance",
            "uncertainty",
          ]}
        />
      </div>
    </Panel>
    </section>
  );
}
