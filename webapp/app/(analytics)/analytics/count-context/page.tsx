import type { Metadata } from "next";
import { CountContext } from "@/components/analytics/count-context/CountContext";
import { loadCountContext } from "@/lib/analytics/countContext.server";
import "./count-context.css";

export const metadata: Metadata = {
  title: "Count context",
  description: "Published MLB pitch mix and outcome proxies by count-leverage class.",
};

export default function CountContextPage() {
  const data = loadCountContext();
  return <div className="cc-page"><p className="cc-kicker">MLB / Descriptive count context</p><h1>Pitch mix by count class, with its real denominators.</h1><p className="cc-intro">This snapshot separates pitch frequency from conditional sequencing and keeps every published denominator beside its measurement. It describes the committed local Statcast pull; it is not a forecast.</p><CountContext data={data} /></div>;
}
