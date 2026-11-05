import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <section className="space-y-2">
      <h2 className="text-xl font-semibold tracking-tight">Page not found</h2>
      <p className="text-slate-600">The page you are looking for does not exist.</p>
      <Link to="/" className="text-sm font-medium text-slate-700 underline">
        Back to tanks
      </Link>
    </section>
  );
}
