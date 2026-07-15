"use client";

// MarketSurfaceTable.tsx -- the full coherent market surface for one game.
//
// Renders every market | side | line | model probability | provenance read off
// ONE engine matrix (the markets array of a PredictRecord / Report). The whole
// surface is spined by a single anchor, so the marginals are coherent. We show
// the MODEL probability (devigged_prob is the engine's implied prob) -- there is
// NO $/price/payout column anywhere. Missing prob -> honest "--", never a fake 0.
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

/** Minimal coherent-surface row shape (accepts PredictMarket or Market). */
export type SurfaceRow = Pick<
  PredictMarket | Market,
  "market_type" | "side" | "line" | "devigged_prob"
>;

export interface MarketSurfaceTableProps {
  /** The coherent market surface, read off ONE engine matrix. */
  markets: SurfaceRow[];
  /** Engine/model that produced the surface (e.g. "possession MC", "Dixon-Coles"). */
  model?: string;
  /** Phase the surface was produced at (e.g. "pregame"). */
  phase?: string;
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

/** Full coherent market surface for a game (no $ -- probability only). */
export function MarketSurfaceTable({
  markets,
  model = "possession MC",
  phase = "pregame",
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
              "One coherent market surface, spined by a single anchor. Probability only -- no price."}
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
                  model prob
                  <InfoTip term="probability" />
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
                  <ProvenanceBadge model={model} phase={phase} showTip={false} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Panel>
  );
}
