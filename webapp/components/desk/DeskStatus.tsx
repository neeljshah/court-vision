// DeskStatus.tsx -- the Record hub's status card, the qualification census summary
// and the NotClaimed block. Server components; every number carries its as-of and
// receipt. Dates are the receipts' own (no viewer clock). PAPER ONLY.

import type { Desk } from "@/lib/desk.server";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import { GateStatus, GateStatusLegend, ReceiptChip as KitReceiptChip, gateStatusesIn, isGateStatus } from "@/components/evidence";
import {
  CENSUS, CENSUS_SRC, UPTIME_SRC, ghBlob, minutesBetween, type Uptime,
} from "./deskExtras.server";

function Row({ label, value, asOf, src, verdict }: {
  label: string; value: string; asOf: string | null; src: string; verdict?: string | null;
}) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-border/50 px-3 py-2 sm:flex-row sm:items-baseline sm:gap-3">
      <dt className="text-xs text-muted-foreground sm:w-56 sm:shrink-0">{label}</dt>
      <dd className="flex flex-wrap items-baseline gap-2 text-sm text-foreground">
        <span>{value}</span>
        <span className="font-data text-xs text-faint">as of {asOf ?? "not stated"}</span>
        <ReceiptChip sourceArtifact={src} asOf={asOf} verified="descriptive_only" verdict={verdict ?? null}
          href={ghBlob(src)} />
      </dd>
    </div>
  );
}

/** The latest heartbeat rows in the export's desk status, aged against the export's own stamp. */
export function heartbeats(desk: Desk | null) {
  const st = desk?.health?.desk_status ?? {};
  return Object.entries(st).filter(([k]) => k.startsWith("heartbeat:") || k.startsWith("capture:")).map(([k, v]) => ({
    key: k, decision: v.decision ?? "not stated", reason: v.reason ?? "not stated", ts: v.ts,
    ageMin: minutesBetween(v.ts, desk?.generated_at_utc),
  }));
}

export function StatusCard({ desk, uptime }: { desk: Desk | null; uptime: Uptime | null }) {
  const nights = desk?.health?.nights ?? [];
  const last = nights[nights.length - 1];
  const books = heartbeats(desk).find((h) => h.key === "heartbeat:books_root");
  const exportAsOf = desk?.generated_at_utc?.slice(0, 10) ?? null;
  return (
    <dl data-testid="desk-status-card">
      {last ? (
        <Row label="Last scored night" asOf={desk?.date ?? null} src={`docs/evidence/forward/nights/${last.date}.json`}
          value={`${last.date} ${last.status ?? "status not stated"}${
            last.reasons?.length ? ` (${last.reasons.join(", ")})` : " (all steps ran)"}`} />
      ) : (
        <div><dt className="sr-only">Status</dt><dd className="px-3 py-2 text-xs text-stale">No night receipt is in the desk export, so the last night cannot be shown.</dd></div>
      )}
      {uptime ? (
        <>
          <Row label="Nights scored / days in window" asOf={uptime.asOf} src={UPTIME_SRC}
            value={`${uptime.scored} of ${uptime.days} days (${uptime.complete} COMPLETE, ${uptime.partial} PARTIAL); ${uptime.scheduled} days scheduled; window ${uptime.window}`} />
          <Row label="Scored-night share (host uptime)" asOf={uptime.asOf} src={UPTIME_SRC}
            value={`${(uptime.share * 100).toFixed(1)} pct of days, window ${uptime.window}`} />
        </>
      ) : (
        <div><dt className="sr-only">Status</dt><dd className="px-3 py-2 text-xs text-stale">The uptime receipt {UPTIME_SRC} could not be read at build time, so no uptime share is shown.</dd></div>
      )}
      {books ? (
        <Row label="Capture heartbeat (books root)" asOf={exportAsOf} src="webapp/public/data/desk/latest.json"
          value={`${books.decision} (${books.reason}) at ${books.ts ?? "time not stated"}${
            books.ageMin != null ? `, ${books.ageMin} min before the export was generated` : ""}`} />
      ) : (
        <div><dt className="sr-only">Status</dt><dd className="px-3 py-2 text-xs text-stale">The desk export carries no capture heartbeat, so its age cannot be shown.</dd></div>
      )}
    </dl>
  );
}

export function CensusSummary() {
  return (
    <div className="flex flex-col gap-2 px-3 py-2 text-xs" data-testid="census-summary">
      <p className="text-muted-foreground">
        Why 0 of {CENSUS.served} served games qualify ({CENSUS.window}). Qualification grades the captured tape,
        not the model.
      </p>
      <ul className="flex flex-col gap-1">
        {CENSUS.causes.map((c) => (
          <li key={c.cause}>
            <span className="font-data text-foreground">
              {isGateStatus(c.cause) ? <GateStatus token={c.cause} gloss={false} /> : c.cause}: {c.n} games
            </span>{" "}
            <span className="text-muted-foreground">-- {c.why}.</span>
          </li>
        ))}
      </ul>
      <GateStatusLegend tokens={gateStatusesIn(CENSUS.causes.map((c) => c.cause))} />
      <p className="text-faint">
        {CENSUS.causes.map((c) => c.n).join(" + ")} = {CENSUS.served}; PASS {CENSUS.pass}.{" "}
        <KitReceiptChip source={CENSUS_SRC} asOf={CENSUS.asOf} status="descriptive_only" />
      </p>
    </div>
  );
}

export function DeskNotClaimed() {
  return (
    <aside aria-label="What this record is not" data-testid="desk-not-claimed"
      className="border border-border bg-card px-3 py-3 text-xs text-muted-foreground">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-foreground">What this record is not</h2>
      <ul className="list-disc pl-4">
        <li>Not a verdict on the model: no scored cell has reached its 30-game floor and no game has qualified.</li>
        <li>Not an execution record: no order was placed; every fill is simulated on the recorded tape.</li>
        <li>Not a return figure: the desk counts fills and contracts only, in paper units.</li>
        <li>Not a closing-line reading: the fill receipts carry no closing price.</li>
      </ul>
    </aside>
  );
}
