import type { MetadataRoute } from "next";

// PWA manifest so the Bet Board installs to a phone home screen.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "CourtVision Board",
    short_name: "CV Board",
    description:
      "Calibrated sports forecasts vs book prices. Paper intent logging only.",
    start_url: "/games",
    display: "standalone",
    background_color: "#0C0F15",
    theme_color: "#0C0F15",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
  };
}
