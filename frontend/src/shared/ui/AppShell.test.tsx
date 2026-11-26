import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { AppShell, DEFAULT_NAV } from "./AppShell";

function renderShell(
  children: React.ReactNode,
  route = "/",
  navBadges?: Record<string, React.ReactNode>,
  extra: Partial<React.ComponentProps<typeof AppShell>> = {},
) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AppShell navBadges={navBadges} {...extra}>
        {children}
      </AppShell>
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

  it("links to the quality profiles and marks them current on their pages", () => {
    renderShell("content", "/quality-profiles/p1");
    expect(screen.getByRole("link", { name: "Quality" })).toHaveAttribute("href", "/quality-profiles");
    expect(screen.getByRole("link", { name: "Quality" })).toHaveAttribute("aria-current", "page");
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

  it("renders the navigation it is given instead of the default one", () => {
    renderShell("content", "/users", undefined, {
      nav: [...DEFAULT_NAV, { to: "/users", label: "Users", sections: ["/users"] }],
    });
    expect(screen.getByRole("link", { name: "Users" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Tanks" })).toBeInTheDocument();
  });

  it("can hide the navigation entirely (forced password change)", () => {
    renderShell("content", "/", undefined, { nav: [] });
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
  });

  it("shows the account slot inside the banner", () => {
    renderShell("content", "/", undefined, { account: <p>Ada</p> });
    expect(screen.getByRole("banner")).toContainElement(screen.getByText("Ada"));
  });
});
