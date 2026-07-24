// FigureWithSource.tsx -- a claim-page figure: a basePath-prefixed image with an
// honest source caption and (optionally) a receipt chip. Thin, server-renderable,
// tokens only. Images resolve to the staged public tree (img/showcase/<base>) that
// evidence.server produces, so no C:/Users path can ever render.

import { ReceiptChip, type ReceiptChipProps } from "@/components/showcase/ReceiptChip";

// Static-export basePath landmine (same as Nav.tsx / lib/fetchHonest.ts): asset
// URLs must carry the /court-vision prefix at build time.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

export function FigureWithSource({
  src,
  alt,
  caption,
  chip,
}: {
  /** Repo-relative staged path, e.g. "img/showcase/pitch_sequencing.png". */
  src: string;
  alt: string;
  caption?: string;
  chip?: ReceiptChipProps;
}) {
  return (
    <figure className="m-0 border border-border bg-card">
      {/* ponytail: plain <img>, not next/image -- static export has no image
          optimizer, and the raw asset is exactly what ships. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`${BASE_PATH}/${src}`}
        alt={alt}
        loading="lazy"
        className="block h-auto w-full max-w-full"
      />
      {(caption || chip) && (
        <figcaption className="flex items-baseline gap-1 border-t border-border px-3 py-2 text-[11px] leading-relaxed text-faint">
          <span>{caption}</span>
          {chip && <ReceiptChip {...chip} />}
        </figcaption>
      )}
    </figure>
  );
}
