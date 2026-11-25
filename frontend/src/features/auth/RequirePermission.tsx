import type { ReactNode } from "react";
import { Link } from "react-router";
import { usePermissions } from "./hooks";
import type { Permissions } from "./hooks";

/** Page-level guard. The API enforces the rule too; this only avoids showing a page that cannot work. */
export function RequirePermission({
  allow,
  children,
}: {
  allow: (permissions: Permissions) => boolean;
  children: ReactNode;
}) {
  const permissions = usePermissions();
  if (allow(permissions)) return <>{children}</>;
  return (
    <section className="space-y-2">
      <h2 className="text-xl font-semibold tracking-tight">Not allowed</h2>
      <p className="text-slate-600">Your role does not give you access to this page.</p>
      <Link to="/" className="text-sm font-medium text-slate-700 underline">
        Back to tanks
      </Link>
    </section>
  );
}
