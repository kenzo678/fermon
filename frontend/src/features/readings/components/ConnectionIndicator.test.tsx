import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConnectionIndicator } from "./ConnectionIndicator";

describe("ConnectionIndicator", () => {
  it.each([
    ["live", "Live"],
    ["reconnecting", "Reconnecting…"],
    ["offline", "Offline"],
  ] as const)("renders %s as an accessible status", (status, text) => {
    render(<ConnectionIndicator status={status} />);
    expect(screen.getByRole("status", { name: `Connection: ${text}` })).toHaveTextContent(text);
  });
});
