// HomeForwardStatus -- forward paper series status (P2.1 item 3) with the last night's
// receipt chip. Wording is the packet's licensed sentence (JOB_EVIDENCE_PACKET section 4).
import Link from "next/link";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import type { Desk } from "@/lib/desk.server";

export function HomeForwardStatus({ desk }: { desk: Desk | null }) {
  const nights = desk?.health?.nights ?? [];
  const last = nights.length ? nights[nights.length - 1] : null;
  return (
    <div className="metric border border-border bg-card p-3 text-sm" data-testid="forward-status">
      <p className="m-0 text-foreground">
        PAPER ONLY: a prospective, receipt-backed series has run since 2026-10-06. It has no
        calibration verdict yet.
      </p>
      <div className="mt-1 font-data text-xs text-muted-foreground">
        <span data-role="verdict" className="border border-border px-1.5 text-foreground">INSUFFICIENT</span>{" "}
        {last ? (
          <>
            <span data-role="n">last night {last.date}: {last.status ?? "status not recorded"}</span>
            {last.reasons?.length ? ` (${last.reasons.join(", ")})` : ""} &middot;{" "}
            <span data-role="asof">as of {desk!.date}</span>
            <span data-role="receipt">
              <ReceiptChip sourceArtifact="webapp/public/data/desk/latest.json" asOf={desk!.date}
                verified="descriptive_only" verdict="INSUFFICIENT" />
            </span>
          </>
        ) : (
          <span data-role="n">desk export not staged on this clone</span>
        )}{" "}
        &middot; <Link href="/desk/" className="text-primary underline underline-offset-2 hover:no-underline">night receipts</Link>
      </div>
    </div>
  );
}
