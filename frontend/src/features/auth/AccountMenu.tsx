import { useNavigate } from "react-router";
import { Link } from "react-router";
import { useLogout, useSession } from "./hooks";

export const PASSWORD_PATH = "/account/password";

const linkClass =
  "rounded px-1 py-0.5 text-slate-600 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500";

/** Header block for the signed-in user: name, role, change password and sign out. */
export function AccountMenu({ showChangePassword = true }: { showChangePassword?: boolean }) {
  const user = useSession().data;
  const logout = useLogout();
  const navigate = useNavigate();
  if (user === undefined || user === null) return null;
  return (
    <div role="group" aria-label="Account" className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 text-sm">
      <span className="font-medium">{user.display_name}</span>
      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{user.role}</span>
      {showChangePassword && (
        <Link to={PASSWORD_PATH} className={linkClass}>
          Change password
        </Link>
      )}
      <button
        type="button"
        disabled={logout.isPending}
        // Leave first-hand for the login page: the guard would otherwise remember this page as the return target.
        onClick={() => logout.mutate(undefined, { onSettled: () => void navigate("/login", { replace: true }) })}
        className={`${linkClass} underline disabled:opacity-60`}
      >
        Sign out
      </button>
    </div>
  );
}
