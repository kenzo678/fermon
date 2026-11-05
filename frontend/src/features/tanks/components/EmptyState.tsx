export function EmptyState() {
  return (
    <section className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
      <h3 className="text-base font-semibold">No tanks yet</h3>
      <p className="mt-1 text-sm text-slate-600">
        Tanks appear here as soon as they report their first reading.
      </p>
    </section>
  );
}
