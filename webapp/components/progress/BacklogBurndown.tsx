"use client";

// BacklogBurndown -- the improvement-backlog burn-down (73 total -> remaining)
// plus a "what's next" strip (the AI's own next improvements). This is the
// COMPLETENESS axis of honest progress: the backlog shrinks as discovered work
// is closed. Closing an item is mostly recording a REJECT (a SUCCESS) or
// exposing an already-computed coherent market -- it is NOT an accuracy/edge
// climb. NO $ field anywhere.

import { Panel, Badge } from "@/components/p6/Primitives";
import { InfoTip } from "@/components/depth";

const clampPct = (x: number) => Math.min(100, Math.max(0, x));

export function BacklogBurndown({
  total,
  remaining,
}: {
  total: number | null;
  remaining: number | null;
}) {
  const t = typeof total === "number" ? total : null;
  const r = typeof remaining === "number" ? remaining : null;
  const closed = t !== null && r !== null ? Math.max(0, t - r) : null;
  const pct = t && closed !== null ? clampPct((closed / t) * 100) : 0;

  return (
    <Panel
      title="improvement backlog burn-down"
      right={
        <span className="inline-flex items-center gap-1.5">
          {t !== null && r !== null ? (
            <Badge tone="slate">
              {r} of {t} remaining
            </Badge>
          ) : null}
          <InfoTip
            text="The AI's own discovered backlog. It shrinks as items are CLOSED -- mostly by recording a REJECT (a SUCCESS) or re-exposing an already-computed coherent market. Closing an item is COMPLETENESS, not an accuracy or $ edge climb."
            ariaLabel="what is the backlog burn-down?"
          />
        </span>
      }
    >
      {t === null || r === null ? (
        <p className="text-sm text-muted-foreground">
          backlog count unavailable -- honest empty, never a fabricated burn-down.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-end justify-between">
            <div>
              <div className="font-mono text-2xl tabular-nums text-foreground">
                {closed}
                <span className="text-sm text-muted-foreground"> / {t} closed</span>
              </div>
              <div className="text-[11px] text-muted-foreground">
                {r} remaining in the queue
              </div>
            </div>
            <div className="font-mono text-sm text-tier-a">{pct.toFixed(0)}%</div>
          </div>
          <div
            role="meter"
            aria-label={`backlog ${pct.toFixed(0)} percent closed`}
            aria-valuenow={Number(pct.toFixed(0))}
            aria-valuemin={0}
            aria-valuemax={100}
            className="relative h-2.5 w-full overflow-hidden rounded-full bg-slate-800/70"
          >
            <span
              aria-hidden
              className="h-full bg-tier-a/70"
              style={{ width: `${pct}%`, display: "block" }}
            />
          </div>
          <p className="text-[11px] leading-relaxed text-faint">
            Measurement-only: the backlog DISCOVERS + RANKS work; it never fixes,
            ships, or flips a flag. Most items close as a recorded REJECT (a
            success) -- the market is efficient.
          </p>
        </div>
      )}
    </Panel>
  );
}
