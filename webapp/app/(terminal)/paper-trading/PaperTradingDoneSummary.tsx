"use client";

import { Unavailable } from "@/components/p6/Primitives";
import { StatTile, EMPTY_CELL, type DoneSummary } from "./paperTradingHelpers";

export function PaperTradingDoneSummary({ summary, loading, error }: {
  summary: DoneSummary | null;
  loading: boolean;
  error: string | null;
}) {
  const rows = [
    ["Total bets", "done-total", summary?.nTotal],
    ["Settled", "done-settled", summary?.nSettled],
    ["Push", "done-push", summary?.nPush],
    ["Void", "done-void", summary?.nVoid],
    ["Units staked", "done-units-staked", summary?.totalUnitsStaked],
  ] as const;
  return (
    <section data-testid="done-settled-summary" aria-label="Done and settled summary" className="mb-5 mt-6">
      <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-widest text-muted-foreground">
        Done / settled summary
      </h2>
      {!loading && !summary && <Unavailable reason={error ?? "Paper history unavailable"} />}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
        {rows.map(([label, id, value]) => (
          <StatTile key={id} label={label} testId={id} loading={loading}
            value={loading || value == null ? EMPTY_CELL : id === "done-units-staked" ? value.toFixed(2) : String(value)}
            note={id === "done-void" && summary?.nUnknown ? `${summary.nUnknown} graded with an unrecognised outcome` : undefined}
            valueClass="text-foreground" />
        ))}
      </div>
    </section>
  );
}
