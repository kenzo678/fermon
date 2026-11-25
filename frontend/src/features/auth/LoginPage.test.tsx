import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import { makeUser } from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { LoginPage, formatRetryDelay } from "./LoginPage";

function Pages() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<p>Home page</p>} />
      <Route path="/batches" element={<p>Batches page</p>} />
      <Route path="/from-batches" element={<Navigate to="/login" state={{ from: "/batches?status=active" }} />} />
      <Route path="/from-elsewhere" element={<Navigate to="/login" state={{ from: "https://evil.example" }} />} />
    </Routes>
  );
}

async function signIn(email = "ada@example.com", password = "correct horse") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

const loginOk = () =>
  http.post(`${API_URL}/auth/login`, () => HttpResponse.json({ user: makeUser() }));

describe("LoginPage", () => {
  it("posts the credentials and goes to the dashboard", async () => {
    let body: unknown;
    server.use(
      http.post(`${API_URL}/auth/login`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ user: makeUser() });
      }),
    );
    renderWithProviders(<Pages />, { route: "/login", user: null });
    await signIn();
    expect(await screen.findByText("Home page")).toBeInTheDocument();
    expect(body).toEqual({ email: "ada@example.com", password: "correct horse" });
  });

  it("returns to the page the user asked for before being sent to login", async () => {
    server.use(loginOk());
    renderWithProviders(<Pages />, { route: "/from-batches", user: null });
    await signIn();
    expect(await screen.findByText("Batches page")).toBeInTheDocument();
  });

  it("ignores a return target that leaves the app", async () => {
    server.use(loginOk());
    renderWithProviders(<Pages />, { route: "/from-elsewhere", user: null });
    await signIn();
    expect(await screen.findByText("Home page")).toBeInTheDocument();
  });

  it("shows one generic message for a failed login", async () => {
    server.use(
      http.post(`${API_URL}/auth/login`, () =>
        HttpResponse.json({ detail: [{ field: null, message: "invalid email or password" }] }, { status: 401 }),
      ),
    );
    renderWithProviders(<Pages />, { route: "/login", user: null });
    await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("tells the user when to retry after too many attempts", async () => {
    server.use(
      http.post(`${API_URL}/auth/login`, () =>
        HttpResponse.json(
          { detail: [{ field: null, message: "too many failed login attempts" }] },
          { status: 429, headers: { "Retry-After": "900" } },
        ),
      ),
    );
    renderWithProviders(<Pages />, { route: "/login", user: null });
    await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many failed attempts. Try again in 15 minutes.");
  });

  it("falls back to the server message for other failures", async () => {
    server.use(http.post(`${API_URL}/auth/login`, () => HttpResponse.error()));
    renderWithProviders(<Pages />, { route: "/login", user: null });
    await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent("Network error");
  });

  it("does not submit an empty form", async () => {
    renderWithProviders(<Pages />, { route: "/login", user: null });
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter your email.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
  });

  it("skips the form for someone already signed in", async () => {
    renderWithProviders(<Pages />, { route: "/login" });
    expect(await screen.findByText("Home page")).toBeInTheDocument();
  });
});

describe("formatRetryDelay", () => {
  it.each([
    [undefined, "later"],
    [1, "in 1 second"],
    [45, "in 45 seconds"],
    [60, "in 1 minute"],
    [61, "in 2 minutes"],
    [900, "in 15 minutes"],
  ])("%s -> %s", (seconds, text) => {
    expect(formatRetryDelay(seconds)).toBe(text);
  });
});
