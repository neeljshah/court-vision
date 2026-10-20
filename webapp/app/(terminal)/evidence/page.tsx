// app/evidence/page.tsx -- Evidence index: the 4-bucket claim index.
// Server component, staged JSON only (evidence_index.json via evidence.server.ts).

import { buildClaimIndex } from "@/lib/evidence.server";
import { ClaimIndex } from "@/components/evidence/ClaimIndex";

// Counts come from the staged evidence_index.json so the description cannot
// drift from the page (it once said 22 while the index held 23).
const INDEX = buildClaimIndex();

export const metadata = {
  title: "Evidence",
  description:
    `The ${INDEX.claimCount} evidence claims, grouped into ${INDEX.buckets.length} buckets, each with its strongest receipt. ` +
    "Calibration and engineering evidence only -- no dollar edge claimed.",
};

export default function EvidencePage() {
  const index = INDEX;

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header>
        <p className="microlabel">evidence / claim index</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          Evidence
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {index.claimCount} claims, each backed by a cited artifact. No dollar
          edge, ROI, or bankroll result is claimed anywhere on this page --
          calibration and engineering evidence only.
        </p>
      </header>

      {index.buckets.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          evidence_index.json unavailable on this clone.
        </p>
      ) : (
        <ClaimIndex data={index} />
      )}
    </main>
  );
}
