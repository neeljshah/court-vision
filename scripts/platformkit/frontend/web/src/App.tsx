import { useState } from "react";
import { Activity } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fmtPct } from "@/lib/format";
import { useSlate } from "@/lib/useSlate";
import { HonestBanner } from "@/components/board/HonestBanner";
import { BoardControls } from "@/components/board/BoardControls";
import { BoardScreen } from "@/components/screens/BoardScreen";
import { PlaceholderScreen } from "@/components/screens/PlaceholderScreen";
import { GameDetail, type GameRef } from "@/components/game/GameDetail";
import type { SlateRow } from "@/lib/api";

export default function App() {
  const [sport, setSport] = useState("soccer_intl");
  const [minEdge, setMinEdge] = useState(0);
  const [autoPoll, setAutoPoll] = useState(true);
  const { data, loading, error, lastUpdated, reload } = useSlate(sport, autoPoll);
  const [activeGame, setActiveGame] = useState<GameRef | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  function openGame(game: GameRef) {
    setActiveGame(game);
    setDetailOpen(true);
  }

  return (
    <div className="board-shell min-h-screen">
      <header className="border-b border-border/60 px-6 py-4">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              <h1 className="text-lg font-semibold tracking-tight">
                CourtVision Board
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  multi-sport decision-support
                </span>
              </h1>
            </div>
            <span className="text-xs text-muted-foreground">
              {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "--"}
            </span>
          </div>
          <HonestBanner note={data?.honest_note} />
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-6 py-5">
        <div className="mb-4">
          <BoardControls
            sport={sport}
            onSport={setSport}
            minEdge={minEdge}
            onMinEdge={setMinEdge}
            autoPoll={autoPoll}
            onAutoPoll={setAutoPoll}
            onRefresh={reload}
            loading={loading}
          />
        </div>

        <Tabs defaultValue="board">
          <TabsList>
            <TabsTrigger value="board">Board</TabsTrigger>
            <TabsTrigger value="arb">Arbitrage</TabsTrigger>
            <TabsTrigger value="ev">+EV</TabsTrigger>
            <TabsTrigger value="tracker">Bet tracker / CLV</TabsTrigger>
          </TabsList>

          <TabsContent value="board">
            <BoardScreen
              sport={sport}
              data={data}
              minEdge={minEdge}
              loading={loading}
              error={error}
              onOpenGame={openGame}
            />
          </TabsContent>

          <TabsContent value="arb">
            <PlaceholderScreen
              title="Arbitrage feed"
              description="Cross-book arb opportunities (execution edge -- line-shopping, not a model edge). Surfaced from the same slate's arb_pct."
              data={data}
              filter={(rows: SlateRow[]) => rows.filter((r) => r.arb_pct !== null && r.arb_pct > 0)}
              metric={(r) => `arb ${fmtPct(r.arb_pct)}  (${r.best_home_book ?? "?"} / ${r.best_away_book ?? "?"})`}
              emptyHint="No arbitrage on the current slate (no multi-book odds corpus, or none priced as arb)."
            />
          </TabsContent>

          <TabsContent value="ev">
            <PlaceholderScreen
              title="+EV feed"
              description="Rows where the model diverges from the best available price. Decision-support only; no money edge is claimed."
              data={data}
              filter={(rows: SlateRow[]) =>
                rows.filter((r) => r.model_ev_best !== null && r.model_ev_best > 0)
              }
              metric={(r) => `EV ${fmtPct(r.model_ev_best, true)} @ ${r.best_home_book ?? "?"}`}
              emptyHint="No positive-EV rows on the current slate (or no multi-book odds present)."
            />
          </TabsContent>

          <TabsContent value="tracker">
            <PlaceholderScreen
              title="Bet tracker / CLV"
              description="Your logged 'I placed this' intents and their closing-line value. CLV (not ROI) is the honest yardstick. Full ledger view is a TODO."
              data={data}
              filter={() => []}
              metric={() => ""}
              emptyHint="Logged intents (via 'I placed this') will appear here with their CLV once the ledger read endpoint is wired."
            />
          </TabsContent>
        </Tabs>
      </main>

      <GameDetail game={activeGame} open={detailOpen} onOpenChange={setDetailOpen} />
    </div>
  );
}
