"use client";

// OnboardingOverlay -- a lightweight first-run "what is this & how to read it"
// guide PLUS a persistent Help affordance.
//
// First visit: the dialog auto-opens once (localStorage flag cv-onboarded), so a
// new reader gets the honest framing + a one-line purpose for every page before
// they explore. After that it stays dismissed, but a small fixed "?" Help button
// (bottom-right) re-opens it any time.
//
// It is DISMISSIBLE and NON-BLOCKING: Radix Dialog traps focus while open,
// closes on Escape / overlay-click / the Close button, and never gates the app.
// All copy is honest framing (units not $, calibration not edge, self-improve
// READY-inert, real-money DENY) -- it NEVER invents a number or a game.
//
// ASCII only. <= 300 LOC.

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "cv-onboarded";

// One honest line of "what this page is for" per product area. These mirror the
// Nav links so a reader can map the tour to the menu. No numbers, no $.
const PAGE_GUIDE: { href: string; label: string; purpose: string }[] = [
  {
    href: "/",
    label: "Home",
    purpose:
      "The front door: what CourtVision is, the DATA -> ... -> VALIDATION funnel, " +
      "live status, and the honest headline findings.",
  },
  {
    href: "/games",
    label: "Games",
    purpose:
      "Tonight's real slate as cards. Open a game for one coherent prediction, the " +
      "market surface, validated signals, and (when live) an in-game number.",
  },
  {
    href: "/risk",
    label: "Risk",
    purpose:
      "Descriptive portfolio risk in UNITS (not dollars): joint exposure, capped " +
      "sizing, risk-of-ruin as a descriptor -- never money advice.",
  },
  {
    href: "/progress",
    label: "Progress",
    purpose:
      "The honest 'getting better' view: validation coverage, gate verdicts, and " +
      "backlog over time. The model is STATIC -- this is NOT a live accuracy climb.",
  },
  {
    href: "/system",
    label: "System",
    purpose:
      "The full gate-verdict ledger (every signal tested, leak-free), the backlog, " +
      "and CLV over time. A REJECT is a SUCCESS, not a failure.",
  },
  {
    href: "/how-it-works",
    label: "How it works",
    purpose:
      "The funnel and validation discipline explained in plain language, with a " +
      "live honest example -- never a fabricated game.",
  },
];

// The four honest rails every reader should know before reading any number.
const RAILS: { term: string; line: string }[] = [
  {
    term: "Units, not dollars",
    line: "Every size is an abstract UNIT (probability-derived). There is no $ field anywhere.",
  },
  {
    term: "Calibration, not a market edge",
    line: "The honest win is matching the devigged close within noise. No profit edge is claimed.",
  },
  {
    term: "Self-improve: READY but INERT",
    line: "The auto-recalibration loop is built and human-gated OFF. The model does not move on its own.",
  },
  {
    term: "Real money: DENY",
    line: "Paper mode only. Real-money placement is denied by default; vs_close is UNPROVEN where no in-play price exists.",
  },
];

function HelpButton({ onClick }: { onClick: () => void }) {
  return (
    <button
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
  const [ready, setReady] = useState(false);

  // First-run detection -- only after mount (localStorage is client-only).
  useEffect(() => {
    let seen = true;
    try {
      seen = localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      seen = true;
    }
    if (!seen) setOpen(true);
    setReady(true);
  }, []);

  // Persist the "seen" flag the first time the guide closes, so it never
  // auto-opens again (but the Help button can always re-open it).
  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) {
      try {
        localStorage.setItem(STORAGE_KEY, "1");
      } catch {
        /* ignore -- non-blocking */
      }
    }
  };

  if (!ready) return null;

  return (
    <>
      <HelpButton onClick={() => setOpen(true)} />
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto rounded-none border-border bg-card shadow-none">
          <DialogHeader>
            <DialogTitle className="microlabel text-foreground">
              What is this &amp; how to read it
            </DialogTitle>
            <DialogDescription className="text-faint">
              CourtVision is a calibrated multi-sport prediction system. Honest
              decision-support only -- read these four rails first, then use the
              page map below.
            </DialogDescription>
          </DialogHeader>

          {/* Honest rails -- the framing that governs every number. */}
          <section aria-label="Honest framing">
            <h3 className="microlabel mb-2">The honest framing</h3>
            <ul className="flex flex-col gap-2">
              {RAILS.map((r) => (
                <li
                  key={r.term}
                  className="border border-border bg-surface-1 p-2.5 text-xs"
                >
                  <span className="font-data font-medium text-foreground">{r.term}.</span>{" "}
                  <span className="text-faint">{r.line}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* Page map -- one honest purpose line per product area. */}
          <section aria-label="Page guide" className="mt-1">
            <h3 className="microlabel mb-2">Where to look</h3>
            <ul className="flex flex-col gap-1.5">
              {PAGE_GUIDE.map((p) => (
                <li key={p.href}>
                  <a
                    href={p.href}
                    onClick={() => handleOpenChange(false)}
                    className={cn(
                      "block border border-border px-2.5 py-2 text-xs transition-colors",
                      "hover:bg-surface-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    )}
                  >
                    <span className="font-data font-medium text-foreground">{p.label}</span>
                    <span className="ml-2 text-faint">{p.purpose}</span>
                  </a>
                </li>
              ))}
            </ul>
          </section>

          <p className="mt-1 text-[11px] leading-relaxed text-faint">
            This guide is dismissible and non-blocking. Re-open it any time with
            the &quot;?&quot; button in the bottom-right corner.
          </p>
        </DialogContent>
      </Dialog>
    </>
  );
}
