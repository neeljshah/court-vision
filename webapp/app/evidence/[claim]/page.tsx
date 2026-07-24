// app/evidence/[claim]/page.tsx -- one evidence claim (T2.4). Static export:
// generateStaticParams emits the 22 claim slugs (retraction-story owns its own
// static route and is excluded), and buildClaimPage parses that claim's markdown
// + joins the staged artifact index at build time. No client fetch, no /api.

import { notFound } from "next/navigation";
import { listClaimSlugs, buildClaimPage } from "@/lib/evidence.server";
import { ClaimPage } from "@/components/evidence/ClaimPage";

// Only the known slugs build; an unknown /evidence/<x> 404s rather than being
// server-rendered (there is no server in an export).
export const dynamicParams = false;

export function generateStaticParams() {
  return listClaimSlugs().map((claim) => ({ claim }));
}

export function generateMetadata({ params }: { params: { claim: string } }) {
  const props = buildClaimPage(params.claim);
  return {
    title: props ? `Evidence / ${props.title}` : "Evidence",
    description: props?.lede || props?.claim?.slice(0, 160) || "Evidence claim.",
  };
}

export default function EvidenceClaimPage({
  params,
}: {
  params: { claim: string };
}) {
  const props = buildClaimPage(params.claim);
  if (!props) notFound();
  return <ClaimPage {...props} />;
}
