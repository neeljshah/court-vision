import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ModuleDetail } from "@/components/analytics/modules/ModuleDetail";

const data = join(process.cwd(), "public", "data");
export type Mod = { id: string; title: string; one_line?: string; out_path: string; chart_path?: string; status: string; as_of: string };
export type Cite = { field?: string; value?: unknown; path?: string };
export type Insight = { title?: string; headline_insight?: string; what_it_means?: string; how_to_read?: string; caveat?: string; cited?: Cite[] };
export type Out = Record<string, unknown>;
const readJson = <T,>(path: string): T | null => { try { return JSON.parse(readFileSync(path, "utf-8")) as T; } catch { return null; } };
const manifest = () => readJson<{ modules: Mod[] }>(join(data, "showcase", "site_manifest.json"));
const subtitle = (mod: Mod, insight: Insight | null) => mod.one_line?.trim() && !/^descriptive_only$/i.test(mod.one_line) ? mod.one_line : insight?.headline_insight?.trim() || "";
export function generateStaticParams() { return (manifest()?.modules || []).map(mod => ({ id: mod.id })); }
export function generateMetadata({ params }: { params: { id: string } }): Metadata {
  const mod = manifest()?.modules.find(item => item.id === params.id);
  if (!mod) return { title: "Module", description: "A measured, receipt-cited analytics module." };
  const insight = readJson<Insight>(join(data, "insights", `${mod.id}.json`));
  return { title: insight?.title || mod.title, description: subtitle(mod, insight) || "A measured, receipt-cited analytics module." };
}
export default function ModulePage({ params }: { params: { id: string } }) {
  const mod = manifest()?.modules.find(item => item.id === params.id);
  if (!mod) notFound();
  const out = readJson<Out>(join(data, "showcase", `${mod.id}.json`)) || {};
  const insight = readJson<Insight>(join(data, "insights", `${mod.id}.json`));
  return <ModuleDetail mod={mod} out={out} insight={insight} subtitle={subtitle(mod, insight)} />;
}
