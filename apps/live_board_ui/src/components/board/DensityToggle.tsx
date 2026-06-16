/** DensityToggle -- controlled icon button that switches row density.
 * Density state lives in App (single source of truth) so the toggle and the
 * board always agree; this component just renders + reports the toggle. */
import { Rows3, Rows2 } from "lucide-react";
import type { Density } from "@/hooks/useDensity";
import { cn } from "@/lib/utils";

interface DensityToggleProps {
  density: Density;
  onToggle: () => void;
}

export function DensityToggle({ density, onToggle }: DensityToggleProps) {
  const isComfortable = density === "comfortable";
  const nextLabel = isComfortable ? "Switch to compact rows" : "Switch to comfortable rows";
  const currentLabel = isComfortable ? "Currently comfortable rows" : "Currently compact rows";

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={nextLabel}
      title={nextLabel}
      className={cn(
        "rounded-md p-2 border border-line",
        "text-muted hover:text-txt hover:bg-surface2",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        "transition-colors"
      )}
    >
      {isComfortable ? (
        <Rows3 className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Rows2 className="h-4 w-4" aria-hidden="true" />
      )}
      <span className="sr-only">{currentLabel}</span>
    </button>
  );
}
