import { Link, useParams } from "react-router";

// Replaced by the real detail view with the charts.
export function TankDetailPlaceholder() {
  const { tankId } = useParams();
  return (
    <section className="space-y-2">
      <h2 className="text-xl font-semibold tracking-tight">Tank detail — coming soon</h2>
      <p className="text-slate-600">{tankId}</p>
      <Link to="/" className="text-sm font-medium text-slate-700 underline">
        Back to tanks
      </Link>
    </section>
  );
}
