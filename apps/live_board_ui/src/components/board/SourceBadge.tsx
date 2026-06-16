/** SourceBadge: honest provenance pill for each board row.
 * Maps row.source -> Badge variant + a plain-language explanation exposed via the
 * native title + aria-label. Non-interactive on purpose: board rows are clickable
 * (open the detail dialog), so a nested focusable trigger here would be invalid;
 * the legend dialog + game-detail dialog carry the full provenance accessibly.
 * Never implies edge, value, or profit. */
import type { BoardRow } from "@/types/board";
import { Badge } from "@/components/ui/badge";

interface SourceBadgeProps {
  row: BoardRow;
}

interface BadgeConfig {
  variant: "model" | "market" | "muted";
  label: string;
  tooltip: string;
}

function getConfig(row: BoardRow): BadgeConfig {
  switch (row.source) {
    case "model":
      return {
        variant: "model",
        label: "MODEL",
        tooltip: "Our calibrated pregame win-prob (matchup is in-corpus).",
      };
    case "live-model":
      return {
        variant: "model",
        label: "MODEL - LIVE",
        tooltip: "Our calibrated in-game win-prob, updating live.",
      };
    case "market":
      return {
        variant: "market",
        label: "MARKET",
        tooltip: "Devigged market-implied probability (no in-corpus model).",
      };
    case "live-market":
      return {
        variant: "market",
        label: "MARKET - LIVE",
        tooltip: "Devigged market-implied probability, updating live.",
      };
    case "unavailable":
      if (row.market_odds != null) {
        return {
          variant: "market",
          label: "MARKET LINE",
          tooltip:
            "Raw market line shown; no model or devigged probability.",
        };
      }
      return {
        variant: "muted",
        label: "SCORE ONLY",
        tooltip:
          "No in-corpus model and no usable odds -> live score/clock only.",
      };
    default:
      // Exhaustiveness guard: any future RowSource still gets an honest pill.
      return {
        variant: "muted",
        label: "SCORE ONLY",
        tooltip:
          "No in-corpus model and no usable odds -> live score/clock only.",
      };
  }
}

export function SourceBadge({ row }: SourceBadgeProps) {
  const { variant, label, tooltip } = getConfig(row);

  return (
    <Badge variant={variant} title={tooltip} aria-label={`Source: ${label}. ${tooltip}`}>
      {label}
    </Badge>
  );
}
