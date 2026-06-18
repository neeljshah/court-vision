import { Card, CardContent } from "@/components/ui/card";
import type { SlatePayload } from "@/lib/api";
import type { GameRef } from "@/components/game/GameDetail";
import { BoardTable } from "@/components/board/BoardTable";

/** The primary BOARD screen: dense sortable/filterable odds grid. */
export function BoardScreen({
  sport,
  data,
  minEdge,
  loading,
  error,
  onOpenGame,
}: {
  sport: string;
  data: SlatePayload | null;
  minEdge: number;
  loading: boolean;
  error: string | null;
  onOpenGame?: (game: GameRef) => void;
}) {
  if (error) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-destructive">
          Could not reach the decision-support API: {error}
          <p className="mt-2 text-xs text-muted-foreground">
            Is serve.py running on port 8098? Start it with{" "}
            <code>python -m scripts.platformkit.frontend.serve</code>.
          </p>
        </CardContent>
      </Card>
    );
  }
  if (!data) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          {loading ? "Loading slate..." : "No data."}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <BoardTable sport={sport} rows={data.rows} minEdge={minEdge} onOpenGame={onOpenGame} />
      </CardContent>
      <div className="border-t border-border/60 px-4 py-2 text-[11px] text-muted-foreground">
        *Edge = model P(home) minus market-implied P(home), shown for decision support only.
        Arb % and best-line are <span className="font-medium">execution edges</span>{" "}
        (line-shopping), not a model money edge. Status: {data.status}
        {data.predictor_available === false ? " (predictor unavailable -- no fabricated numbers)" : ""}.
      </div>
    </Card>
  );
}
