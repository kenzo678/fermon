import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import { makeUser } from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { ChangePasswordPage } from "./ChangePasswordPage";

function Pages() {
  return (
    <Routes>
      <Route path="/account/password" element={<ChangePasswordPage />} />
      <Route path="/" element={<p>Home page</p>} />
    </Routes>
  );
}

async function fill(current: string, next: string, confirm = next) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Current password"), current);
  await user.type(screen.getByLabelText("New password"), next);
  await user.type(screen.getByLabelText("Confirm new password"), confirm);
  await user.click(screen.getByRole("button", { name: "Change password" }));
}

describe("ChangePasswordPage", () => {
  it("changes the password, refreshes the session and goes home", async () => {
    let body: unknown;
    let meCalls = 0;
    server.use(
      http.post(`${API_URL}/auth/password`, async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
      http.get(`${API_URL}/auth/me`, () => {
        meCalls += 1;
        return HttpResponse.json({ user: makeUser({ must_change_password: false }) });
      }),
    );
    renderWithProviders(<Pages />, {
      route: "/account/password",
      user: makeUser({ must_change_password: true }),
    });
    await fill("temporary-pass", "a-much-better-one");
    expect(await screen.findByText("Home page")).toBeInTheDocument();
    expect(body).toEqual({ current_password: "temporary-pass", new_password: "a-much-better-one" });
    expect(meCalls).toBeGreaterThan(0);
  });

  it("says so when the current password is wrong, and stays on the page", async () => {
    server.use(
      http.post(`${API_URL}/auth/password`, () =>
        HttpResponse.json({ detail: [{ field: null, message: "current password is incorrect" }] }, { status: 401 }),
      ),
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json({ user: makeUser() })),
    );
    renderWithProviders(<Pages />, { route: "/account/password" });
    await fill("wrong-wrong", "a-much-better-one");
    expect(await screen.findByRole("alert")).toHaveTextContent("current password is incorrect");
    expect(screen.queryByText("Home page")).not.toBeInTheDocument();
  });

  it("shows the server's field error for a weak new password", async () => {
    server.use(
      http.post(`${API_URL}/auth/password`, () =>
        HttpResponse.json(
          { detail: [{ field: "new_password", message: "must differ from the current password" }] },
          { status: 422 },
        ),
      ),
    );
    renderWithProviders(<Pages />, { route: "/account/password" });
    await fill("same-password-1", "same-password-1");
    expect(await screen.findByText("must differ from the current password")).toBeInTheDocument();
  });

  it("checks length and confirmation before calling the server", async () => {
    let called = false;
    server.use(
      http.post(`${API_URL}/auth/password`, () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<Pages />, { route: "/account/password" });
    await fill("whatever-12", "short", "short");
    expect(screen.getByText("Use at least 10 characters.")).toBeInTheDocument();
    expect(called).toBe(false);
  });

  it("reports a confirmation mismatch", async () => {
    renderWithProviders(<Pages />, { route: "/account/password" });
    await fill("whatever-12", "a-much-better-one", "another-one-xx");
    expect(screen.getByText("The passwords do not match.")).toBeInTheDocument();
  });

  it("explains the forced change for a temporary password", () => {
    renderWithProviders(<Pages />, {
      route: "/account/password",
      user: makeUser({ must_change_password: true }),
    });
    expect(screen.getByText(/temporary password/i)).toBeInTheDocument();
  });
});
