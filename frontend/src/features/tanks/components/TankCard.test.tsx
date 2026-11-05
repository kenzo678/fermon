import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeReading, makeTank } from "../../../test/fixtures";
import { renderWithProviders } from "../../../test/renderWithProviders";
import { TankCard } from "./TankCard";

describe("TankCard", () => {
  it("shows the id when there is no display name", () => {
    renderWithProviders(<TankCard tank={makeTank("tank-1")} />);
    expect(screen.getByRole("heading", { level: 3, name: "tank-1" })).toBeInTheDocument();
  });

  it("prefers the display name over the id", () => {
    renderWithProviders(<TankCard tank={makeTank("tank-1", { display_name: "Pale Ale" })} />);
    expect(screen.getByRole("heading", { level: 3, name: "Pale Ale" })).toBeInTheDocument();
  });

  it("links to the tank detail page", () => {
    renderWithProviders(<TankCard tank={makeTank("tank-1")} />);
    expect(screen.getByRole("link", { name: "tank-1" })).toHaveAttribute("href", "/tanks/tank-1");
  });

  it("encodes the id in the link target", () => {
    renderWithProviders(<TankCard tank={makeTank("a b/c")} />);
    expect(screen.getByRole("link", { name: "a b/c" })).toHaveAttribute("href", "/tanks/a%20b%2Fc");
  });

  it("renders each latest value with its unit and sensible decimals", () => {
    renderWithProviders(<TankCard tank={makeTank("tank-1")} />);
    expect(screen.getByText("18.5 °C")).toBeInTheDocument();
    expect(screen.getByText("1.23 bar")).toBeInTheDocument();
    expect(screen.getByText("4.3 % ABV")).toBeInTheDocument();
  });

  it("labels each measurement", () => {
    renderWithProviders(<TankCard tank={makeTank("tank-1")} />);
    for (const label of ["Temperature", "Pressure", "Alcohol"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("shows a dash for a measurement without a reading", () => {
    const tank = makeTank("tank-1");
    tank.latest.pressure = null;
    renderWithProviders(<TankCard tank={tank} />);
    const pressure = screen.getByText("Pressure").closest("div")!;
    expect(within(pressure).getByText("—")).toBeInTheDocument();
    expect(screen.getByText("18.5 °C")).toBeInTheDocument();
  });

  it("shows when the newest reading was recorded, as machine-readable time", () => {
    const tank = makeTank("tank-1");
    tank.latest.alcohol = makeReading("tank-1", "alcohol", 4, "2026-03-02T12:30:00Z");
    renderWithProviders(<TankCard tank={tank} />);
    const updated = screen.getByText(/^Updated/);
    expect(within(updated).getByText((_, el) => el?.tagName === "TIME")).toHaveAttribute(
      "datetime",
      "2026-03-02T12:30:00Z",
    );
  });

  it("says there are no readings when every measurement is missing", () => {
    const tank = makeTank("tank-1", {
      latest: { temperature: null, pressure: null, alcohol: null },
    });
    renderWithProviders(<TankCard tank={tank} />);
    expect(screen.getByText("No readings yet")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(3);
  });

  it("shows when the tank was first seen", () => {
    renderWithProviders(<TankCard tank={makeTank("tank-1")} />);
    const firstSeen = screen.getByText(/^First seen/);
    expect(within(firstSeen).getByText((_, el) => el?.tagName === "TIME")).toHaveAttribute(
      "datetime",
      "2026-02-01T08:00:00Z",
    );
  });
});
