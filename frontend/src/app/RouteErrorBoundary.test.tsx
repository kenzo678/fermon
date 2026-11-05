import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, Route, Routes, useParams } from "react-router";
import { RouteBoundary } from "./RouteErrorBoundary";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../test/renderWithProviders";
import { RouteErrorBoundary } from "./RouteErrorBoundary";

function Broken(): never {
  throw new Error("Failed to fetch dynamically imported module");
}

describe("RouteErrorBoundary", () => {
  // React logs caught render errors; keep the test output clean.
  beforeEach(() => vi.spyOn(console, "error").mockImplementation(() => {}));
  afterEach(() => vi.restoreAllMocks());

  it("renders its children when nothing fails", () => {
    renderWithProviders(
      <RouteErrorBoundary>
        <p>content</p>
      </RouteErrorBoundary>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("shows a recoverable error instead of a blank page when a route fails to load", () => {
    renderWithProviders(
      <RouteErrorBoundary>
        <Broken />
      </RouteErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("This page failed to load");
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to tanks" })).toHaveAttribute("href", "/");
  });

  it("resets when the URL changes within the same route (e.g. another tank)", async () => {
    function Page() {
      const { tankId } = useParams();
      if (tankId === "bad") throw new Error("chunk failed");
      return <p>{`page ${tankId}`}</p>;
    }
    renderWithProviders(
      <>
        <Link to="/tanks/good">go good</Link>
        <Routes>
          <Route
            path="/tanks/:tankId"
            element={
              <RouteBoundary>
                <Page />
              </RouteBoundary>
            }
          />
        </Routes>
      </>,
      { route: "/tanks/bad" },
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "go good" }));
    expect(screen.getByText("page good")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
