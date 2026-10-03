"use client";

// ModelVsMarketBar.tsx -- opposing probability bars: model vs devigged market.
//
// HONESTY RAILS:
//   - Divergence is labeled "calibrated divergence" -- NEVER "edge" or "profit"
//   - Negative divergence (model below market) is a valid under/away signal, not an error
//   - Colors: model bar = --s-model amber; market bar = --s-market blue (source colors)
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
  model_prob: number | null;
  /** [0,1] devigged market probability for this side. */
  market_prob: number | null;
  /** Signed divergence: model_prob - market_prob (pre-computed for display). */
  divergence: number | null;
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

function isProbability(p: unknown): p is number {
  return typeof p === "number" && Number.isFinite(p) && p >= 0 && p <= 1;
}

function pctStr(p: number): string {
  return `${p * 100}%`;
}

function fmtProb(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}

// Divergence magnitude tag: classifies the signal for the label chip.
function divergenceToneClass(is_signal: boolean): string {
  if (!is_signal) return "text-muted-foreground bg-surface-3 border-border";
  // Both directions of signal use the same slate-200 tone (honest: not green for over, not red for under)
  return "text-foreground bg-surface-3 border-muted-foreground";
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
  const modelAvailable = isProbability(model_prob);
  const marketAvailable = isProbability(market_prob);
  const divergenceAvailable = modelAvailable && marketAvailable &&
    typeof divergence === "number" && Number.isFinite(divergence) && Math.abs(divergence) <= 1;
  const divergenceText = divergenceAvailable ? divergence_label : "Unavailable";
  const modelText = modelAvailable ? fmtProb(model_prob) : "unavailable";
  const marketText = marketAvailable ? fmtProb(market_prob) : "unavailable";

  const ariaBase = aria_suffix ? ` -- ${aria_suffix}` : "";
  const ariaLabel =
    framing === "descriptive"
      ? `Model vs market probabilities${ariaBase}: calibration context only, no active bet recommendation`
      : `Model vs market probabilities${ariaBase}: model ${modelText}, market ${marketText}, calibrated divergence ${divergenceText}, not an edge or profit claim`;

  return (
    <div
      className="flex flex-col gap-2"
      role="group"
      aria-label={ariaLabel}
      data-testid="model-vs-market-bar"
    >
      {/* Descriptive overlay */}
      {framing === "descriptive" ? (
        <div className="rounded-md border border-border bg-surface-2 px-3 py-2">
          <span
            className="font-mono text-[10px] text-muted-foreground"
            data-testid="descriptive-note"
          >
            {DESCRIPTIVE_NOTE}
          </span>
        </div>
      ) : null}

      {/* Model row */}
      <div className="flex items-center gap-2" data-testid="model-bar-row"
        role={modelAvailable ? undefined : "group"}
        aria-label={modelAvailable ? undefined : "Model probability unavailable"}>
        <span
          className="w-16 shrink-0 text-right font-mono text-[9px] uppercase tracking-widest text-muted-foreground"
          aria-hidden="true"
        >
          Model p
        </span>
        <div className="relative flex-1 overflow-hidden rounded-full bg-surface-3" style={{ height: "10px" }}>
          {modelAvailable && (
          <div
            className={cn(
              "absolute inset-y-0 left-0 rounded-full transition-all duration-300",
              BAR_HEIGHT,
              "bg-s-model",
            )}
            style={{ width: pctStr(model_prob) }}
            role="meter"
            aria-label={`model probability ${fmtProb(model_prob)}`}
            aria-valuenow={Math.round(model_prob * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            data-testid="model-bar"
          />
          )}
        </div>
        <span
          className="w-12 shrink-0 font-mono text-[11px] tabular-nums text-foreground"
          aria-hidden="true"
        >
          {modelAvailable ? modelText : "--"}
        </span>
      </div>

      {/* Market row (devigged) */}
      <div className="flex items-center gap-2" data-testid="market-bar-row"
        role={marketAvailable ? undefined : "group"}
        aria-label={marketAvailable ? undefined : "Market probability unavailable"}>
        <span
          className="w-16 shrink-0 text-right font-mono text-[9px] uppercase tracking-widest text-muted-foreground"
          aria-hidden="true"
        >
          Market p
        </span>
        <div className="relative flex-1 overflow-hidden rounded-full bg-surface-3" style={{ height: "10px" }}>
          {marketAvailable && (
          <div
            className={cn(
              "absolute inset-y-0 left-0 rounded-full transition-all duration-300",
              BAR_HEIGHT,
              "bg-s-market",
            )}
            style={{ width: pctStr(market_prob) }}
            role="meter"
            aria-label={`devigged market probability ${fmtProb(market_prob)}`}
            aria-valuenow={Math.round(market_prob * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            data-testid="market-bar"
          />
          )}
        </div>
        <span
          className="w-12 shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground"
          aria-hidden="true"
        >
          {marketAvailable ? marketText : "--"}
        </span>
      </div>

      {/* Divergence chip */}
      {framing !== "descriptive" ? (
        <div className="flex flex-wrap items-center justify-end gap-1.5">
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
              divergenceToneClass(divergenceAvailable && divergence_is_signal),
            )}
            title={divergenceAvailable ? DIVERGENCE_TIP : "Requires valid model and market probabilities and a reported divergence."}
            aria-label={`calibrated divergence ${divergenceText} -- not an edge or profit claim`}
            data-testid="divergence-chip"
          >
            {divergenceText}
          </span>
        </div>
      ) : null}

      {/* Confidence strip (optional) */}
      {divergenceAvailable && isProbability(confidence) && confidence > 0 && framing !== "descriptive" ? (
        <div
          className="flex items-center gap-2"
          aria-label={`signal strength proxy ${(confidence * 100).toFixed(0)}% -- derived from EV magnitude, not a profit claim`}
          title="signal strength proxy -- derived from EV magnitude, not a fabricated confidence"
        >
          <span className="w-16 shrink-0 text-right font-mono text-[9px] uppercase tracking-widest text-faint">
            Signal
          </span>
          <div className="relative flex-1 overflow-hidden rounded-full bg-surface-3" style={{ height: "4px" }}>
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-muted-foreground transition-all duration-300"
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
