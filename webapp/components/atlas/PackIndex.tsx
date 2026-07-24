// PackIndex.tsx -- 7-card grid for /atlas (T1.2). Server component: props are
// plain data from atlas.server.listPacks(), no client state needed.
//
// Mirrors the mockup's ".door" card (border, hover border-primary, big mono
// count) using the house Panel look instead of ad-hoc CSS. Each card links to
// /atlas/[sport] and carries the pack's ReceiptChip (source manifest + as_of).

import Link from "next/link";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import type { PackMeta } from "@/lib/atlas.server";

export function PackIndex({ packs }: { packs: PackMeta[] }) {
  if (packs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No atlas packs staged in public/data/showcase/ yet.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {packs.map((p) => (
        <Link
          key={p.slug}
          href={`/atlas/${p.slug}`}
          className="group border border-border bg-card p-5 transition-colors hover:border-primary/60"
        >
          <div className="microlabel">{p.sport}</div>
          <h2 className="mt-1 text-lg font-semibold text-foreground group-hover:text-primary">
            {p.label}
          </h2>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-data text-3xl tabular-nums text-primary">
              {p.count}
            </span>
            <span className="text-xs text-muted-foreground">entities</span>
            <ReceiptChip {...p.chip} />
          </div>
          <div className="mt-3 font-data text-[11px] text-faint">
            as of {p.asOf ?? "not yet measured on this clone"}
          </div>
        </Link>
      ))}
    </div>
  );
}
