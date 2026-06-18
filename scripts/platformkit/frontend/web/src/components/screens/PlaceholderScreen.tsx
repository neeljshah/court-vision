import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { SlatePayload, SlateRow } from "@/lib/api";

export interface PlaceholderScreenProps {
  title: string;
  description: string;
  data: SlatePayload | null;
  /** Filter the same slate rows into the rows relevant to this screen. */
  filter: (rows: SlateRow[]) => SlateRow[];
  /** Short label for each surfaced row's metric. */
  metric: (row: SlateRow) => string;
  emptyHint: string;
}

/**
 * Stub screen for Arbitrage / +EV / Bet-tracker tabs. Wired to the SAME /api/slate
 * data so the information architecture is real; the dedicated view is a TODO.
 */
export function PlaceholderScreen({
  title,
  description,
  data,
  filter,
  metric,
  emptyHint,
}: PlaceholderScreenProps) {
  const rows = data ? filter(data.rows) : [];
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>{title}</CardTitle>
          <Badge variant="muted">preview</Badge>
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{emptyHint}</p>
        ) : (
          <ul className="divide-y divide-border/60">
            {rows.map((r, i) => (
              <li key={`${r.matchup}-${i}`} className="flex items-center justify-between py-2.5">
                <span className="font-medium">{r.matchup}</span>
                <span className="font-mono text-xs text-muted-foreground">{metric(r)}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
