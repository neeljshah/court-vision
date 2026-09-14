import { existsSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";

const SHOWCASE_DATA = join(process.cwd(), "public", "data", "showcase");
const SHOWCASE_IMAGES = join(process.cwd(), "public", "img", "showcase");
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";
const REPOSITORY = "https://github.com/neeljshah/court-vision";

type ManifestModule = {
  id: string;
  title: string;
  one_line?: string;
  out_path?: string;
  chart_path?: string | null;
  status?: string;
  as_of?: string | null;
  evidence_page?: string | null;
};

export type EvidenceChart = {
  id: string;
  title: string;
  description: string;
  status: "published" | "partial";
  asOf: string | null;
  imageSrc: string;
  sourceUrl: string;
  evidenceUrl: string | null;
};

function publicUrl(path: string): string {
  return `${REPOSITORY}/blob/master/${path}`;
}

function safePath(path: string | undefined): string | null {
  if (!path || path.includes("..") || path.startsWith("/")) return null;
  return path;
}

/** Reads the public manifest and admits only image assets staged for the site. */
export function getEvidenceCharts(): EvidenceChart[] {
  let modules: ManifestModule[] = [];
  try {
    const raw = JSON.parse(readFileSync(join(SHOWCASE_DATA, "site_manifest.json"), "utf8")) as {
      modules?: ManifestModule[];
    };
    modules = Array.isArray(raw.modules) ? raw.modules : [];
  } catch {
    return [];
  }

  return modules.flatMap((item) => {
    const chartPath = safePath(item.chart_path || undefined);
    const sourcePath = safePath(item.out_path);
    if (!chartPath || !sourcePath || !/^[a-z0-9_]+$/.test(item.id)) return [];
    const imageName = basename(chartPath);
    if (!existsSync(join(SHOWCASE_IMAGES, imageName))) return [];
    return [{
      id: item.id,
      title: item.title,
      description: item.one_line || "Published chart; see the linked source module for its recorded method.",
      status: item.status === "partial" ? "partial" : "published",
      asOf: item.as_of || null,
      imageSrc: `${BASE_PATH}/img/showcase/${imageName}`,
      sourceUrl: publicUrl(sourcePath),
      evidenceUrl: safePath(item.evidence_page || undefined) ? publicUrl(item.evidence_page!) : null,
    }];
  });
}

export const evidenceRepositoryUrl = REPOSITORY;
