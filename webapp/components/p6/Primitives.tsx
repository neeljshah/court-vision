"use client";

import type { ReactNode } from "react";
import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { PanelHead, Panel as TerminalPanel } from "@/components/ui/terminal";

// Panel -- p6 adapter over the Direction A terminal Panel/PanelHead.
// Accepts optional asOf/stale so panels can carry the freshness stamp
// (stale renders amber, never silently green).
export function Panel({
  title,
  right,
  children,
  className,
  asOf,
  stale,
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  asOf?: string | null;
  stale?: boolean;
}) {
  return (
    <TerminalPanel className={className}>
      <PanelHead title={title} right={right} asOf={asOf ?? undefined} stale={stale} />
      <div className="p-4">{children}</div>
    </TerminalPanel>
  );
}

// Unavailable -- the single, honest degraded state. NEVER a guessed number.
export function Unavailable({ reason }: { reason?: string }) {
  return (
    <div
      role="status"
      aria-label={reason ? `unavailable: ${reason}` : "unavailable"}
      className="flex flex-col gap-1 rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-3 text-sm"
    >
      <span className="font-mono text-amber-400">unavailable</span>
      {reason ? (
        <span className="text-xs text-muted-foreground">{reason}</span>
      ) : null}
    </div>
  );
}

// Badge -- small status pill.
// a11y: role="status" so the pill is exposed as a live-region status to AT;
// aria-label is derived from the text content when children is a plain string,
// so screen readers announce both the text AND the semantic role rather than
// relying on color alone to convey state. Non-string children (e.g. nested
// <span> wrappers) receive a generic role without an aria-label override.
export function Badge({
  children,
  tone = "slate",
}: {
  children: ReactNode;
  tone?: "slate" | "green" | "red" | "amber" | "gold";
}) {
  const tones: Record<string, string> = {
    slate: "bg-slate-800 text-slate-300 border-slate-700",
    green: "bg-tier-a/20 text-tier-a border-tier-a/40",
    red: "bg-red-950/40 text-red-400 border-red-900/50",
    amber: "bg-amber-950/30 text-amber-400 border-amber-900/50",
    gold: "bg-tier-s/20 text-tier-s border-tier-s/40",
  };
  const label = typeof children === "string" ? children : undefined;
  return (
    <span
      role="status"
      aria-label={label}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

// FreshnessBadge -- provenance/freshness from API as_of/source fields.
//
// HARD RAIL -- stale-never-green: a backend `status` string of "ok"/"fresh" is
// NOT trusted on its own. If we have an `asOf` timestamp we ALWAYS re-derive the
// age locally; a feed whose own generated_at is older than STALE_THRESHOLD_S can
// never read green, no matter what status the upstream claims. This closes the
// freshness-path gap where a stale snapshot stamped status="ok" went green.
export function FreshnessBadge({
  asOf,
  source,
  status,
}: {
  asOf?: string | null;
  source?: string | null;
  status?: string;
}) {
  if (!asOf && !source && !status) return null;
  let tone: "green" | "amber" | "slate" = "slate";
  if (status === "fresh" || status === "ok") tone = "green";
  else if (status === "stale" || status === "unknown") tone = "amber";
  // Re-derive from the feed's OWN age and take the more conservative tone:
  // green is permitted only when the age is genuinely fresh. A stale/unknown age
  // demotes a claimed-green to amber (never green-on-stale).
  if (asOf) {
    const ageT = ageTone(asOf);
    if (tone === "green" && ageT !== "green") {
      tone = ageT === "slate" ? "amber" : ageT;
    }
  }
  const ago = asOf ? timeAgoIso(asOf) : null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge tone={tone}>{status || (ago ? `as of ${ago}` : "live")}</Badge>
      {source ? (
        <span className="font-mono text-[10px] text-muted-foreground">{source}</span>
      ) : null}
    </span>
  );
}

export function timeAgoIso(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const secs = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const m = Math.floor(secs / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ---------------------------------------------------------------------------
// TickingFreshnessBadge -- self-updating age + tone without a new fetch.
//
// Renders "as of Ns ago" / "Nm ago" etc. and re-derives the tone every
// TICK_MS (30 s) so a once-fresh badge honestly degrades to amber/slate as
// real time passes. Uses fake-timer-friendly window.setInterval.
//
// Tone degradation schedule (measured from asOf):
//   < FRESH_THRESHOLD_S (5 min) --> green
//   < STALE_THRESHOLD_S (60 min)--> amber
//   >= STALE_THRESHOLD_S        --> slate (silent stale, no alarm)
//
// Props
//   asOf    ISO-8601 string. When absent / unparseable -> slate "unavailable".
//   source  Optional provenance label rendered in muted mono next to the pill.
//   tickMs  Override tick interval (default 30 000 ms). Exposed for testing.
// ---------------------------------------------------------------------------

const FRESH_THRESHOLD_S = 5 * 60;   // 5 min
const STALE_THRESHOLD_S = 60 * 60;  // 60 min
const DEFAULT_TICK_MS   = 30_000;

function ageTone(asOf: string | null | undefined): "green" | "amber" | "slate" {
  if (!asOf) return "slate";
  const t = Date.parse(asOf);
  if (Number.isNaN(t)) return "slate";
  const secs = Math.max(0, (Date.now() - t) / 1000);
  if (secs < FRESH_THRESHOLD_S) return "green";
  if (secs < STALE_THRESHOLD_S) return "amber";
  return "slate";
}

export function TickingFreshnessBadge({
  asOf,
  source,
  tickMs = DEFAULT_TICK_MS,
}: {
  asOf?: string | null;
  source?: string | null;
  tickMs?: number;
}) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!asOf) return;
    const id = window.setInterval(() => setTick((n) => n + 1), tickMs);
    return () => window.clearInterval(id);
  }, [asOf, tickMs]);

  // Suppress unused-variable lint; the tick value forces a re-render.
  void tick;

  if (!asOf) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <Badge tone="slate">unavailable</Badge>
      </span>
    );
  }

  const tone = ageTone(asOf);
  const label = timeAgoIso(asOf);

  return (
    <span
      className="inline-flex items-center gap-1.5"
      data-testid="ticking-freshness-badge"
    >
      <Badge tone={tone}>
        <span data-testid="ticking-age-label">{label}</span>
      </Badge>
      {source ? (
        <span className="font-mono text-[10px] text-muted-foreground">{source}</span>
      ) : null}
    </span>
  );
}

// ---------------------------------------------------------------------------
// ModeDot -- shows whether a panel is live over SSE or polling. A "disconnected"
// mode (live + poll fallback both failed) reads RED as "live feed unavailable"
// so a frozen panel is never presented as live.
export function ModeDot({
  mode,
}: {
  mode: "sse" | "poll" | "disconnected" | "idle";
}) {
  const map = {
    sse: { c: "bg-tier-a", t: "SSE" },
    poll: { c: "bg-amber-400", t: "POLL" },
    disconnected: { c: "bg-red-500", t: "live feed unavailable" },
    idle: { c: "bg-slate-600", t: "..." },
  } as const;
  const m = map[mode];
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground">
      <span className={cn("h-1.5 w-1.5 rounded-full", m.c)} />
      {m.t}
    </span>
  );
}
