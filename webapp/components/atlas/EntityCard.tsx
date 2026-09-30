// EntityCard.tsx -- one entity's descriptive HTML card (T1.4).
//
// Server component. Renders the panel head (name + id + as-of), a stat grid of
// every key_number (one receipt chip per stat), and a card foot (sample floor
// + a link to the committed card PNG). Descriptive only -- no prediction, no
// edge. Mirrors mockups/atlas-entity.html; the honesty banner + floor note +
// cross-links live in the page, not here.

import { Panel, Num } from "@/components/ui/terminal";
import { ReceiptChip, type ReceiptChipProps } from "@/components/showcase/ReceiptChip";
import type { EntityCardProps } from "@/lib/atlas.server";

// next/image / <a> do not auto-prefix basePath in export mode -- prefix by hand
// (same landmine Nav.tsx documents). The card PNGs live at docs/img/atlas/... in
// the repo; the gate must stage them into webapp/public/docs/img/atlas/ for this
// link to resolve. ponytail: broken only until assets are staged -- a build
// concern flagged to the gate, not a runtime branch here.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

// Humanize a snake_case key_number into a readable, ASCII microlabel:
// career_pts_per36 -> "career pts / 36", career_fg3_pct -> "career fg3 %".
function humanize(key: string): string {
  return key
    .replace(/_per(\d+)/g, " / $1")
    .replace(/_pct\b/g, " %")
    .replace(/_/g, " ")
    .trim();
}

// A key_number that ends in _id is an identifier, not a stat -- it goes in the
// subtitle, never in a stat tile.
function isIdKey(key: string): boolean {
  return /(^|_)id$/.test(key);
}

// ponytail: mlb-pitching nests a breakdown object under some key_numbers
// (e.g. count_leverage_pct: {pitcher_ahead, even, ...}) instead of a scalar --
// flatten it to one readable line rather than "[object Object]".
function formatValue(v: unknown): string {
  if (v != null && typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, n]) => `${k}: ${n}`)
      .join(", ");
  }
  return String(v);
}

function record(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : null;
}

function published(value: unknown, decimals?: number): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return decimals === undefined ? String(value) : value.toFixed(decimals);
  }
  return typeof value === "string" && value ? value : "Not published";
}

function TimeBucketTable({ value, chip }: { value: unknown; chip: ReceiptChipProps }) {
  const rows = Array.isArray(value) ? value : [];
  return <section className="min-w-0 border-t border-border px-3.5 py-3">
    <div role="region" aria-label="Calibration by time bucket table scroll" tabIndex={0} className="overflow-x-auto">
      <table className="w-full min-w-[360px] text-left font-data text-sm">
        <caption className="mb-2 text-left font-semibold">Calibration by time bucket</caption>
        <thead><tr className="border-b border-border"><th scope="col">Time bucket</th><th scope="col" className="text-right">N rows</th><th scope="col" className="text-right">Observed outcome mean</th></tr></thead>
        <tbody>{rows.length ? rows.map((raw, index) => {
          const row = record(raw);
          return <tr key={index} className="border-b border-border/50">
            <th scope="row" className="py-1 text-left font-normal">{published(row?.bucket)}</th>
            <td className="text-right">{published(row?.n)}</td><td className="text-right">{published(row?.mean_y)}</td>
          </tr>;
        }) : <tr><td colSpan={3}>Not published</td></tr>}</tbody>
      </table>
    </div>
    <ReceiptChip {...chip} />
  </section>;
}

function VelocityTable({ value, chip }: { value: unknown; chip: ReceiptChipProps }) {
  const rows = record(value);
  const entries = rows ? Object.entries(rows) : [];
  return <section className="min-w-0 border-t border-border px-3.5 py-3">
    <div role="region" aria-label="Velocity percentiles by pitch type table scroll" tabIndex={0} className="overflow-x-auto">
      <table className="w-full min-w-[420px] text-left font-data text-sm">
        <caption className="mb-2 text-left font-semibold">Velocity percentiles by pitch type</caption>
        <thead><tr className="border-b border-border"><th scope="col">Pitch type</th><th scope="col" className="text-right">N pitches</th><th scope="col" className="text-right">P10 mph</th><th scope="col" className="text-right">P50 mph</th><th scope="col" className="text-right">P90 mph</th></tr></thead>
        <tbody>{entries.length ? entries.map(([type, raw]) => {
          const row = record(raw);
          return <tr key={type} className="border-b border-border/50">
            <th scope="row" className="py-1 text-left font-normal">{type}</th>
            <td className="text-right">{published(row?.n)}</td><td className="text-right">{published(row?.p10, 1)}</td>
            <td className="text-right">{published(row?.p50, 1)}</td><td className="text-right">{published(row?.p90, 1)}</td>
          </tr>;
        }) : <tr><td colSpan={5}>Not published</td></tr>}</tbody>
      </table>
    </div>
    <ReceiptChip {...chip} />
  </section>;
}

export function EntityCard({
  entity,
  label,
  keyNumbers,
  floors,
  asOf,
  pngHref,
  chip,
}: EntityCardProps) {
  const idEntry = Object.entries(keyNumbers).find(([k]) => isIdKey(k));
  const stats = Object.entries(keyNumbers).filter(([k]) => !isIdKey(k) && k !== "by_time_bucket" && k !== "velo_percentiles_by_type");
  const statChip: ReceiptChipProps = { ...chip };

  return (
    <Panel>
      <div className="flex items-baseline justify-between border-b border-border px-3.5 py-2">
        <span className="font-semibold text-foreground">
          {entity}
          <span className="microlabel ml-2 normal-case tracking-normal">
            {label}
            {idEntry ? ` -- ${idEntry[0]} ${idEntry[1]}` : ""}
          </span>
        </span>
        {asOf && <span className="microlabel text-faint">as of {asOf}</span>}
      </div>

      <div className="grid grid-cols-2 gap-px border-t border-border bg-border sm:grid-cols-3">
        {stats.map(([k, v]) => (
          <div key={k} className="bg-card px-4 py-3.5">
            <div className="microlabel">{humanize(k)}</div>
            <div className="mt-1 text-2xl">
              <Num>{formatValue(v)}</Num>
              <ReceiptChip {...statChip} />
            </div>
          </div>
        ))}
      </div>

      {Object.hasOwn(keyNumbers, "by_time_bucket") && <TimeBucketTable value={keyNumbers.by_time_bucket} chip={statChip} />}
      {Object.hasOwn(keyNumbers, "velo_percentiles_by_type") && <VelocityTable value={keyNumbers.velo_percentiles_by_type} chip={statChip} />}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-3.5 py-3">
        {floors && <span className="microlabel">sample floor -- {floors}</span>}
        {pngHref && (
          <a
            href={`${BASE_PATH}/${pngHref}`}
            download
            className="font-data text-xs text-faint hover:text-primary"
          >
            download card PNG -&gt; {pngHref}
          </a>
        )}
      </div>
    </Panel>
  );
}
