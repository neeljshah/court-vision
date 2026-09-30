import { isSnapshotMode } from "@/lib/fetchHonest";

// Scheduled time and feed health do not establish a game's phase.
// Archived phases must never be presented as current live status.
const PHASE_LABELS: Record<string, string> = {
  pre: "PREGAME",
  in: "LIVE",
  post: "DONE",
  in_progress: "LIVE",
  live: "LIVE",
};

export function GameStatusChip({ state }: { state?: string }) {
  const phase = state?.trim().toLowerCase();
  const label = isSnapshotMode
    ? "SNAPSHOT"
    : phase && Object.hasOwn(PHASE_LABELS, phase)
      ? PHASE_LABELS[phase]
      : "STATUS UNKNOWN";
  const description = isSnapshotMode
    ? "Published historical snapshot; current game status is not available."
    : label === "STATUS UNKNOWN"
      ? "Game status is not reported. Scheduled time does not establish game status."
      : `Reported game status: ${label.toLowerCase()}`;

  return (
    <span
      aria-label={description}
      title={description}
      className="inline-flex items-center border border-border px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider text-muted-foreground"
    >
      {label}
    </span>
  );
}
