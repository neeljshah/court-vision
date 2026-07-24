"use client";

// /paper/[betId] -- full execution detail for one PM paper trade.
// Loads the full trail via useLiveData and finds the matching row by bet_id.
// Shows: venue, price taken, model_prob, confidence, units, tier, result, CLV.
//
// LIVE POLLING:
//   - Open trades: poll every 30s -- status may change.
//   - Settled trades: status is final, only CLV can update; same cadence.
//   - Pause-on-hidden, last-good data retained on failed poll, honest stale state.
//   - Never green-on-stale. Never crashes on a failed poll.
//
// UNITS / probability only. NO $ P&L field. No edge claimed.
// CLV may be INSUFFICIENT_DATA when no closing line was captured.

import { useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, isUnavailable, type PaperTrailRow, type PaperTrail } from "@/lib/p5api";
import type { Unavailable } from "@/lib/types";
import { useLiveData } from "@/lib/useLiveData";
import { ExecutionDetail } from "@/components/paper_pm/ExecutionDetail";
import { toBetId } from "@/components/paper_pm/PmTradeRow";
import { ExecutionTrail } from "@/components/execution/ExecutionTrail";
import { paperRowToExecutionTrail } from "@/components/paper_pm/paperTrailAdapter";
import { humanizeMatchup } from "@/lib/betdesc";

// ---------------------------------------------------------------------------
// matchRow -- find the row matching the URL betId.
// toBetId encodes sport|game_id|market|side|book.
// ---------------------------------------------------------------------------

function matchRow(rows: PaperTrailRow[], betId: string): PaperTrailRow | null {
  const target = decodeURIComponent(betId);
  // try exact match first
  for (const r of rows) {
    if (decodeURIComponent(toBetId(r)) === target) return r;
  }
  // fallback: the betId prefix (sport|game_id) matches
  const prefix = target.split("|").slice(0, 2).join("|");
  for (const r of rows) {
    const id = decodeURIComponent(toBetId(r));
    if (id.startsWith(prefix)) return r;
  }
  return null;
}

// ---------------------------------------------------------------------------
// fmtAge -- compact human-readable last-updated age label.
// ---------------------------------------------------------------------------

function fmtAge(ageSec: number | null, isStaleOrErr: boolean): string {
  if (ageSec === null) return "checking";
  const label =
    ageSec < 5
      ? "just now"
      : ageSec < 60
      ? `${ageSec}s ago`
      : `${Math.round(ageSec / 60)}m ago`;
  return isStaleOrErr ? `stale: ${label}` : label;
}

// ---------------------------------------------------------------------------
// BetDetailPage
// ---------------------------------------------------------------------------

export default function BetDetailPageClient() {
  const params = useParams<{ betId: string }>();
  const betId = params?.betId ?? "";

  // Fetcher: GET the full trail (returns trail or unavailable sentinel).
  const fetcher = useCallback(
    async (signal: AbortSignal): Promise<PaperTrail | Unavailable> => {
      const t = await api.getPaperTrail({ limit: 2000 }, signal);
      if (isUnavailable(t)) {
        return {
          status: "unavailable",
          reason: (t as Unavailable).reason ?? "unavailable",
        } as Unavailable;
      }
      return t as PaperTrail;
    },
    [],
  );

  const { data, ageSec, isStale, error, isLoading } = useLiveData<PaperTrail>(
    fetcher,
    {
      // Open trades may change status; 30s is a good cadence for both.
      intervalMs: 30_000,
      staleAfterSec: 90,
    },
  );

  // Resolve the row from last-good trail (retained across failed polls by useLiveData).
  const row = useMemo<PaperTrailRow | null>(() => {
    if (!betId || !data) return null;
    return matchRow(data.trail, betId);
  }, [data, betId]);

  // Show loading placeholder only during the very first fetch (no last-good data yet).
  const showLoading = isLoading && data === null;

  // Derive error message for ExecutionDetail:
  //   - First poll failed (no last-good data) -> show reason.
  //   - Data loaded but bet not found -> show not-found message.
  //   - Stale / error WITH last-good row -> DON'T hide the row; badge shows stale.
  const rowError: string | null = (() => {
    if (showLoading) return null;
    if (data === null && error) return error;
    if (data !== null && !row) {
      return `trade not found: ${decodeURIComponent(betId)}`;
    }
    return null;
  })();

  // Stale-or-error flag drives the freshness badge colour.
  const isStaleOrErr = isStale || (error !== null && data !== null);

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <nav aria-label="breadcrumb" className="mb-5">
        <ol className="flex items-center gap-2 text-[11px] text-slate-500">
          <li>
            <Link href="/paper" className="hover:text-slate-300">
              PM trail
            </Link>
          </li>
          <li aria-hidden="true">/</li>
          <li className="font-mono text-slate-400">
            {row ? humanizeMatchup(row.matchup || row.game_id) : decodeURIComponent(betId)}
          </li>
        </ol>
      </nav>

      {/* Freshness badge (LiveBadge-equivalent inline indicator).
          Honesty rails:
            - Never green-on-stale: amber colour when isStale or error with last-good.
            - Green pulse ONLY when live (!isStale, no error, has data).
            - "checking" when no data yet (never "loading" / never red-failed).
            - data-testid lets tests assert the element is present. */}
      <div className="mb-4 flex items-center justify-end">
        <span
          data-testid="bet-detail-last-updated"
          className={[
            "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-mono",
            isStaleOrErr
              ? "border-amber-800/50 bg-amber-950/40 text-amber-400"
              : ageSec !== null
              ? "border-slate-700 bg-slate-800/40 text-slate-500"
              : "border-slate-700/50 bg-slate-800/20 text-slate-600",
          ].join(" ")}
          role="status"
          aria-live="polite"
          aria-label={
            isStaleOrErr
              ? `Stale data${ageSec !== null ? `, ${ageSec}s old` : ""}`
              : ageSec !== null
              ? `Live data, updated ${ageSec}s ago`
              : "Checking for live data"
          }
        >
          {/* Green pulse dot -- only when live (not stale, no error, has age) */}
          {!isStaleOrErr && ageSec !== null && (
            <span className="relative flex h-2 w-2 shrink-0" aria-hidden="true">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
            </span>
          )}
          {/* Amber dot -- stale or error-with-last-good */}
          {isStaleOrErr && (
            <span
              className="h-2 w-2 shrink-0 rounded-full bg-amber-500"
              aria-hidden="true"
            />
          )}
          {/* Neutral dot -- checking (no data yet, no error) */}
          {ageSec === null && !isStaleOrErr && (
            <span
              className="h-2 w-2 shrink-0 rounded-full bg-slate-600"
              aria-hidden="true"
            />
          )}
          <span>{fmtAge(ageSec, isStaleOrErr)}</span>
        </span>
      </div>

      <ExecutionDetail
        row={row}
        loading={showLoading}
        error={rowError}
      />

      {/* ExecutionTrail: mounted below ExecutionDetail once the row is loaded.
          Shows line-shopping table (single taken-book row), Shin devig,
          and decision trail (tier / units / CLV) -- all via the pure adapter.
          UNITS only. No $ field. CLV may be INSUFFICIENT_DATA.
          On failed poll with last-good row, the trail is still visible. */}
      {!showLoading && row && (
        <ExecutionTrail
          className="mt-4"
          {...paperRowToExecutionTrail(row)}
        />
      )}
      {!showLoading && !row && (
        <ExecutionTrail
          className="mt-4"
          bookLines={[]}
          bestBook={null}
          devig={null}
          decision={null}
          stakeUnits={null}
          tier={null}
          clvStatus={null}
          modelProb={null}
          error={rowError ?? "trade not found"}
        />
      )}

      <div className="mt-6">
        <Link
          href="/paper"
          className="font-mono text-[11px] text-slate-500 hover:text-slate-300"
        >
          &larr; back to PM trail
        </Link>
      </div>
    </div>
  );
}
