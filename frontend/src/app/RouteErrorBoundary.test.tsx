import { screen } from "@testing-library/react";
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
});
