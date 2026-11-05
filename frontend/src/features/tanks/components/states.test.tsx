import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../../test/renderWithProviders";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";

describe("EmptyState", () => {
  it("explains that no tanks have reported yet", () => {
    renderWithProviders(<EmptyState />);
    expect(screen.getByRole("heading", { name: "No tanks yet" })).toBeInTheDocument();
    expect(screen.getByText(/appear here/i)).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("announces the message and calls onRetry from the retry button", async () => {
    const onRetry = vi.fn();
    renderWithProviders(<ErrorState message="Could not load tanks" onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load tanks");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("LoadingState", () => {
  it("exposes a labelled busy status with skeleton placeholders", () => {
    renderWithProviders(<LoadingState />);
    const status = screen.getByRole("status", { name: "Loading tanks" });
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status.querySelectorAll("[data-skeleton]").length).toBeGreaterThan(0);
  });
});
