"use client";

// OnboardingOverlay -- a "what is this & how to read it" guide behind a
// persistent Help affordance.
//
// It no longer auto-opens on a first visit: a modal over the landing page meant
// a cold visitor saw the guide instead of the scoreboard, its headline result
// and the evidence / analytics doors (QA pass 2026-10-20). The small fixed "?"
// Help button (bottom-right) opens it any time.
//
// It is DISMISSIBLE and NON-BLOCKING: Radix Dialog traps focus while open,
// closes on Escape / overlay-click / the Close button, and never gates the app.
// All copy is honest framing (units not $, calibration not edge, self-improve
// READY-inert, real-money DENY) -- it NEVER invents a number or a game.
//
// Bundle note: the dialog (Radix primitive + guide copy, OnboardingGuide.tsx)
// is dynamic-imported on the first Help press. Only this button ships with the
// root layout, so every terminal page loads ~25 KB raw less JS up front.
//
// ASCII only. <= 300 LOC.

import dynamic from "next/dynamic";
import { useRef, useState, type RefObject } from "react";
import { cn } from "@/lib/utils";

const OnboardingGuide = dynamic(
  () => import("./OnboardingGuide").then((m) => m.OnboardingGuide),
  { ssr: false },
);

function HelpButton({ onClick, buttonRef }: { onClick: () => void; buttonRef: RefObject<HTMLButtonElement> }) {
  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={onClick}
      aria-label="Open the how-to-read-this guide"
      className={cn(
        "fixed bottom-4 right-4 z-30 flex h-10 w-10 items-center justify-center",
        "rounded-full border border-border bg-card text-foreground",
        "transition-colors hover:bg-surface-2",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      <span aria-hidden className="font-data text-base font-semibold">
        ?
      </span>
    </button>
  );
}

export function OnboardingOverlay() {
  const [open, setOpen] = useState(false);
  // Once requested, the guide stays mounted (closed) so a second press is instant.
  const [requested, setRequested] = useState(false);
  // The guide opens without a Radix Dialog.Trigger, so it is told where focus goes back to.
  const helpRef = useRef<HTMLButtonElement>(null);

  return (
    <>
      <HelpButton
        buttonRef={helpRef}
        onClick={() => {
          setRequested(true);
          setOpen(true);
        }}
      />
      {requested && <OnboardingGuide open={open} setOpen={setOpen} returnFocusTo={helpRef} />}
    </>
  );
}
