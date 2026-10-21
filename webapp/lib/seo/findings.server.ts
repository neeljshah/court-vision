// lib/seo/findings.server.ts -- metadata for one T4 finding page, read from the finding's own
// data: the index entry (title, dek), its spec's packet verdicts over the staged artifact, the
// artifact's as-of, and the finding's social card. Build-time only (reads public/data).
//
//   export const metadata: Metadata = findingMetadata("shrinkage");
import type { Metadata } from "next";
import { FINDING_SPECS } from "@/components/analytics/findings/findingSpecs";
import { findingAsOf, packetVerdicts } from "@/components/analytics/findings/FindingTemplate";
import { findingsIndex } from "@/lib/analytics/findingsIndex";
import { findingMeta } from "@/lib/analytics/og";
import { loadArtifact } from "@/lib/showcase.server";
import { findingPageMeta } from "./families";

export function findingMetadata(slug: string): Metadata {
  const spec = FINDING_SPECS[slug];
  const entry = findingsIndex.find((f) => f.slug === slug);
  const artifactId = spec?.artifactId ?? entry?.artifactIds[0];
  const artifact = artifactId ? loadArtifact(artifactId) : null;
  const verdicts = spec && artifact ? packetVerdicts(spec, artifact) : [];
  const asOf = (artifact && findingAsOf(artifact)) || entry?.asOf || null;
  return findingPageMeta(
    { slug, title: entry?.title ?? spec?.title ?? slug, dek: entry?.dek ?? spec?.claim ?? "", verdicts, asOf },
    findingMeta(slug),
  );
}
