"use client";

// InfoTip.tsx -- a hover/tap "what is this?" affordance.
//
// Wraps the shared ui/tooltip with a plain-language definition pulled from the
// GLOSSARY (or an explicit `text` prop). Accessible: the trigger is a real
// <button> with aria-label, keyboard-focusable, and the tooltip works on tap
// (Radix opens on focus/touch). Renders an inline "(i)" marker so a reader can
// always ask what a number means.
//
// No numbers, no $ field; purely an explanatory affordance.

import * as React from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { lookupTerm } from "./glossary";

export interface InfoTipProps {
  /** Glossary term key (e.g. "clv"). Resolved from GLOSSARY for the definition. */
  term?: string;
  /** Explicit definition text; overrides the glossary lookup when provided. */
  text?: string;
  /** Optional visible label rendered before the (i) marker. */
  label?: string;
  /** Accessible name for the trigger; defaults to "what is <label/term>?". */
  ariaLabel?: string;
  className?: string;
}

/**
 * Inline tooltip explaining a term. Resolves copy from `text` first, else the
 * GLOSSARY by `term`. Falls back to a neutral message if neither resolves --
 * never fabricates a definition.
 */
export function InfoTip({ term, text, label, ariaLabel, className }: InfoTipProps) {
  const entry = term ? lookupTerm(term) : undefined;
  const definition =
    text ?? entry?.definition ?? "No definition available for this term.";
  const shownLabel = label ?? entry?.label ?? term ?? "info";
  const aria = ariaLabel ?? `what is ${shownLabel}?`;

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={aria}
            className={cn(
              "inline-flex items-center gap-1 text-faint " +
                "hover:text-foreground focus:outline-none focus-visible:ring-2 " +
                "focus-visible:ring-ring align-middle",
              className
            )}
          >
            {label && <span className="microlabel">{label}</span>}
            {/* Info glyph: an icon, not a card -- rounded-full is the icon shape, not decoration. */}
            <span
              aria-hidden
              className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-current text-[9px] font-data font-semibold leading-none"
            >
              i
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent
          role="tooltip"
          className="max-w-xs border-border bg-card text-xs leading-relaxed text-foreground"
        >
          {definition}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
