"use client";

// ProvenanceBadge.tsx -- shows where a number came from.
//
// Renders "model | phase" provenance (e.g. "Dixon-Coles | pregame") as a small
// outline chip with an InfoTip explaining what provenance means. Accepts either
// a free-form `model`/`phase` pair or the backend's string[] provenance trail
// (InGameServed.served.provenance). Purely descriptive; no numbers, no $.

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { InfoTip } from "./InfoTip";

export interface ProvenanceBadgeProps {
  /** Producing model/engine, e.g. "Dixon-Coles", "MOV-Elo", "possession MC". */
  model?: string;
  /** Phase the number was produced at, e.g. "pregame", "in-game", "close". */
  phase?: string;
  /**
   * Backend provenance trail (e.g. InGameServed.served.provenance). When given,
   * its parts are joined with " | " and used as the label.
   */
  trail?: string[];
  /** Show the explanatory InfoTip (default true). */
  showTip?: boolean;
  className?: string;
}

/** Join provenance parts honestly; empty -> a neutral "unknown" marker. */
function buildLabel(model?: string, phase?: string, trail?: string[]): string {
  if (trail && trail.length > 0) return trail.filter(Boolean).join(" | ");
  const parts = [model, phase].filter(Boolean) as string[];
  return parts.length > 0 ? parts.join(" | ") : "provenance unknown";
}

/** A small "model | phase" provenance chip. */
export function ProvenanceBadge({
  model,
  phase,
  trail,
  showTip = true,
  className,
}: ProvenanceBadgeProps) {
  const label = buildLabel(model, phase, trail);
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <Badge
        variant="outline"
        className="rounded-none border-border font-data text-[10px] font-normal tracking-tight text-faint"
        title={`source: ${label}`}
      >
        {label}
      </Badge>
      {showTip && <InfoTip term="provenance" />}
    </span>
  );
}
