import type { MetadataRoute } from "next";

// An explicit route keeps Next's file metadata from emitting an unprefixed link.
// Both product layouts declare the base-prefixed manifest URL.
export const dynamic = "force-static";
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

export function GET() {
  const manifest: MetadataRoute.Manifest = {
    name: "CourtVision Board",
    short_name: "CV Board",
    description: "Calibrated sports forecasts vs book prices. Paper intent logging only.",
    start_url: `${BASE_PATH}/games/`,
    scope: `${BASE_PATH}/`,
    display: "standalone",
    background_color: "#0C0F15",
    theme_color: "#0C0F15",
    icons: [
      { src: `${BASE_PATH}/brand/icon-192.png`, sizes: "192x192", type: "image/png", purpose: "any" },
      { src: `${BASE_PATH}/brand/icon-512.png`, sizes: "512x512", type: "image/png", purpose: "any" },
    ],
  };
  return Response.json(manifest, { headers: { "Content-Type": "application/manifest+json" } });
}
