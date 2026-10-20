// app/(terminal)/not-found.tsx -- notFound() inside a site-group segment; the group
// layout already supplies the shell, so this is the shared 404 body only.
import { NotFoundBody } from "@/components/shell/NotFoundBody";

export default function NotFound() {
  return <NotFoundBody />;
}
