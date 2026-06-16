/**
 * App.tsx -- Root composition for the live sports decision-support board.
 * Wires sport/league state, polling hook, search + live-only filter, and all panel components.
 * Sport is deep-linkable via ?sport= so a view can be shared / bookmarked.
 * Tap-to-detail: clicking a row opens GameDetailDialog for that BoardRow.
 * No $ edge, ROI, or retracted numbers appear here or in any child import.
 */
import { useEffect, useMemo, useState } from "react";
import type { BoardRow, Sport } from "@/types/board";
import { SOCCER_LEAGUES, SPORTS } from "@/types/board";
import { useBoard } from "@/hooks/useBoard";
import { filterRows } from "@/lib/filter";
import { useScoreFlash } from "@/hooks/useScoreFlash";
import { useDensity } from "@/hooks/useDensity";
import type { SortMode } from "@/lib/sort";

import { Header } from "@/components/board/Header";
import { ThemeToggle } from "@/components/board/ThemeToggle";
import { DensityToggle } from "@/components/board/DensityToggle";
import { SportTabs } from "@/components/board/SportTabs";
import { LeagueSelect } from "@/components/board/LeagueSelect";
import { StampBar } from "@/components/board/StampBar";
import { FilterBar } from "@/components/board/FilterBar";
import { Disclaimer } from "@/components/board/Disclaimer";
import { LoadingState } from "@/components/board/LoadingState";
import { ErrorState } from "@/components/board/ErrorState";
import { EmptyState } from "@/components/board/EmptyState";
import { BoardTable } from "@/components/board/BoardTable";
import { LegendDialog } from "@/components/board/LegendDialog";
import { GameDetailDialog } from "@/components/board/GameDetailDialog";
import { SortSelect } from "@/components/board/SortSelect";

const VALID_SPORTS = SPORTS.map((s) => s.value);

/** Read the initial sport from ?sport= (defaults to mlb), SSR-safe. */
function initialSport(): Sport {
  if (typeof window === "undefined") return "mlb";
  const q = new URLSearchParams(window.location.search).get("sport");
  return q && VALID_SPORTS.includes(q as Sport) ? (q as Sport) : "mlb";
}

export default function App() {
  const [sport, setSport] = useState<Sport>(initialSport);
  const [league, setLeague] = useState<string>(SOCCER_LEAGUES[0].value);
  const [query, setQuery] = useState<string>("");
  const [liveOnly, setLiveOnly] = useState<boolean>(false);
  const [selected, setSelected] = useState<BoardRow | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("default");

  const { density, toggle: toggleDensity } = useDensity();

  // Keep the URL in sync so the current sport is shareable/bookmarkable.
  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("sport", sport);
    window.history.replaceState(null, "", url);
  }, [sport]);

  // Reset filter state and selected row whenever sport changes.
  useEffect(() => {
    setQuery("");
    setLiveOnly(false);
    setSelected(null);
  }, [sport]);

  const { data, error, loading, refreshing, refresh, stale } = useBoard(
    sport,
    sport === "soccer" ? league : undefined,
  );

  const allRows = useMemo(() => data?.rows ?? [], [data]);
  const liveCount = useMemo(
    () => allRows.filter((r) => r.state === "in").length,
    [allRows],
  );

  // Single memoized pass: filter once, derive section counts from the result so
  // typing in search / each 25s poll does not trigger 5 redundant O(n) scans.
  const { filtered, filteredLiveCount, filteredUpcomingCount, filteredFinishedCount } =
    useMemo(() => {
      const f = filterRows(allRows, query, liveOnly);
      return {
        filtered: f,
        filteredLiveCount: f.filter((r) => r.state === "in").length,
        filteredUpcomingCount: f.filter((r) => r.state === "pre").length,
        filteredFinishedCount: f.filter((r) => r.state === "post").length,
      };
    }, [allRows, query, liveOnly]);

  const flashKeys = useScoreFlash(allRows);

  const showFilterBar = Boolean(data) && allRows.length > 0;
  const showEmpty = !loading && !error && data && allRows.length === 0;
  const showFilterEmpty = data && allRows.length > 0 && filtered.length === 0;
  const showTable = data && allRows.length > 0 && filtered.length > 0;

  return (
    <div className="min-h-screen overflow-x-hidden bg-bg text-txt">
      <Header>
        <div className="flex items-center gap-1">
          <DensityToggle density={density} onToggle={toggleDensity} />
          <ThemeToggle />
        </div>
      </Header>

      <main className="mx-auto max-w-5xl px-3 pb-20 pt-3">
        {/* Controls -- stack on mobile, single row from sm up. */}
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <SportTabs sport={sport} onChange={setSport} />

          <LegendDialog />

          {sport === "soccer" && (
            <LeagueSelect league={league} onChange={setLeague} />
          )}

          <SortSelect value={sortMode} onChange={setSortMode} />

          <div className="sm:ml-auto">
            <StampBar
              generatedAt={data?.generated_at ?? null}
              liveCount={filteredLiveCount}
              upcomingCount={filteredUpcomingCount}
              finishedCount={filteredFinishedCount}
              refreshing={refreshing}
              onRefresh={refresh}
              stale={stale}
              connectionIssue={Boolean(error && data)}
            />
          </div>
        </div>

        {/* Search + live-only filter row (only when rows exist) */}
        {showFilterBar && (
          <div className="mt-3">
            <FilterBar
              query={query}
              onQuery={setQuery}
              liveOnly={liveOnly}
              onLiveOnly={setLiveOnly}
              shown={filtered.length}
              total={allRows.length}
              liveCount={liveCount}
            />
          </div>
        )}

        {/* Honesty banner */}
        <div className="mt-3">
          <Disclaimer variant="banner" />
        </div>

        {/* Main content -- animate-fade-in on swap */}
        <div key={`${sport}-${league}`} className="mt-4 animate-fade-in">
          {loading && <LoadingState />}
          {error && !data && <ErrorState message={error} onRetry={refresh} />}
          {showEmpty && <EmptyState />}
          {showFilterEmpty && (
            <EmptyState message="No games match your filter." />
          )}
          {showTable && (
            <BoardTable
              rows={filtered}
              sport={sport}
              generatedAt={data.generated_at}
              onSelect={setSelected}
              flashKeys={flashKeys}
              density={density}
              sortMode={sortMode}
            />
          )}
        </div>
      </main>

      {/* Footer disclaimer */}
      <footer className="mx-auto max-w-5xl px-3 pb-6">
        <Disclaimer variant="footer" />
      </footer>

      {/* Tap-to-detail overlay -- rendered once outside main to avoid layout shift */}
      <GameDetailDialog
        row={selected}
        open={selected !== null}
        onOpenChange={(o) => { if (!o) setSelected(null); }}
      />
    </div>
  );
}
