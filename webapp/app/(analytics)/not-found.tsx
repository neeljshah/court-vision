// app/(analytics)/not-found.tsx -- notFound() inside an /analytics segment (e.g. an
// unknown /analytics/m/<id>); the group layout supplies the shell.
import { NotFoundBody } from "@/components/shell/NotFoundBody";

export default function NotFound() {
  return <NotFoundBody />;
}
