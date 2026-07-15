"use client";

import { api, type PaperTrail as PaperTrailEnvelope, type PaperTrailRow } from "@/lib/p5api";
import { useStream } from "@/lib/useStream";
import { P5_BASE } from "@/lib/p5api";
import { Panel, Unavailable, Badge, ModeDot } from "./Primitives";
import { Num } from "@/components/ui/terminal";
import { deriveResult, showClv as rowHasClv } from "./paper-history-utils";
import { cn, fmtPct } from "@/lib/utils";
import { EMPTY_CELL } from "@/lib/tokens";

// PaperTrail -- the live paper trail (open + settled) from /api/paper/trail,
// streamed over the /api/stream/paper SSE endpoint with a poll fallback. Shows
// EVERY trade on BOTH paths (settled history never vanishes on fallback, never
// truncated). UNITS / probability only -- raw model_prob, never a $ amount.
// A no-close / open bet renders pending/void, NEVER a 0-fill win.

const RESULT_TONE = {
  win: "green",
  loss: "red",
  void: "slate",
  pending: "amber",
} as const;

// The SSE frame and the poll body both resolve to a PaperTrailRow[]. The stream
// may emit {trail:[]} or the legacy {open:[]}; prefer the full trail so settled
// rows persist. The poll path fetches the canonical full trail directly.
function extractRows(data: unknown): PaperTrailRow[] {
  if (!data || typeof data !== "object") return [];
  const d = data as { trail?: PaperTrailRow[]; open?: PaperTrailRow[] };
  return d.trail ?? d.open ?? [];
}

export function PaperTrail() {
  const { data, mode } = useStream<PaperTrailEnvelope>({
    sseUrl: `${P5_BASE}/api/stream/paper`,
    pollFn: async (s) => {
      // Full trail (open + settled), high cap so history never truncates.
      const d = await api.getPaperTrail({ limit: 5000 }, s);
      return d as PaperTrailEnvelope;
    },
    pollMs: 6000,
  });

  const rows = extractRows(data);
  const status = (data as PaperTrailEnvelope | null)?.status;

  return (
    <Panel title="Live paper trail" right={<ModeDot mode={mode} />}>
      {!data ? (
        <p className="text-sm text-faint">connecting...</p>
      ) : status === "unavailable" ? (
        <Unavailable reason={(data as { reason?: string }).reason} />
      ) : rows.length === 0 ? (
        <p className="text-sm text-faint">No paper trades yet.</p>
      ) : (
        <div className="max-h-[420px] overflow-x-auto overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-card">
              <tr className="microlabel text-left">
                <th className="px-3 py-1.5">Matchup</th>
                <th className="px-3 py-1.5">Side</th>
                <th className="px-3 py-1.5 text-right">Model P</th>
                <th className="px-3 py-1.5 text-right">CLV</th>
                <th className="px-3 py-1.5 text-right">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {/* EVERY trade -- no slice. Settled history persists on both paths. */}
              {rows.map((r, i) => (
                <Row key={`${r.game_id}-${r.market_type}-${r.side}-${i}`} row={r} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-[11px] text-faint">
        Paper only -- executed is always false. Stakes are units; there is no
        dollar column. No $ edge is claimed.
      </p>
    </Panel>
  );
}

function Row({ row: r }: { row: PaperTrailRow }) {
  const res = deriveResult(r);
  // CLV only when graded against a (real or proxy) close; pending/void/no-close
  // renders "--", NEVER 0.0.
  const showClv = rowHasClv(r);
  return (
    <tr
      className={cn(
        "hover:bg-surface-2",
        res === "void" ? "text-muted-foreground" : "text-foreground",
      )}
    >
      <td className="px-3 py-1.5">
        <div className="font-medium">{r.matchup || r.game_id}</div>
        <div className="font-data text-[10px] text-faint">
          {r.sport}
          {r.tier ? ` - ${r.tier}` : ""}
        </div>
      </td>
      <td className="px-3 py-1.5 font-data">{r.side}</td>
      <td className="px-3 py-1.5 text-right">
        <Num>
          {r.model_prob != null ? `${(r.model_prob * 100).toFixed(1)}%` : EMPTY_CELL}
        </Num>
      </td>
      <td
        className={cn(
          "px-3 py-1.5 text-right",
          showClv
            ? (r.clv_pct as number) > 0
              ? "text-up"
              : (r.clv_pct as number) < 0
                ? "text-down"
                : "text-muted-foreground"
            : "text-muted-foreground",
        )}
      >
        {showClv ? (
          <Num>
            {r.clv_is_proxy ? <span className="text-stale">~</span> : null}
            {fmtPct(r.clv_pct as number)}
          </Num>
        ) : (
          <Num>{EMPTY_CELL}</Num>
        )}
      </td>
      <td className="px-3 py-1.5 text-right">
        <Badge tone={RESULT_TONE[res]}>{res}</Badge>
      </td>
    </tr>
  );
}
