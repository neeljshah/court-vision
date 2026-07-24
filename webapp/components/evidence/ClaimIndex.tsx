// ClaimIndex.tsx -- the 4-bucket claim index: each row is a claim + its
// strongest receipt. Links out to /evidence/<slug> (retraction-story routes
// to its own page). Server component -- no client state needed.

import Link from "next/link";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import type { ClaimIndex as ClaimIndexData } from "@/lib/evidence.server";

export function ClaimIndex({ data }: { data: ClaimIndexData }) {
  return (
    <div className="flex flex-col gap-6">
      {data.buckets.map((bucket) => (
        <Panel key={bucket.name}>
          <PanelHead title={bucket.name} />
          <ul className="divide-y divide-border" role="list">
            {bucket.claims.map((c) => (
              <li key={c.slug}>
                <Link
                  href={`/evidence/${c.slug}`}
                  className="flex items-start justify-between gap-4 px-3 py-2.5 hover:bg-surface-2"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-foreground">{c.title}</div>
                    {c.claim && (
                      <div className="mt-0.5 truncate text-[13px] text-muted-foreground">
                        {c.claim}
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1 pt-0.5">
                    <span className="hidden font-data text-[11px] text-faint sm:inline">
                      {c.receipt.label}
                    </span>
                    <ReceiptChip
                      sourceArtifact={c.receipt.source ?? "not yet measured"}
                      // The index has no per-claim date; the full receipt with
                      // its real as-of date lives on the claim page.
                      asOf={c.receipt.source ? "see claim page" : null}
                      verified={c.edgeClaimed ? undefined : "edge_claimed:false"}
                    />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      ))}
    </div>
  );
}
