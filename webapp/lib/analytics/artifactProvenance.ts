import siteManifest from "@/public/data/showcase/site_manifest.json";

type DateKind = "snapshot" | "observation_window";

type ManifestModule = {
  id: string;
  out_path: string;
};

const publishedArtifacts = new Set(
  (siteManifest.modules as ManifestModule[]).flatMap((entry) => [
    `${entry.id}.json`,
    fileName(entry.out_path),
  ])
);

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() || "";
}

function basePath(): string {
  return (process.env.NEXT_PUBLIC_BASE_PATH || "").replace(/\/$/, "");
}

/** Returns the exported JSON URL only for artifacts listed in the committed manifest. */
export function artifactUrl(source: string | null | undefined, base = basePath()): string | null {
  if (!source) return null;
  const name = fileName(source.split(/[?#]/, 1)[0]);
  if (!name || !publishedArtifacts.has(name)) return null;
  return `${base}/data/showcase/${name}`;
}

/** Labels dates by meaning so a snapshot stamp is never presented as an observation period. */
export function provenanceDate(value: string | null | undefined, kind: DateKind = "snapshot"): string {
  if (!value) return "date not published";
  if (/^(snapshot generated:|observation window:|date not published$)/.test(value)) return value;
  const date = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:/.test(value) ? value.slice(0, 10) : value;
  return kind === "observation_window" ? `observation window: ${date}` : `snapshot generated: ${date}`;
}
