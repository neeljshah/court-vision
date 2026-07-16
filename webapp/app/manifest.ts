import type { MetadataRoute } from "next";

// PWA manifest so the Bet Board installs to a phone home screen.
// BASE_PATH matches lib/fetchHonest.ts -- next/image + metadata icons don't
// auto-prefix basePath in unoptimized export mode.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

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
      { src: `${BASE_PATH}/brand/icon-192.png`, sizes: "192x192", type: "image/png", purpose: "any" },
      { src: `${BASE_PATH}/brand/icon-512.png`, sizes: "512x512", type: "image/png", purpose: "any" },
    ],
  };
}
