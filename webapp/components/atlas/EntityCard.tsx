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
  const stats = Object.entries(keyNumbers).filter(([k]) => !isIdKey(k));
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
