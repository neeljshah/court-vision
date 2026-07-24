"use client";

// ReceiptChip.tsx -- THE signature component: every number wears its receipt.
//
// Resting state: a compact monospace "R" glyph after a number. Expanded: a
// popover (four rows -- SOURCE / AS OF / VERIFIED / VERDICT) on pointer hover
// (tooltip) or touch tap (dialog). Badge color = meaning: edge_claimed:false /
// descriptive_only are neutral info blue (the point -- no edge claimed);
// MODEL_SHARPER green, MARKET_SHARPER red (losses at full size), UNDERPOWERED /
// NO_MARKET_COMPARISON faint, VALIDATION_PENDING / stale amber. Never green by
// default. Descriptive only; never invents a value. See DESIGN.md sec.3.

import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import {
  Dialog,
  DialogContent,
  DialogTrigger,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export interface ReceiptChipProps {
  /** Repo-relative artifact path (backslashes normalized). */
  sourceArtifact: string;
  /** ISO or "YYYY-MM-DD"; null -> VALIDATION_PENDING. */
  asOf: string | null;
  verified?: "edge_claimed:false" | "descriptive_only" | "validation_pending";
  /** MARKET_SHARPER_PROVISIONAL | MODEL_SHARPER_PROVISIONAL | UNDERPOWERED | ... */
  verdict?: string | null;
  n?: number | null;
  ci?: [number, number] | null;
  /** Freshness violation -> glyph + AS OF row amber. */
  stale?: boolean;
  /** Link to the file on the public origin. */
  href?: string | null;
  className?: string;
}

// Detect touch (coarse pointer / no hover) after mount so SSR stays stable.
function useIsTouch(): boolean {
  const [touch, setTouch] = React.useState(false);
  React.useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    setTouch(window.matchMedia("(hover: none), (pointer: coarse)").matches);
  }, []);
  return touch;
}

function verdictClass(verdict?: string | null): string {
  if (!verdict) return "text-faint border-border";
  if (verdict.startsWith("MODEL_SHARPER"))
    return "text-success border-success/50";
  if (verdict.startsWith("MARKET_SHARPER"))
    return "text-danger border-danger/50";
  if (verdict === "UNDERPOWERED" || verdict === "NO_MARKET_COMPARISON")
    return "text-faint border-border";
  return "text-faint border-border";
}

function verifiedClass(verified: string): string {
  if (verified === "validation_pending") return "text-stale border-stale/50";
  return "text-info border-info/50"; // edge_claimed:false | descriptive_only
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="microlabel pt-0.5">{label}</dt>
      <dd className="m-0 break-all font-data text-[11px] text-foreground">
        {children}
      </dd>
    </>
  );
}

/** The four-row receipt body, shared by tooltip and dialog. */
function ReceiptRows(props: ReceiptChipProps) {
  const { sourceArtifact, asOf, verdict, n, ci, stale, href } = props;
  const verified = asOf == null ? "validation_pending" : props.verified ?? "edge_claimed:false";
  const isStale = stale || verified === "validation_pending";
  const nBits = [
    n != null ? `n = ${n}` : null,
    ci ? `[95% CI ${ci[0]}, ${ci[1]}]` : null,
  ].filter(Boolean);
  return (
    <dl className="m-0 grid grid-cols-[64px_1fr] gap-x-2.5 gap-y-1">
      <Row label="source">
        {href ? (
          <a
            href={href}
            className="underline decoration-dotted underline-offset-2 hover:text-primary"
            target="_blank"
            rel="noreferrer"
          >
            {sourceArtifact}
          </a>
        ) : (
          sourceArtifact
        )}
      </Row>
      <Row label="as of">
        <span className={cn(isStale && "text-stale")}>
          {asOf ?? "not yet measured on this clone"}
        </span>
      </Row>
      <Row label="verified">
        <span
          className={cn(
            "inline-block border px-1.5 py-px font-data text-[10px]",
            verifiedClass(verified)
          )}
        >
          {verified}
        </span>
      </Row>
      {(verdict || nBits.length > 0) && (
        <Row label="verdict">
          {verdict && (
            <span className={cn("font-data", verdictClass(verdict).split(" ")[0])}>
              {verdict}
            </span>
          )}
          {nBits.length > 0 && (
            <span className="ml-2 text-faint">{nBits.join("  ")}</span>
          )}
        </Row>
      )}
    </dl>
  );
}

/** The resting "R" glyph -- faint by default, amber when stale/pending. */
const Glyph = React.forwardRef<
  HTMLButtonElement,
  React.ComponentPropsWithoutRef<"button"> & { amber?: boolean }
>(({ amber, className, ...props }, ref) => (
  <button
    ref={ref}
    type="button"
    aria-label="show receipt: source, as-of, verification"
    className={cn(
      "ml-1 inline-flex items-center border px-1 align-[1px] font-data text-[10px] leading-tight",
      "focus:outline-none focus-visible:ring-1 focus-visible:ring-ring",
      amber ? "border-stale/60 text-stale" : "border-border text-faint",
      className
    )}
    {...props}
  >
    R
  </button>
));
Glyph.displayName = "ReceiptGlyph";

/** Every number-bearing surface gets one of these. */
export function ReceiptChip(props: ReceiptChipProps) {
  const isTouch = useIsTouch();
  const amber = Boolean(props.stale) || props.asOf == null;

  if (isTouch) {
    return (
      <Dialog>
        <DialogTrigger asChild>
          <Glyph amber={amber} className={props.className} />
        </DialogTrigger>
        <DialogContent className="max-w-[340px] rounded-none border-border bg-card p-3">
          <DialogTitle className="microlabel mb-2">receipt</DialogTitle>
          <ReceiptRows {...props} />
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <TooltipPrimitive.Provider delayDuration={100}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>
          <Glyph amber={amber} className={props.className} />
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side="top"
            align="end"
            sideOffset={6}
            className="z-50 w-[340px] border border-border bg-card p-3 text-left shadow-lg"
          >
            <ReceiptRows {...props} />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
