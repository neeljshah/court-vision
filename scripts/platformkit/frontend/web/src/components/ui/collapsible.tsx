import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Minimal, dependency-free collapsible section (no extra radix package needed).
 * Used for the grouped bet sections in the game detail view.
 */
export function CollapsibleSection({
  title,
  badge,
  defaultOpen = true,
  children,
}: {
  title: React.ReactNode;
  badge?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="rounded-lg border border-border/60 bg-background/40">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left hover:bg-accent/40"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-sm font-medium">
          {title}
          {badge}
        </span>
        <ChevronDown
          className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? <div className="border-t border-border/60">{children}</div> : null}
    </div>
  );
}
