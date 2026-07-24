import { PaperHistory } from "@/components/p6/PaperHistory";

export const metadata = {
  title: "Paper Trade History",
};

// Paper-Trade History view. READ-ONLY over the P5 Auto-API (:8099). The
// canonical audit surface for the self-improving paper-trade loop: EVERY trade
// (open + settled) in one sortable / filterable table. UNITS / probability
// only -- there is NO dollar column or $ field anywhere on this page.
export default function PaperHistoryPage() {
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">
          Paper trade history{" "}
          <span className="font-mono text-muted-foreground">audit</span>
        </h1>
        <span className="font-mono text-[11px] text-faint">
          reads P5 Auto-API -- paper-only -- no $ claimed
        </span>
      </header>

      <PaperHistory />

      <footer className="mt-4 text-center text-[11px] text-faint">
        Paper only -- stakes are units. There is no dollar column and no ROI. No
        $ edge is claimed. CLV (better-number-than-close) is the only honest
        yardstick; vs-close is UNPROVEN where no in-play odds are available.
      </footer>
    </main>
  );
}
