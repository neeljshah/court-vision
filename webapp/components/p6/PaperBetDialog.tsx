"use client";

import { useState } from "react";
import type { BestBet, PaperPlaceResult } from "@/lib/p5api";
import { api, isUnavailable } from "@/lib/p5api";
import { Badge } from "./Primitives";
import { Num } from "@/components/ui/terminal";
import { cn, fmtPct, tierClass } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

type PlaceStatus = "idle" | "pending" | "confirmed" | "error";

// PaperBetDialog -- pre-filled (read-only) review of a single best-bet, with a
// "Record paper bet" action. PAPER ONLY: api.placePaper hits /api/paper/place,
// which sizes the stake server-side in UNITS (executed always false). NO $ field
// is sent or shown. best_book -> book, best_odds -> taken_decimal.
export function PaperBetDialog({
  bet,
  sport,
  gameId,
  onClose,
  onPlaced,
}: {
  bet: BestBet | null;
  sport: string | undefined;
  gameId: string;
  onClose: () => void;
  onPlaced: (b: BestBet) => void;
}) {
  const [status, setStatus] = useState<PlaceStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const open = bet != null;

  const reset = () => {
    setStatus("idle");
    setError(null);
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      onClose();
      reset();
    }
  };

  const submit = async () => {
    if (!bet || !sport) {
      setStatus("error");
      setError("missing sport context for this game");
      return;
    }
    setStatus("pending");
    setError(null);
    const res = await api.placePaper({
      sport,
      game_id: gameId,
      market_type: bet.market_type,
      side: bet.side,
      book: bet.best_book,
      taken_decimal: bet.best_odds,
    });
    if (isUnavailable(res)) {
      setStatus("error");
      setError(res.reason || "placement unavailable");
      return;
    }
    const r = res as PaperPlaceResult;
    if (r.status === "ok") {
      setStatus("confirmed");
      onPlaced(bet);
      reset();
    } else {
      setStatus("error");
      setError(r.reason || `placement ${r.status}`);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="w-full max-w-[480px] border-border bg-card"
        aria-label="Place paper bet"
      >
        <DialogHeader>
          <DialogTitle className="text-base">
            Place paper bet (paper only)
          </DialogTitle>
          <DialogDescription className="text-xs text-faint">
            Paper only -- executed is always false -- no $ amount. Stake is sized
            server-side in UNITS.
          </DialogDescription>
        </DialogHeader>

        {bet ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <Field label="Market">
              {bet.market_type}{" "}
              <span className="text-faint">{bet.side}</span>
            </Field>
            <Field label="Line">{bet.line != null ? bet.line : "--"}</Field>
            <Field label="Odds (dec)">
              <Num>{bet.best_odds.toFixed(2)}</Num>
            </Field>
            <Field label="Book">
              <span className="text-muted-foreground">{bet.best_book}</span>
            </Field>
            <Field label="Tier">
              <span
                className={cn(
                  "inline-flex border px-1.5 py-0.5 text-[10px] font-data",
                  tierClass(bet.tier || undefined),
                )}
              >
                {bet.tier || "--"}
              </span>
            </Field>
            <Field label="EV (vs devig)">
              <Num>{fmtPct(bet.ev)}</Num>
            </Field>
            <Field label="Model prob">
              <Num>{fmtPct(bet.model_prob, false)}</Num>
            </Field>
            <Field label="Stake (units)">
              <Num>{bet.stake_units.toFixed(2)}u</Num>
            </Field>
          </dl>
        ) : null}

        <div className="border border-border bg-surface-1 px-3 py-2 text-[11px] text-faint">
          This records a paper bet. No real money is placed. Stake is sized
          server-side in UNITS -- no $ amount is stored or displayed. CLV grades
          against the close; vs-close comparison is UNPROVEN (no in-play odds).
        </div>

        {status === "error" && error ? (
          <p
            className="text-xs text-danger"
            role="alert"
            aria-live="polite"
          >
            {error}
          </p>
        ) : null}
        {status === "confirmed" ? (
          <p
            className="text-xs text-tier-a"
            role="status"
            aria-live="polite"
          >
            Paper bet recorded (units only).
          </p>
        ) : null}

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleOpenChange(false)}
            disabled={status === "pending"}
          >
            Cancel
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={submit}
            disabled={status === "pending"}
          >
            {status === "pending" ? "Recording..." : "Record paper bet"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="microlabel">{label}</dt>
      <dd className="text-foreground">{children}</dd>
    </div>
  );
}
