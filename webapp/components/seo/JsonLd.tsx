// components/seo/JsonLd.tsx -- renders one <script type="application/ld+json"> from a builder in
// lib/seo/jsonld.ts. Server-safe; React 18 leaves it where it is rendered (body), which
// structured-data consumers accept anywhere in the document.
import { serializeJsonLd, type JsonLd as JsonLdData } from "@/lib/seo/jsonld";

export function JsonLd({ data }: { data: JsonLdData | JsonLdData[] }) {
  // eslint-disable-next-line react/no-danger
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(data) }} />;
}

export default JsonLd;
