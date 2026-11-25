import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import { makeUser } from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { RequireAuth } from "./RequireAuth";
import { RequirePermission } from "./RequirePermission";

function Login() {
  const { state } = useLocation();
  return <p>Login page from {(state as { from?: string } | null)?.from ?? "nowhere"}</p>;
}

function Pages() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<p>Dashboard</p>} />
        <Route path="/batches" element={<p>Batches</p>} />
        <Route path="/account/password" element={<p>Change password page</p>} />
        <Route
          path="/users"
          element={
            <RequirePermission allow={(p) => p.canManageUsers}>
              <p>Users page</p>
            </RequirePermission>
          }
        />
      </Route>
    </Routes>
  );
}

describe("RequireAuth", () => {
  it("sends an anonymous visitor to the login page, remembering where they were going", async () => {
    renderWithProviders(<Pages />, { route: "/batches?status=active#top", user: null });
    expect(await screen.findByText("Login page from /batches?status=active#top")).toBeInTheDocument();
  });

  it("renders the page for a signed-in user", () => {
    renderWithProviders(<Pages />, { route: "/batches" });
    expect(screen.getByText("Batches")).toBeInTheDocument();
  });

  it("asks the server while the session is unknown, then lets the user in", async () => {
    server.use(http.get(`${API_URL}/auth/me`, () => HttpResponse.json({ user: makeUser() })));
    renderWithProviders(<Pages />, { route: "/batches", seedSession: false });
    expect(screen.getByRole("status", { name: "Checking your session" })).toBeInTheDocument();
    expect(await screen.findByText("Batches")).toBeInTheDocument();
  });

  it("sends an unknown, unauthenticated visitor to login after the check", async () => {
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json({ detail: [] }, { status: 401 })),
    );
    renderWithProviders(<Pages />, { route: "/", seedSession: false });
    expect(await screen.findByText("Login page from /")).toBeInTheDocument();
  });

  it("offers a retry when the session check itself fails", async () => {
    server.use(http.get(`${API_URL}/auth/me`, () => HttpResponse.json({}, { status: 500 })));
    renderWithProviders(<Pages />, { route: "/", seedSession: false });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("forces a temporary password to be replaced before anything else", () => {
    renderWithProviders(<Pages />, { route: "/batches", user: makeUser({ must_change_password: true }) });
    expect(screen.getByText("Change password page")).toBeInTheDocument();
    expect(screen.queryByText("Batches")).not.toBeInTheDocument();
  });

  it("lets a user with a temporary password reach the change-password page itself", () => {
    renderWithProviders(<Pages />, {
      route: "/account/password",
      user: makeUser({ must_change_password: true }),
    });
    expect(screen.getByText("Change password page")).toBeInTheDocument();
  });
});

describe("RequirePermission", () => {
  it("renders the page when the permission is held", () => {
    renderWithProviders(<Pages />, { route: "/users" });
    expect(screen.getByText("Users page")).toBeInTheDocument();
  });

  it("explains the lack of access instead of rendering the page", () => {
    renderWithProviders(<Pages />, { route: "/users", user: makeUser({ role: "brewer" }) });
    expect(screen.getByRole("heading", { name: "Not allowed" })).toBeInTheDocument();
    expect(screen.queryByText("Users page")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to tanks" })).toHaveAttribute("href", "/");
  });
});
