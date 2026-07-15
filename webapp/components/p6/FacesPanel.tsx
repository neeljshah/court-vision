"use client";

import { useCallback } from "react";
import {
  api,
  type Catalog,
  type CatalogFace,
  type AllHonest,
} from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, Unavailable, Badge } from "./Primitives";
import { Dot } from "@/components/ui/terminal";

// FacesPanel -- the unified-gateway face directory + the SINGLE honesty bit.
// Reads GET /api/catalog (the contracted faces: prediction / execution / lines /
// intelligence, each with version + capabilities + honest_note) and GET
// /api/status.all_honest (the one product-wide boolean).
//
// The ALL-HONEST badge is GREEN only when all_honest.ok === true. If ANY face
// violates a rail ($ key / fabricated edge / real money / stale-green) the bit
// flips false and we render RED ("honesty check failed") + list the violations --
// we NEVER hide a violation or paint it green. A missing/torn feed reads RED too
// (an ambiguous honesty state is dishonest, never green).
//
// Live polling: uses useLiveData (pause-on-hidden, last-good, stale badge).
// No bespoke setInterval.

export function FacesPanel() {
  const catalogFetcher = useCallback(
    (s: AbortSignal) => api.getCatalog(s) as Promise<Catalog>,
    [],
  );
  const {
    data: catalog,
    error: catErr,
  } = useLiveData<Catalog>(catalogFetcher, {
    intervalMs: 15000,
    staleAfterSec: 60,
  });

  const honestFetcher = useCallback(
    (s: AbortSignal) => api.getAllHonest(s) as Promise<AllHonest>,
    [],
  );
  const {
    data: honest,
    error: honestErr,
    isLoading: honestLoading,
  } = useLiveData<AllHonest>(honestFetcher, {
    intervalMs: 15000,
    staleAfterSec: 60,
  });

  // For HonestyBadge: pre-resolve window when loading=true + no data + no error.
  const honestPreResolve = honestLoading && !honest && !honestErr;

  return (
    <Panel
      title="gateway faces -- one model, many faces"
      right={
        <HonestyBadge
          honest={honest}
          err={honestErr}
          preResolve={honestPreResolve}
        />
      }
    >
      {catErr ? (
        <Unavailable reason={catErr} />
      ) : !catalog ? (
        <FacesSkeletonGrid />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {(catalog.faces || []).map((f) => (
              <FaceCard key={f.face} face={f} />
            ))}
          </div>

          <ViolationList honest={honest} err={honestErr} preResolve={honestPreResolve} />

          {catalog.honest_note ? (
            <p className="mt-3 text-[11px] text-faint">
              {catalog.honest_note}
            </p>
          ) : null}
        </>
      )}
    </Panel>
  );
}

// HonestyBadge -- the single ALL-HONEST bit. GREEN only on ok===true.
//
// Three distinct states:
//   1. preResolve (loading, no data, no error) -> NEUTRAL slate 'checking...' badge.
//   2. non-null err            -> feed torn / unavailable
//      -> RED 'honesty check unavailable'. Ambiguous is never green.
//   3. honest.ok === false     -> at least one violation
//      -> RED 'honesty check failed'.
//   4. honest.ok === true      -> all rails satisfied
//      -> GREEN 'all honest'.
function HonestyBadge({
  honest,
  err,
  preResolve,
}: {
  honest: AllHonest | null;
  err: string | null;
  preResolve: boolean;
}) {
  // State 1: pure pre-resolve / SSR null (no error yet)
  if (preResolve) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <Dot state="warn" />
        <Badge tone="slate">checking...</Badge>
      </span>
    );
  }
  // State 2: real feed error (catalog torn, network failure, etc.)
  if (err) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <Dot state="bad" />
        <Badge tone="red">honesty check unavailable</Badge>
      </span>
    );
  }
  // State 3: resolved honest bit
  if (!honest) {
    // last-good retained -- no data at all (should not happen post-resolve but be safe)
    return (
      <span className="inline-flex items-center gap-1.5">
        <Dot state="warn" />
        <Badge tone="slate">checking...</Badge>
      </span>
    );
  }
  if (honest.ok) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <Dot state="ok" />
        <Badge tone="green">all honest</Badge>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <Dot state="bad" />
      <Badge tone="red">honesty check failed</Badge>
    </span>
  );
}

function FaceCard({ face }: { face: CatalogFace }) {
  return (
    <div className="border border-border bg-surface-1 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-semibold uppercase text-foreground">
          {face.face}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">
          v{face.version}
        </span>
      </div>
      {face.title ? (
        <p className="mt-0.5 text-[11px] text-muted-foreground">{face.title}</p>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-1">
        {(face.capabilities || []).map((c) => (
          <span
            key={c}
            className="inline-flex rounded border border-slate-700 bg-slate-800/60 px-1.5 py-0.5 font-mono text-[9px] text-slate-400"
          >
            {c}
          </span>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <span className="font-mono text-[9px] text-faint">
          units: {face.units}
        </span>
        <span className="font-mono text-[9px] text-faint">
          edge_claimed: {String(face.edge_claimed)}
        </span>
        <span className="font-mono text-[9px] text-faint">
          real_money: {String(face.real_money_enabled)}
        </span>
      </div>
    </div>
  );
}

// FaceCardSkeleton -- matches the FaceCard layout; pulsing placeholder used
// while the catalog API call is in-flight. Neutral by design; no honesty bit.
function FaceCardSkeleton() {
  return (
    <div
      aria-hidden="true"
      className="animate-pulse border border-border bg-surface-1 p-3"
    >
      {/* header row: face name + version */}
      <div className="flex items-center justify-between gap-2">
        <div className="h-3 w-20 rounded bg-slate-800" />
        <div className="h-2.5 w-8 rounded bg-slate-800" />
      </div>
      {/* subtitle */}
      <div className="mt-1.5 h-2.5 w-32 rounded bg-slate-800/70" />
      {/* capability pills row */}
      <div className="mt-2 flex flex-wrap gap-1">
        <div className="h-4 w-12 rounded border border-slate-700 bg-slate-800/60" />
        <div className="h-4 w-16 rounded border border-slate-700 bg-slate-800/60" />
        <div className="h-4 w-10 rounded border border-slate-700 bg-slate-800/60" />
      </div>
      {/* meta row */}
      <div className="mt-2 flex flex-wrap gap-1.5">
        <div className="h-2.5 w-14 rounded bg-slate-800/60" />
        <div className="h-2.5 w-20 rounded bg-slate-800/60" />
        <div className="h-2.5 w-18 rounded bg-slate-800/60" />
      </div>
    </div>
  );
}

// FacesSkeletonGrid -- 2-up grid of FaceCardSkeleton placeholders that fills
// the catalog pre-resolve window. Matches the real faces grid (grid-cols-1
// sm:grid-cols-2) so there is zero layout shift on resolve.
function FacesSkeletonGrid() {
  return (
    <div
      role="status"
      aria-label="loading faces"
      data-testid="faces-skeleton-grid"
      className="grid grid-cols-1 gap-2 sm:grid-cols-2"
    >
      <FaceCardSkeleton />
      <FaceCardSkeleton />
    </div>
  );
}

// ViolationList -- surfaces the reason when the honesty check is non-ok.
//
// preResolve (loading=true, no data, no error) -> renders NOTHING.
// A non-null err (torn feed, network failure) -> red unavailable box with reason.
// honest.ok===false -> red failure box with per-face violation list.
// honest.ok===true  -> renders nothing (badge in the header already shows green).
function ViolationList({
  honest,
  err,
  preResolve,
}: {
  honest: AllHonest | null;
  err: string | null;
  preResolve: boolean;
}) {
  // Pure pre-resolve: no data and no error yet -> show nothing
  if (preResolve) return null;

  // Real feed error: ambiguous honesty is never green -- surface the reason
  if (err) {
    return (
      <div className="mt-3 border border-red-900/50 bg-red-950/30 px-3 py-2">
        <p className="font-mono text-[11px] text-red-400">
          honesty check unavailable -- an ambiguous honesty state is NOT green
        </p>
        <p className="mt-0.5 text-[10px] text-muted-foreground">{err}</p>
      </div>
    );
  }

  // All clear
  if (!honest || honest.ok) return null;

  return (
    <div className="mt-3 border border-red-900/50 bg-red-950/30 px-3 py-2">
      <p className="font-mono text-[11px] text-red-400">
        honesty check FAILED -- {honest.violations.length} violation
        {honest.violations.length === 1 ? "" : "s"} ({honest.n_faces} faces)
      </p>
      <ul className="mt-1 space-y-0.5">
        {honest.violations.map((v, i) => (
          <li key={i} className="font-mono text-[10px] text-amber-400">
            {v.face}: {v.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}
