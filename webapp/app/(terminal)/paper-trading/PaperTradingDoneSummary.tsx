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
    ["Win", "done-win", summary?.nWin],
    ["Loss", "done-loss", summary?.nLoss],
    ["Push", "done-push", summary?.nPush],
    ["Void", "done-void", summary?.nVoid],
    ["Units staked", "done-units-staked", summary?.totalUnitsStaked],
  ] as const;
  return (
    <section data-testid="done-settled-summary" aria-label="Done and settled summary" className="mb-5 mt-6">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
        Done / settled summary
      </h2>
      {!loading && !summary && <Unavailable reason={error ?? "Paper history unavailable"} />}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {rows.map(([label, id, value]) => (
          <StatTile key={id} label={label} testId={id} loading={loading}
            value={loading || value == null ? EMPTY_CELL : id === "done-units-staked" ? value.toFixed(2) : String(value)}
            valueClass={value && value > 0 && id === "done-win" ? "text-success"
              : value && value > 0 && id === "done-loss" ? "text-danger" : "text-foreground"} />
        ))}
      </div>
    </section>
  );
}
