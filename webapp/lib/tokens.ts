/**
 * tokens.ts -- JS-accessible design token constants.
 *
 * Mirrors the CSS custom properties in globals.css so components that need
 * runtime color values (e.g. recharts) can reference tokens without
 * hardcoding hex literals.
 *
 * All values are CSS variable references; resolve at runtime via:
 *   getComputedStyle(document.documentElement).getPropertyValue('--tier-a')
 * or use the helper below.
 */

/** Resolve a CSS variable at runtime (client-side only). */
export function cssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

/** Tier label -> CSS variable name mapping. */
export const TIER_VAR: Record<"S" | "A" | "B" | "C", string> = {
  S: "--tier-s",
  A: "--tier-a",
  B: "--tier-b",
  C: "--tier-c",
};

/**
 * Tier label -> Tailwind utility class name.
 * Use for text color; e.g. className={tierTextClass(bet.tier)}
 */
export function tierTextClass(tier: string): string {
  switch (tier?.toUpperCase()) {
    case "S": return "text-tier-s";
    case "A": return "text-tier-a";
    case "B": return "text-tier-b";
    case "C": return "text-tier-c";
    default:  return "text-muted-foreground";
  }
}

/**
 * Tier label -> Tailwind border + background badge class.
 * Returns classes compatible with shadcn Badge variant="outline".
 */
export function tierBadgeClass(tier: string): string {
  switch (tier?.toUpperCase()) {
    case "S": return "border-tier-s text-tier-s bg-tier-s/10";
    case "A": return "border-tier-a text-tier-a bg-tier-a/10";
    case "B": return "border-tier-b text-tier-b bg-tier-b/10";
    case "C": return "border-tier-c text-tier-c bg-tier-c/10";
    default:  return "border-border text-muted-foreground";
  }
}

/**
 * Semantic status -> Tailwind text class.
 * success/warning/danger/info correspond to CSS vars defined in globals.css.
 */
export function statusTextClass(
  status: "success" | "warning" | "danger" | "info" | "muted"
): string {
  switch (status) {
    case "success": return "text-success";
    case "warning": return "text-warning";
    case "danger":  return "text-danger";
    case "info":    return "text-info";
    default:        return "text-muted-foreground";
  }
}

/** Canonical empty-cell marker -- ASCII safe, visually neutral. */
export const EMPTY_CELL = "--";

/** Standard "paper mode" label text. */
export const PAPER_MODE_LABEL = "PAPER MODE";
