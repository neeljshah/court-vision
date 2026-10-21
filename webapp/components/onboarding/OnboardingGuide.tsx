"use client";

// OnboardingGuide -- the "what is this & how to read it" dialog body. Split out
// of OnboardingOverlay so the Radix Dialog primitive and this copy are
// dynamic-imported on the first Help press instead of shipping with every
// terminal page (AppShell renders the overlay in the root layout). Copy is
// unchanged; honest framing only (units not $, calibration not edge).
//
// ASCII only. <= 300 LOC.

import Link from "next/link";
import type { RefObject } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

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
    href: "/desk",
    label: "Desk",
    purpose:
      "The paper desk (PAPER ONLY): tonight's priced games, exposure in UNITS " +
      "(not dollars), and the recorder's status -- never money advice.",
  },
  {
    href: "/paper-trading",
    label: "Paper record",
    purpose:
      "Every paper fill with its receipt, as counts and contracts. No closing-line " +
      "reading exists yet. Calibration is the claim; there is no profit claim.",
  },
  {
    href: "/desk/health",
    label: "Desk health",
    purpose:
      "The gate-verdict ledger (each tested signal's leak-free verdict), freshness, " +
      "and the night's refusals. A REJECT is a SUCCESS, not a failure.",
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


export function OnboardingGuide({ open, setOpen, returnFocusTo }: {
  open: boolean; setOpen: (open: boolean) => void; returnFocusTo?: RefObject<HTMLElement>;
}) {
  return (
      <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        className="max-h-[85vh] max-w-2xl overflow-y-auto rounded-none border-border bg-card shadow-none"
        // No Dialog.Trigger here: without this Radix hands focus to nothing and it lands on <body>.
        onCloseAutoFocus={(e) => {
          if (!returnFocusTo?.current) return;
          e.preventDefault();
          returnFocusTo.current.focus();
        }}
      >
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
                <Link
                  href={p.href}
                  onClick={() => setOpen(false)}
                  className={cn(
                    "block border border-border px-2.5 py-2 text-xs transition-colors",
                    "hover:bg-surface-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  )}
                >
                  <span className="font-data font-medium text-foreground">{p.label}</span>
                  <span className="ml-2 text-faint">{p.purpose}</span>
                </Link>
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
  );
}

export default OnboardingGuide;
