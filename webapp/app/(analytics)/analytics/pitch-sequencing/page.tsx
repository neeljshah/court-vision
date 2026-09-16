import type { Metadata } from "next";
import { PitchSequencing } from "@/components/analytics/pitch-sequencing/PitchSequencing";
import { loadPitchSequencing } from "@/lib/analytics/pitchSequencing.server";
import "./pitch-sequencing.css";

export const metadata: Metadata = {
  title: "Pitch sequencing",
  description: "Published conditional next-pitch matrices by count class.",
};

export default function PitchSequencingPage() {
  const data = loadPitchSequencing();
  return <div className="ps-page"><p className="ps-kicker">MLB / Descriptive sequencing</p><h1>Published pitch transitions by count class.</h1><p className="ps-intro">This matrix records the published conditional frequency of a next pitch type given the previous pitch type, within a plate appearance. It is a descriptive view of the local Statcast pull.</p><PitchSequencing data={data} /></div>;
}
