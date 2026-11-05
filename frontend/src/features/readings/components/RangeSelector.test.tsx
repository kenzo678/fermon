import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RangeSelector } from "./RangeSelector";

describe("RangeSelector", () => {
  it("renders an accessible radio group with the selected range checked", () => {
    render(<RangeSelector value="6h" onChange={() => {}} />);
    const group = screen.getByRole("radiogroup", { name: "Time range" });
    expect(group).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    expect(screen.getByRole("radio", { name: "Last 6 hours" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Last hour" })).not.toBeChecked();
  });

  it("reports the chosen range", async () => {
    const onChange = vi.fn();
    render(<RangeSelector value="24h" onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "Last 7 days" }));
    expect(onChange).toHaveBeenCalledWith("7d");
  });
});
