// findingHref.ts -- the ONE href of a finding page. A slug whose route was retired
// (lib/redirects.ts: /analytics/findings/retraction/ -> /evidence/retractions/) links
// straight to its new home instead of landing on the redirect stub. No node:fs, so the
// client-safe papers helpers can import it.
import { resolveRedirect } from "@/lib/redirects";

export function findingHref(slug: string): string {
  const path = `/analytics/findings/${slug}/`;
  return resolveRedirect(path) ?? path;
}
