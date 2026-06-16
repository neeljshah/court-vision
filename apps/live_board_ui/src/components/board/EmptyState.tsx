/** Centered placeholder shown when the board has no rows to display. */
import { CalendarOff } from "lucide-react";

interface EmptyStateProps {
  message?: string;
}

export function EmptyState({
  message = "Nothing scheduled for this selection. Try another sport or league.",
}: EmptyStateProps) {
  return (
    <div
      className="py-14 text-center text-muted flex flex-col items-center gap-4"
      role="status"
      aria-live="polite"
    >
      <CalendarOff className="w-12 h-12 text-muted" aria-hidden="true" />
      <h2 className="text-lg font-semibold text-muted">No games right now</h2>
      <p className="text-sm text-muted max-w-xs">{message}</p>
    </div>
  );
}
