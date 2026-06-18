import { ShieldAlert } from "lucide-react";

const FALLBACK =
  "Decision-support only; markets efficient; no edge claimed; you place every bet.";

/** Persistent, always-visible honesty banner. Never hide this. */
export function HonestBanner({ note }: { note?: string | null }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.08)] px-4 py-2.5 text-xs text-[hsl(var(--warning))]">
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <p className="leading-relaxed">
        <span className="font-semibold">
          Decision-support only; markets efficient; no edge claimed; you place every bet.
        </span>{" "}
        {note && note !== FALLBACK ? <span className="opacity-80">{note}</span> : null}
      </p>
    </div>
  );
}
