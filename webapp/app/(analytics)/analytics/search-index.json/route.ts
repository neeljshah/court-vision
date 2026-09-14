import { snapshot } from "@/lib/analytics/labHelpers";
import { getResearchAnalyses } from "@/lib/analytics/researchData";
export const dynamic = "force-static";
export function GET() {
  const original = snapshot<{ records: unknown[] }>("search_records");
  const derived = getResearchAnalyses().map(a => ({
    id: `research-${a.id}`, title: a.title, subtitle: `${a.sport.toUpperCase()} / ${a.category} / Derived analysis`,
    href: `/analytics/research/${a.id}`, type: "module",
    keywords: [a.sport, a.category, a.description, a.source, ...a.fields.map(f => f.label)],
  }));
  return Response.json({ records: [...original.records, ...derived] });
}
