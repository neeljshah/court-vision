import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SPORTS } from "@/lib/api";

export interface BoardControlsProps {
  sport: string;
  onSport: (s: string) => void;
  minEdge: number;
  onMinEdge: (n: number) => void;
  autoPoll: boolean;
  onAutoPoll: (b: boolean) => void;
  onRefresh: () => void;
  loading: boolean;
}

/** Sport selector (World Cup first), min-edge filter, auto-poll toggle, refresh. */
export function BoardControls(props: BoardControlsProps) {
  const { sport, onSport, minEdge, onMinEdge, autoPoll, onAutoPoll, onRefresh, loading } = props;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="w-44">
        <Select value={sport} onValueChange={onSport}>
          <SelectTrigger aria-label="Sport">
            <SelectValue placeholder="Sport" />
          </SelectTrigger>
          <SelectContent>
            {SPORTS.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        Min edge %
        <Input
          type="number"
          step="0.5"
          value={Number.isFinite(minEdge) ? minEdge : 0}
          onChange={(e) => onMinEdge(parseFloat(e.target.value) || 0)}
          className="h-8 w-20"
          aria-label="Minimum edge percent filter"
        />
      </label>

      <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={autoPoll}
          onChange={(e) => onAutoPoll(e.target.checked)}
          className="h-3.5 w-3.5 accent-[hsl(var(--primary))]"
        />
        Auto-poll 30s
      </label>

      <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
        <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
        Refresh
      </Button>
    </div>
  );
}
