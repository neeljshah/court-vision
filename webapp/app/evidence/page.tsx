// app/evidence/page.tsx -- Evidence index: the 4-bucket claim index.
// Server component, staged JSON only (evidence_index.json via evidence.server.ts).

import { buildClaimIndex } from "@/lib/evidence.server";
import { ClaimIndex } from "@/components/evidence/ClaimIndex";

export const metadata = {
  title: "Evidence",
  description:
    "The 22 evidence claims, grouped into 4 buckets, each with its strongest receipt. " +
    "Calibration and engineering evidence only -- no dollar edge claimed.",
};

export default function EvidencePage() {
  const index = buildClaimIndex();

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
