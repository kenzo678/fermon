import { useState } from "react";
import { useSession } from "../auth";
import { ErrorState } from "../tanks/components/ErrorState";
import { NewUserForm } from "./components/NewUserForm";
import { UserRow } from "./components/UserRow";
import { useUsersQuery } from "./hooks";

export function UsersPage() {
  const users = useUsersQuery();
  const self = useSession().data;
  const [creating, setCreating] = useState(false);

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Users</h2>
        {!creating && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2"
          >
            New user
          </button>
        )}
      </div>
      {creating && <NewUserForm onDone={() => setCreating(false)} />}
      {users.data !== undefined ? (
        <ul aria-label="Users" className="space-y-3">
          {users.data.map((user) => (
            <UserRow key={user.id} user={user} isSelf={user.id === self?.id} onReload={() => void users.refetch()} />
          ))}
        </ul>
      ) : users.isPending ? (
        <div role="status" aria-label="Loading users" className="h-32 animate-pulse rounded-lg bg-slate-200" />
      ) : (
        <ErrorState message={users.error.message} onRetry={() => void users.refetch()} />
      )}
    </section>
  );
}
