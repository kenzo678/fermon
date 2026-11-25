import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import { makeUser } from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { sessionKeys } from "./api";
import { AccountMenu } from "./AccountMenu";

function Where() {
  const { pathname, state } = useLocation();
  return <p data-testid="where">{pathname + (state === null ? "" : "+state")}</p>;
}

function Harness() {
  return (
    <>
      <AccountMenu />
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </>
  );
}

describe("AccountMenu", () => {
  it("shows who is signed in, with their role, and a link to change the password", () => {
    renderWithProviders(<Harness />, { user: makeUser({ display_name: "Bea Brewer", role: "brewer" }) });
    const account = screen.getByRole("group", { name: "Account" });
    expect(account).toHaveTextContent("Bea Brewer");
    expect(account).toHaveTextContent("brewer");
    expect(screen.getByRole("link", { name: "Change password" })).toHaveAttribute("href", "/account/password");
  });

  it("renders nothing without a session", () => {
    renderWithProviders(<Harness />, { user: null });
    expect(screen.queryByRole("group", { name: "Account" })).not.toBeInTheDocument();
  });

  it("signs out, forgets the session and lands on the login page with no return target", async () => {
    let called = false;
    server.use(
      http.post(`${API_URL}/auth/logout`, () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { queryClient } = renderWithProviders(<Harness />, { route: "/batches" });
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/login"));
    expect(screen.getByTestId("where")).not.toHaveTextContent("+state");
    expect(called).toBe(true);
    expect(queryClient.getQueryData(sessionKeys.current())).toBeNull();
  });
});
