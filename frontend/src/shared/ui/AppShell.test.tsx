import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

function renderShell(children: React.ReactNode, route = "/", navBadges?: Record<string, React.ReactNode>) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AppShell navBadges={navBadges}>{children}</AppShell>
    </MemoryRouter>,
  );
}

describe("AppShell", () => {
  it("renders the app name in a banner landmark", () => {
    renderShell("content");
    const banner = screen.getByRole("banner");
    expect(banner).toHaveTextContent("Fermon");
    expect(screen.getByRole("heading", { level: 1, name: "Fermon" })).toBeInTheDocument();
  });

  it("renders children inside the main landmark", () => {
    renderShell(<p>Tank list</p>);
    expect(screen.getByRole("main")).toContainElement(screen.getByText("Tank list"));
  });

  it("offers a main navigation with Tanks and Batches", () => {
    renderShell("content");
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toContainElement(screen.getByRole("link", { name: "Tanks" }));
    expect(screen.getByRole("link", { name: "Batches" })).toHaveAttribute("href", "/batches");
  });

  it("marks the current section", () => {
    renderShell("content", "/batches/new");
    expect(screen.getByRole("link", { name: "Batches" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Tanks" })).not.toHaveAttribute("aria-current");
  });

  it("links to the alerts page", () => {
    renderShell("content", "/alerts");
    expect(screen.getByRole("link", { name: "Alerts" })).toHaveAttribute("href", "/alerts");
    expect(screen.getByRole("link", { name: "Alerts" })).toHaveAttribute("aria-current", "page");
  });

  it("renders a badge next to the matching nav link", () => {
    renderShell("content", "/", { "/alerts": <span>3</span> });
    expect(screen.getByRole("link", { name: "Alerts 3" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tanks" })).toBeInTheDocument();
  });
});
