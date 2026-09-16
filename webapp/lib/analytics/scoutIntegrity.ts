import { noticesForModules, type DataIntegrityNotice } from "./dataIntegrity";
import type { AskAnswer } from "./askSearch";

const MODULE_ID = /^[a-z0-9_]+$/;

function artifactModuleId(value: string): string | null {
  const artifact = value.split("->", 1)[0].trim().replaceAll("\\", "/");
  const file = artifact.split("/").at(-1) || "";
  const match = file.match(/^([a-z0-9_]+)\.json$/i);
  return match ? match[1].toLowerCase() : null;
}

/** Extracts exact JSON artifact ids; prose and non-JSON citations are ignored. */
export function sourceModuleIds(artifacts: readonly string[]): string[] {
  return Array.from(new Set(artifacts.flatMap(artifact => {
    const id = artifactModuleId(artifact);
    return id ? [id] : [];
  })));
}

export function scoutIntegrity(answer: AskAnswer): { moduleIds: string[]; notices: DataIntegrityNotice[] } {
  const declared = (answer.source_module_ids || []).filter(id => MODULE_ID.test(id));
  const moduleIds = Array.from(new Set([...declared, ...sourceModuleIds([answer.source_artifact])]));
  return { moduleIds, notices: noticesForModules(moduleIds) };
}
