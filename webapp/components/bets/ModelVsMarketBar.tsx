"use client";

// ModelVsMarketBar.tsx -- opposing probability bars: model vs devigged market.
//
// HONESTY RAILS:
//   - Divergence is labeled "calibrated divergence" -- NEVER "edge" or "profit"
//   - Negative divergence (model below market) is a valid under/away signal, not an error
//   - Colors: model bar = slate-300; market bar = slate-500 (neutral opposing pair)
//   - No green for a positive divergence, no red for a negative divergence
//   - Units only; no $ anywhere
//   - When framing='descriptive' suppresses the divergence signal, shows neutral state

import * as React from "react";
import { cn } from "@/lib/utils";
import type { CardFraming } from "./cardDepth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ModelVsMarketBarProps {
  /** [0,1] calibrated model probability for this side. */
  model_prob: number;
  /** [0,1] devigged market probability for this side. */
  market_prob: number;
  /** Signed divergence: model_prob - market_prob (pre-computed for display). */
  divergence: number;
  /** Formatted divergence label, e.g. "+5.3pp". Never says 'edge'/'profit'. */
  divergence_label: string;
  /** Whether divergence crosses the signal threshold (>= 5pp abs). */
  divergence_is_signal: boolean;
  /** When 'descriptive', suppress the divergence framing and show neutral state. */
  framing: CardFraming;
  /** Optional: confidence [0,1] -- shown as a thin strip below the bars. */
  confidence?: number | null;
  /** Optional: aria label suffix for the component. */
  aria_suffix?: string;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

const BAR_HEIGHT = "h-2.5";

// Clamp a probability to [0.02, 0.98] so bars are always visible.
function clampProb(p: number): number {
  return Math.max(0.02, Math.min(0.98, isFinite(p) ? p : 0.5));
}

function pctStr(p: number): string {
  return `${(clampProb(p) * 100).toFixed(0)}%`;
}

function fmtProb(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}

// Divergence magnitude tag: classifies the signal for the label chip.
function divergenceToneClass(divergence: number, is_signal: boolean): string {
  if (!is_signal) return "text-slate-400 bg-slate-800/60 border-slate-700";
  // Both directions of signal use the same slate-200 tone (honest: not green for over, not red for under)
  return "text-slate-200 bg-slate-700/60 border-slate-600";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DIVERGENCE_TIP =
  "Calibrated divergence: model probability minus devigged market probability. " +
  "A positive value means the model sees this outcome as more likely than the market. " +
  "A negative value is a valid under/away signal -- not an error. " +
  "This is NOT an edge or profit claim.";

const DESCRIPTIVE_NOTE =
  "No active bet recommendation. Showing calibration context only.";

export function ModelVsMarketBar({
  model_prob,
  market_prob,
  divergence,
  divergence_label,
  divergence_is_signal,
  framing,
  confidence,
  aria_suffix,
}: ModelVsMarketBarProps) {
  const modelPct = pctStr(model_prob);
  const marketPct = pctStr(market_prob);

  const ariaBase = aria_suffix ? ` -- ${aria_suffix}` : "";
  const ariaLabel =
    framing === "descriptive"
      ? `Model vs market probabilities${ariaBase}: calibration context only, no active bet recommendation`
      : `Model vs market probabilities${ariaBase}: model ${fmtProb(model_prob)}, market ${fmtProb(market_prob)}, calibrated divergence ${divergence_label}, not an edge or profit claim`;

  return (
    <div
      className="flex flex-col gap-2"
      role="group"
      aria-label={ariaLabel}
      data-testid="model-vs-market-bar"
    >
      {/* Descriptive overlay */}
      {framing === "descriptive" ? (
        <div className="rounded-md border border-slate-700 bg-slate-900/60 px-3 py-2">
          <span
            className="font-mono text-[10px] text-muted-foreground"
            data-testid="descriptive-note"
          >
            {DESCRIPTIVE_NOTE}
          </span>
        </div>
      ) : null}

      {/* Model row */}
      <div className="flex items-center gap-2" data-testid="model-bar-row">
        <span
          className="w-16 shrink-0 text-right font-mono text-[9px] uppercase tracking-widest text-muted-foreground"
          aria-hidden="true"
        >
          Model p
        </span>
        <div className="relative flex-1 overflow-hidden rounded-full bg-slate-800" style={{ height: "10px" }}>
          <div
            className={cn(
              "absolute inset-y-0 left-0 rounded-full transition-all duration-300",
              BAR_HEIGHT,
              "bg-slate-300",
            )}
            style={{ width: modelPct }}
            role="meter"
            aria-label={`model probability ${fmtProb(model_prob)}`}
            aria-valuenow={Math.round(model_prob * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            data-testid="model-bar"
          />
        </div>
        <span
          className="w-12 shrink-0 font-mono text-[11px] tabular-nums text-foreground"
          aria-hidden="true"
        >
          {fmtProb(model_prob)}
        </span>
      </div>

      {/* Market row (devigged) */}
      <div className="flex items-center gap-2" data-testid="market-bar-row">
        <span
          className="w-16 shrink-0 text-right font-mono text-[9px] uppercase tracking-widest text-muted-foreground"
          aria-hidden="true"
        >
          Market p
        </span>
        <div className="relative flex-1 overflow-hidden rounded-full bg-slate-800" style={{ height: "10px" }}>
          <div
            className={cn(
              "absolute inset-y-0 left-0 rounded-full transition-all duration-300",
              BAR_HEIGHT,
              "bg-slate-500",
            )}
            style={{ width: marketPct }}
            role="meter"
            aria-label={`devigged market probability ${fmtProb(market_prob)}`}
            aria-valuenow={Math.round(market_prob * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            data-testid="market-bar"
          />
        </div>
        <span
          className="w-12 shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground"
          aria-hidden="true"
        >
          {fmtProb(market_prob)}
        </span>
      </div>

      {/* Divergence chip */}
      {framing !== "descriptive" ? (
        <div className="flex items-center justify-end gap-1.5">
          <span
            className="font-mono text-[9px] uppercase tracking-widest text-faint"
            aria-hidden="true"
          >
            Calibrated divergence
          </span>
          <span
            className={cn(
              "inline-flex items-center rounded border px-2 py-0.5",
              "font-mono text-[10px] font-semibold tabular-nums",
              divergenceToneClass(divergence, divergence_is_signal),
            )}
            title={DIVERGENCE_TIP}
            aria-label={`calibrated divergence ${divergence_label} -- not an edge or profit claim`}
            data-testid="divergence-chip"
          >
            {divergence_label}
          </span>
        </div>
      ) : null}

      {/* Confidence strip (optional) */}
      {confidence != null && confidence > 0 && framing !== "descriptive" ? (
        <div
          className="flex items-center gap-2"
          aria-label={`signal confidence ${(confidence * 100).toFixed(0)}% -- derived from EV magnitude, not a profit claim`}
        >
          <span className="w-16 shrink-0 text-right font-mono text-[9px] uppercase tracking-widest text-faint">
            Signal
          </span>
          <div className="relative flex-1 overflow-hidden rounded-full bg-slate-800/60" style={{ height: "4px" }}>
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-slate-600 transition-all duration-300"
              style={{ width: `${Math.min(100, Math.max(2, confidence * 100)).toFixed(0)}%` }}
              data-testid="confidence-strip"
            />
          </div>
          <span className="w-12 shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
            {(confidence * 100).toFixed(0)}%
          </span>
        </div>
      ) : null}

      {/* Honesty footnote */}
      <p className="font-mono text-[9px] text-faint" aria-hidden="true">
        Calibrated divergence -- not a profit claim. Units only, no $.
      </p>
    </div>
  );
}
