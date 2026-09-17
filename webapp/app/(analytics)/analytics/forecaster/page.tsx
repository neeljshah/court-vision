import { ForecasterReport } from "./ForecasterReport";
import { loadForecasterArms } from "./forecaster.server";

export const metadata = {
  title: "The Forecaster",
  description: "Published calibration checks for pregame and in-game forecasts.",
};

export default function ForecasterPage() {
  return <ForecasterReport data={loadForecasterArms()} />;
}
