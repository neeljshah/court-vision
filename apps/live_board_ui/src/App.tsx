/**
 * App.tsx -- Root composition for the live sports decision-support board.
 * Wires sport/league state, the polling hook, and all panel components.
 * Sport is deep-linkable via ?sport= so a view can be shared / bookmarked.
 * No $ edge, ROI, or retracted numbers appear here or in any child import.
 */
import { useEffect, useState } from "react";
import type { Sport } from "@/types/board";
import { SOCCER_LEAGUES, SPORTS } from "@/types/board";
import { useBoard } from "@/hooks/useBoard";

import { Header } from "@/components/board/Header";
import { ThemeToggle } from "@/components/board/ThemeToggle";
import { SportTabs } from "@/components/board/SportTabs";
import { LeagueSelect } from "@/components/board/LeagueSelect";
import { StampBar } from "@/components/board/StampBar";
import { Disclaimer } from "@/components/board/Disclaimer";
import { LoadingState } from "@/components/board/LoadingState";
import { ErrorState } from "@/components/board/ErrorState";
import { EmptyState } from "@/components/board/EmptyState";
import { BoardTable } from "@/components/board/BoardTable";

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

  // Keep the URL in sync so the current sport is shareable/bookmarkable.
  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("sport", sport);
    window.history.replaceState(null, "", url);
  }, [sport]);

  const { data, error, loading, refreshing, refresh } = useBoard(
    sport,
    sport === "soccer" ? league : undefined,
  );

  const rows = data?.rows ?? [];
  const liveCount = rows.filter((r) => r.state === "in").length;
  const upcomingCount = rows.filter((r) => r.state === "pre").length;
  const finishedCount = rows.filter((r) => r.state === "post").length;

  return (
    <div className="min-h-screen overflow-x-hidden bg-bg text-txt">
      <Header>
        <ThemeToggle />
      </Header>

      <main className="mx-auto max-w-5xl px-3 pb-20 pt-3">
        {/* Controls -- stack on mobile, single row from sm up. */}
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <SportTabs sport={sport} onChange={setSport} />

          {sport === "soccer" && (
            <LeagueSelect league={league} onChange={setLeague} />
          )}

          <div className="sm:ml-auto">
            <StampBar
              generatedAt={data?.generated_at ?? null}
              liveCount={liveCount}
              upcomingCount={upcomingCount}
              finishedCount={finishedCount}
              refreshing={refreshing}
              onRefresh={refresh}
            />
          </div>
        </div>

        {/* Honesty banner */}
        <div className="mt-3">
          <Disclaimer variant="banner" />
        </div>

        {/* Main content -- animate-fade-in on swap */}
        <div key={`${sport}-${league}`} className="mt-4 animate-fade-in">
          {loading && <LoadingState />}
          {error && !data && <ErrorState message={error} onRetry={refresh} />}
          {!loading && !error && data && rows.length === 0 && <EmptyState />}
          {data && rows.length > 0 && (
            <BoardTable
              rows={data.rows}
              sport={sport}
              generatedAt={data.generated_at}
            />
          )}
        </div>
      </main>

      {/* Footer disclaimer */}
      <footer className="mx-auto max-w-5xl px-3 pb-6">
        <Disclaimer variant="footer" />
      </footer>
    </div>
  );
}
