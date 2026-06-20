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
import { cn } from "@/lib/utils";
import { EMPTY_CELL } from "@/lib/tokens";
import type { PredictMarket, Market } from "@/lib/api";
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
      <p className={cn("text-xs text-muted-foreground", className)}>
        No market surface available for this game.
      </p>
    );
  }

  return (
    <div className={className}>
      <Table>
        <TableCaption className="text-left">
          {caption ??
            "One coherent market surface, spined by a single anchor. Probability only -- no price."}
        </TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">market</TableHead>
            <TableHead scope="col">side</TableHead>
            <TableHead scope="col">line</TableHead>
            <TableHead scope="col">
              <span className="inline-flex items-center gap-1">
                model prob
                <InfoTip term="probability" />
              </span>
            </TableHead>
            <TableHead scope="col">provenance</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {markets.map((m, i) => (
            <TableRow key={`${m.market_type}-${m.side}-${i}`}>
              <TableCell className="font-mono text-xs">{m.market_type}</TableCell>
              <TableCell className="text-xs">{m.side}</TableCell>
              <TableCell className="font-mono text-xs tabular-nums">
                {fmtLine(m.line)}
              </TableCell>
              <TableCell className="font-mono text-xs tabular-nums">
                {fmtProb(m.devigged_prob)}
              </TableCell>
              <TableCell>
                <ProvenanceBadge model={model} phase={phase} showTip={false} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
