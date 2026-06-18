import { Badge } from "@/components/ui/badge";
import type { Verdict } from "@/lib/api";

const VARIANT: Record<Verdict, React.ComponentProps<typeof Badge>["variant"]> = {
  MATCH: "success",
  CALIBRATED: "success",
  AHEAD: "success",
  BEHIND: "destructive",
  UNAVAILABLE: "muted",
  UNKNOWN: "muted",
};

/** Honest calibration verdict tag (derived from the predictor's own honest_note). */
export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <Badge variant={VARIANT[verdict] ?? "muted"}>{verdict}</Badge>;
}
