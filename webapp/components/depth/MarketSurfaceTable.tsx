"use client";

// Market reference probabilities from the source's devigged_prob field.
// Book, capture time and proxy status belong to each row; these are not model
// outputs. Missing probability or provenance remains explicitly unavailable.
//
// Accessible: a real <table> with a caption and scoped headers.

import * as React from "react";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
} from "@/components/ui/table";
import { EMPTY_CELL } from "@/lib/tokens";
import type { PredictMarket, Market } from "@/lib/api";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { ProvenanceBadge } from "./ProvenanceBadge";
import { InfoTip } from "./InfoTip";

/** Minimal market-reference row shape (accepts PredictMarket or Market). */
export type SurfaceRow = Pick<
  PredictMarket | Market,
  "market_type" | "side" | "line" | "devigged_prob"
> & Partial<Pick<PredictMarket | Market, "book" | "captured_at" | "clv_is_proxy" | "is_close">>;

export interface MarketSurfaceTableProps {
  /** Published market references, including per-row provenance when present. */
  markets: SurfaceRow[];
  /** Optional caption override. */
  caption?: string;
  className?: string;
}

const fmtProb = (p: number | null | undefined): string =>
  typeof p === "number" && Number.isFinite(p)
    ? `${(p * 100).toFixed(1)}%`
    : EMPTY_CELL;

const fmtLine = (l: number | null | undefined): string =>
  typeof l === "number" && Number.isFinite(l) ? String(l) : EMPTY_CELL;

/** Market reference probabilities for a game. */
export function MarketSurfaceTable({
  markets,
  caption,
  className,
}: MarketSurfaceTableProps) {
  if (!markets || markets.length === 0) {
    return (
      <Panel className={className}>
        <PanelHead title="Market surface" />
        <p className="p-3 text-xs text-faint">
          No market surface available for this game.
        </p>
      </Panel>
    );
  }

  return (
    <Panel className={className}>
      <PanelHead title="Market surface" />
      <div className="overflow-x-auto">
        <Table>
          <TableCaption className="px-3 text-left text-faint">
            {caption ??
              "Devigged market references from the named sources. These are not model probabilities."}
          </TableCaption>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead scope="col" className="microlabel h-auto px-3 py-1.5">
                market
              </TableHead>
              <TableHead scope="col" className="microlabel h-auto px-3 py-1.5">
                side
              </TableHead>
              <TableHead scope="col" className="microlabel h-auto px-3 py-1.5 text-right">
                line
              </TableHead>
              <TableHead scope="col" className="microlabel h-auto px-3 py-1.5 text-right">
                <span className="inline-flex items-center justify-end gap-1">
                  market prob
                  <InfoTip term="devig" />
                </span>
              </TableHead>
              <TableHead scope="col" className="microlabel h-auto px-3 py-1.5">
                provenance
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {markets.map((m, i) => (
              <TableRow
                key={`${m.market_type}-${m.side}-${i}`}
                className="border-border hover:bg-surface-2"
              >
                <TableCell className="p-0 px-3 py-1.5 text-xs">{m.market_type}</TableCell>
                <TableCell className="p-0 px-3 py-1.5 text-xs">{m.side}</TableCell>
                <TableCell className="p-0 px-3 py-1.5 text-right">
                  <Num>{fmtLine(m.line)}</Num>
                </TableCell>
                <TableCell className="p-0 px-3 py-1.5 text-right">
                  <Num>{fmtProb(m.devigged_prob)}</Num>
                </TableCell>
                <TableCell className="p-0 px-3 py-1.5">
                  <ProvenanceBadge
                    trail={[
                      m.book || "source unavailable",
                      m.clv_is_proxy ? "proxy reference" : m.is_close ? "closing reference" : "market reference",
                    ]}
                    showTip={false}
                  />
                  <div className="font-data text-[10px] text-faint">
                    {m.captured_at || "capture time unavailable"}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Panel>
  );
}
