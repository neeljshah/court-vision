import { establishedDatasets } from "./labEstablished";
import { novelDatasets } from "./labNovel";
import { snapshot } from "./labHelpers";
import type { LabData, NovelCard } from "./labTypes";
export function getLabData(): LabData {
  return { datasets: [...establishedDatasets(), ...novelDatasets()], novel: snapshot<{ stats: NovelCard[] }>("novel_stats_index").stats };
}
