import { establishedDatasets } from "./labEstablished";
import { novelDatasets } from "./labNovel";
import { snapshot } from "./labHelpers";
import type { LabData, NovelCard } from "./labTypes";
export function getLabData(): LabData {
  const datasets = [...establishedDatasets(), ...novelDatasets()];
  const liveClock = datasets.find(dataset => dataset.id === "live-clock")!;
  const foresight = datasets.find(dataset => dataset.id === "market-foresight")!;
  const novel = snapshot<{ stats: NovelCard[] }>("novel_stats_index").stats.map(card => {
    if (card.module === "novel_live_clock_fraction") return { ...card, headline: liveClock.rows.map(row =>
      `${row.label}: LCF ${row.values.live_clock_fraction ?? "unavailable"} at ${row.definition?.threshold ?? "unavailable"} ${row.definition?.unit ?? "score units unavailable"} (${row.definition?.clockField ?? "unavailable"} clock; ${row.values.n_games_total ?? "unavailable"} usable score paths).`
    ).join(" ") + " Thresholds and clock units differ; these values do not rank sports." };
    if (card.module === "novel_market_foresight_premium") return { ...card, headline:
      Array.from(new Set(foresight.rows.map(row => row.group))).map(group => {
        const rows = foresight.rows.filter(row => row.group === group);
        const endpoints = rows.length > 1 ? [rows[0], rows[rows.length - 1]] : rows;
        return endpoints.map(row => `${row.label}: MFP ${row.values.mfp ?? "unavailable"} (${row.values.n ?? "unavailable"} checkpoint observations)`).join("; ");
      }).join(". ") + ". These endpoint snapshots have different observation counts and do not establish an in-game trend." };
    const artifact = snapshot<{ headline?: unknown }>(card.module);
    return { ...card, headline: typeof artifact.headline === "string" && artifact.headline.trim()
      ? artifact.headline : "Headline unavailable in the published artifact." };
  });
  return { datasets, novel };
}
