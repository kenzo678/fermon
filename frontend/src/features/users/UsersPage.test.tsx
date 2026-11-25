import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { User } from "../../shared/api";
import { API_URL } from "../../shared/api";
import { makeUser } from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { UsersPage } from "./UsersPage";

const ada = makeUser({ id: "u-ada", email: "ada@example.com", display_name: "Ada Admin", role: "admin" });
const bea = makeUser({ id: "u-bea", email: "bea@example.com", display_name: "Bea Brewer", role: "brewer", version: 3 });
const vic = makeUser({
  id: "u-vic",
  email: "vic@example.com",
  display_name: "Vic Viewer",
  role: "viewer",
  must_change_password: true,
  active: false,
});

const row = (name: string) => screen.getByRole("listitem", { name });

function mockList(users: User[] = [ada, bea, vic]) {
  server.use(
    http.get(`${API_URL}/users`, () => HttpResponse.json(users)),
    // Edits refresh the session too (an admin may edit themselves).
    http.get(`${API_URL}/auth/me`, () => HttpResponse.json({ user: ada })),
  );
}

const conflict = (field: string | null, message: string) =>
  HttpResponse.json({ detail: [{ field, message }] }, { status: 409 });

describe("UsersPage", () => {
  it("lists every user with role and state", async () => {
    mockList();
    renderWithProviders(<UsersPage />, { user: ada });
    expect(await screen.findByRole("heading", { level: 2, name: "Users" })).toBeInTheDocument();
    const bearRow = await screen.findByRole("listitem", { name: "Bea Brewer" });
    expect(bearRow).toHaveTextContent("bea@example.com");
    expect(within(bearRow).getByLabelText("Role")).toHaveValue("brewer");
    expect(row("Vic Viewer")).toHaveTextContent("Inactive");
    expect(row("Vic Viewer")).toHaveTextContent("Must change password");
    expect(row("Ada Admin")).toHaveTextContent("You");
  });

  it("shows a retryable error when the list cannot load", async () => {
    server.use(http.get(`${API_URL}/users`, () => HttpResponse.json({}, { status: 500 })));
    renderWithProviders(<UsersPage />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("creates a user with a temporary password and lists it", async () => {
    let body: unknown;
    let users = [ada];
    server.use(
      http.get(`${API_URL}/users`, () => HttpResponse.json(users)),
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json({ user: ada })),
      http.post(`${API_URL}/users`, async ({ request }) => {
        body = await request.json();
        const created = makeUser({ id: "u-new", email: "new@example.com", display_name: "Nora New", role: "viewer", must_change_password: true });
        users = [...users, created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);
    await screen.findByRole("listitem", { name: "Ada Admin" });
    await user.click(screen.getByRole("button", { name: "New user" }));
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Display name"), "Nora New");
    await user.type(screen.getByLabelText("Temporary password"), "temp-password-1");
    await user.click(screen.getByRole("button", { name: "Create user" }));
    expect(await screen.findByRole("listitem", { name: "Nora New" })).toBeInTheDocument();
    expect(body).toEqual({
      email: "new@example.com",
      display_name: "Nora New",
      role: "viewer",
      temporary_password: "temp-password-1",
    });
    // The form closes and forgets the password.
    expect(screen.queryByLabelText("Temporary password")).not.toBeInTheDocument();
  });

  it("shows the server's field errors when creating fails", async () => {
    mockList([ada]);
    server.use(http.post(`${API_URL}/users`, () => conflict("email", "email 'x@example.com' is already registered")));
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);
    await screen.findByRole("listitem", { name: "Ada Admin" });
    await user.click(screen.getByRole("button", { name: "New user" }));
    await user.type(screen.getByLabelText("Email"), "x@example.com");
    await user.type(screen.getByLabelText("Display name"), "X");
    await user.type(screen.getByLabelText("Temporary password"), "temp-password-1");
    await user.click(screen.getByRole("button", { name: "Create user" }));
    expect(await screen.findByText("email 'x@example.com' is already registered")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows a 422 about the temporary password on its field", async () => {
    mockList([ada]);
    server.use(
      http.post(`${API_URL}/users`, () =>
        HttpResponse.json(
          { detail: [{ field: "temporary_password", message: "must be at least 10 characters" }] },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);
    await screen.findByRole("listitem", { name: "Ada Admin" });
    await user.click(screen.getByRole("button", { name: "New user" }));
    await user.type(screen.getByLabelText("Email"), "x@example.com");
    await user.type(screen.getByLabelText("Display name"), "X");
    await user.type(screen.getByLabelText("Temporary password"), "short");
    await user.click(screen.getByRole("button", { name: "Create user" }));
    expect(await screen.findByText("must be at least 10 characters")).toBeInTheDocument();
  });

  it("changes a role, sending the version it read", async () => {
    mockList();
    let body: unknown;
    server.use(
      http.patch(`${API_URL}/users/u-bea`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...bea, role: "viewer", version: 4 });
      }),
    );
    renderWithProviders(<UsersPage />);
    const select = within(await screen.findByRole("listitem", { name: "Bea Brewer" })).getByLabelText("Role");
    await userEvent.selectOptions(select, "viewer");
    await waitFor(() => expect(body).toEqual({ version: 3, role: "viewer" }));
  });

  it("shows the last-admin refusal on the row", async () => {
    mockList();
    server.use(
      http.patch(`${API_URL}/users/u-ada`, () => conflict("role", "cannot demote or deactivate the last active admin")),
    );
    renderWithProviders(<UsersPage />);
    const select = within(await screen.findByRole("listitem", { name: "Ada Admin" })).getByLabelText("Role");
    await userEvent.selectOptions(select, "viewer");
    expect(await within(row("Ada Admin")).findByRole("alert")).toHaveTextContent(
      "cannot demote or deactivate the last active admin",
    );
  });

  it("explains a version conflict and reloads the list on request", async () => {
    let calls = 0;
    server.use(
      http.get(`${API_URL}/users`, () => {
        calls += 1;
        return HttpResponse.json([ada, bea]);
      }),
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json({ user: ada })),
      http.patch(`${API_URL}/users/u-bea`, () => conflict("version", "user 'u-bea' was modified concurrently; reload and retry")),
    );
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);
    await user.selectOptions(within(await screen.findByRole("listitem", { name: "Bea Brewer" })).getByLabelText("Role"), "viewer");
    const alert = await within(row("Bea Brewer")).findByRole("alert");
    expect(alert).toHaveTextContent("changed by someone else");
    await user.click(within(alert).getByRole("button", { name: "Reload users" }));
    await waitFor(() => expect(calls).toBe(2));
  });

  it("deactivates an active user and reactivates an inactive one", async () => {
    mockList();
    const bodies: unknown[] = [];
    server.use(
      http.patch(`${API_URL}/users/:id`, async ({ request, params }) => {
        bodies.push([params.id, await request.json()]);
        return HttpResponse.json(bea);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);
    await user.click(within(await screen.findByRole("listitem", { name: "Bea Brewer" })).getByRole("button", { name: "Deactivate" }));
    await user.click(within(row("Vic Viewer")).getByRole("button", { name: "Activate" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies).toEqual([
      ["u-bea", { version: 3, active: false }],
      ["u-vic", { version: 1, active: true }],
    ]);
  });

  it("resets a password with a temporary one", async () => {
    mockList();
    let body: unknown;
    server.use(
      http.post(`${API_URL}/users/u-bea/reset-password`, async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);
    const bearRow = await screen.findByRole("listitem", { name: "Bea Brewer" });
    await user.click(within(bearRow).getByRole("button", { name: "Reset password" }));
    await user.type(within(bearRow).getByLabelText("Temporary password"), "another-temp-1");
    await user.click(within(bearRow).getByRole("button", { name: "Set temporary password" }));
    expect(await within(row("Bea Brewer")).findByRole("status")).toHaveTextContent("Temporary password set");
    expect(body).toEqual({ temporary_password: "another-temp-1" });
    expect(within(row("Bea Brewer")).queryByLabelText("Temporary password")).not.toBeInTheDocument();
  });

  it("shows a reset error on its field", async () => {
    mockList();
    server.use(
      http.post(`${API_URL}/users/u-bea/reset-password`, () =>
        HttpResponse.json(
          { detail: [{ field: "temporary_password", message: "must be at least 10 characters" }] },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);
    const bearRow = await screen.findByRole("listitem", { name: "Bea Brewer" });
    await user.click(within(bearRow).getByRole("button", { name: "Reset password" }));
    await user.type(within(bearRow).getByLabelText("Temporary password"), "short");
    await user.click(within(bearRow).getByRole("button", { name: "Set temporary password" }));
    expect(await within(row("Bea Brewer")).findByText("must be at least 10 characters")).toBeInTheDocument();
  });
});
