"use client";

// Legend.tsx -- a compact key for symbols / terms used on a page.
//
// Two uses: (1) pass `terms` (glossary keys) to render an InfoTip-backed key of
// definitions; (2) pass explicit `items` (swatch + label + optional tip) for a
// color/symbol key. Purely explanatory; no numbers, no $ field. Accessible as a
// description list.

import * as React from "react";
import { cn } from "@/lib/utils";
import { InfoTip } from "./InfoTip";
import { lookupTerm } from "./glossary";

export interface LegendItem {
  /** Short label shown for this entry. */
  label: string;
  /** Optional inline definition (rendered via InfoTip). */
  tip?: string;
  /** Optional glossary term to source the tip from. */
  term?: string;
  /** Optional Tailwind classes for a leading swatch (e.g. "bg-tier-s"). */
  swatch?: string;
}

export interface LegendProps {
  /** Heading for the legend block. */
  title?: string;
  /** Glossary term keys -> a definition key. Rendered before `items`. */
  terms?: string[];
  /** Explicit legend rows (swatches / symbols). */
  items?: LegendItem[];
  className?: string;
}

/** A page-level key of terms and/or symbol swatches. */
export function Legend({ title = "Legend", terms, items, className }: LegendProps) {
  const termItems: LegendItem[] = (terms ?? [])
    .map((t) => lookupTerm(t))
    .filter((e): e is NonNullable<typeof e> => Boolean(e))
    .map((e) => ({ label: e.label, term: e.term }));
  const all = [...termItems, ...(items ?? [])];

  if (all.length === 0) return null;

  return (
    <section
      aria-label={title}
      className={cn("border border-border bg-surface-1 p-3 text-xs", className)}
    >
      <h3 className="microlabel mb-2">{title}</h3>
      <dl className="flex flex-wrap gap-x-4 gap-y-2">
        {all.map((it, i) => (
          <div key={`${it.label}-${i}`} className="flex items-center gap-1.5">
            {it.swatch && (
              <span aria-hidden className={cn("inline-block h-3 w-3", it.swatch)} />
            )}
            <dt className="font-data text-foreground">{it.label}</dt>
            {(it.tip || it.term) && (
              <dd className="m-0">
                <InfoTip term={it.term} text={it.tip} />
              </dd>
            )}
          </div>
        ))}
      </dl>
    </section>
  );
}
