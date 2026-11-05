import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeTank } from "../../../test/fixtures";
import { renderWithProviders } from "../../../test/renderWithProviders";
import { TankGrid } from "./TankGrid";

describe("TankGrid", () => {
  it("renders one list item and card per tank", () => {
    const tanks = [makeTank("tank-1"), makeTank("tank-2"), makeTank("tank-3")];
    renderWithProviders(<TankGrid tanks={tanks} />);
    expect(screen.getByRole("list", { name: "Tanks" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getAllByRole("link")).toHaveLength(3);
  });

  it("uses a responsive column layout", () => {
    renderWithProviders(<TankGrid tanks={[makeTank("tank-1")]} />);
    const list = screen.getByRole("list");
    expect(list).toHaveClass("grid-cols-1", "sm:grid-cols-2", "lg:grid-cols-3", "xl:grid-cols-4");
  });
});
