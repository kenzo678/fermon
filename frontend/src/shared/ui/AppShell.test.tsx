import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

describe("AppShell", () => {
  it("renders the app name in a banner landmark", () => {
    render(<AppShell>content</AppShell>);
    const banner = screen.getByRole("banner");
    expect(banner).toHaveTextContent("Fermon");
    expect(screen.getByRole("heading", { level: 1, name: "Fermon" })).toBeInTheDocument();
  });

  it("renders children inside the main landmark", () => {
    render(
      <AppShell>
        <p>Tank list</p>
      </AppShell>,
    );
    expect(screen.getByRole("main")).toContainElement(screen.getByText("Tank list"));
  });
});
