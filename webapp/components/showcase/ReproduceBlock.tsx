"use client";

// ReproduceBlock.tsx -- the "reproduce on a fresh clone" fenced command with a
// copy button and an optional fresh-clone fallback note. Every verified number
// on the site is one command away from being re-derived; this renders that
// command in the house mono/panel idiom. Tokens only, no new dep.

import * as React from "react";
import { cn } from "@/lib/utils";

export function ReproduceBlock({
  command,
  note,
  className,
}: {
  command: string;
  note?: string;
  className?: string;
}) {
  const [copied, setCopied] = React.useState(false);

  function copy() {
    // ponytail: clipboard API only; no execCommand fallback -- every target
    // browser for a static export has it, and a failed copy just shows nothing.
    navigator.clipboard?.writeText(command).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => setCopied(false)
    );
  }

  return (
    <div className={cn("border border-border bg-card", className)}>
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <span className="microlabel">reproduce on a fresh clone</span>
        <button
          type="button"
          onClick={copy}
          className="border border-border px-2 py-px font-data text-[10px] text-faint hover:text-primary focus:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-label="copy reproduce command"
        >
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre className="m-0 overflow-x-auto px-3 py-2.5">
        <code className="font-data text-[13px] text-foreground">{command}</code>
      </pre>
      {note && (
        <p className="m-0 border-t border-border px-3 py-2 text-[11px] leading-relaxed text-faint">
          {note}
        </p>
      )}
    </div>
  );
}
