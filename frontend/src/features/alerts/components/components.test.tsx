import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeAlert } from "../../../test/fixtures";
import { renderWithProviders } from "../../../test/renderWithProviders";
import { formatDateTime } from "../../tanks/format";
import { AlertBadge } from "./AlertBadge";
import { AlertItem } from "./AlertItem";
import { AlertList } from "./AlertList";

/** A labelled timestamp: `<span>Label <time datetime=...>formatted</time></span>`. */
function expectStamp(label: string, iso: string) {
  const time = screen.getByText(formatDateTime(iso), { selector: "time" });
  expect(time).toHaveAttribute("datetime", iso);
  expect(time.parentElement).toHaveTextContent(`${label} ${formatDateTime(iso)}`);
}

describe("AlertBadge", () => {
  it("shows the count with an accessible description", () => {
    renderWithProviders(<AlertBadge count={3} />);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("unresolved alerts")).toHaveClass("sr-only");
  });

  it("caps large counts", () => {
    renderWithProviders(<AlertBadge count={120} />);
    expect(screen.getByText("99+")).toBeInTheDocument();
  });

  it("renders nothing for zero", () => {
    const { container } = renderWithProviders(<AlertBadge count={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("uses the singular for one alert", () => {
    renderWithProviders(<AlertBadge count={1} />);
    expect(screen.getByText("unresolved alert")).toBeInTheDocument();
  });
});

describe("AlertItem", () => {
  it("shows the message, status chip, tank link and opening time", () => {
    renderWithProviders(<AlertItem alert={makeAlert()} onAcknowledge={() => {}} />);
    expect(screen.getByText("Temperature below target (observed 19.1 °C, target 30–35 °C)")).toBeInTheDocument();
    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "tank-1" })).toHaveAttribute("href", "/tanks/tank-1");
    expectStamp("Opened", "2026-03-01T12:00:00Z");
  });

  it("exposes the alert id so a specific alert can be located", () => {
    renderWithProviders(<AlertItem alert={makeAlert({ id: "alert-42" })} onAcknowledge={() => {}} />);
    expect(screen.getByRole("article")).toHaveAttribute("data-alert-id", "alert-42");
  });

  it("offers Acknowledge on open alerts and reports the alert", async () => {
    const onAcknowledge = vi.fn();
    const alert = makeAlert();
    renderWithProviders(<AlertItem alert={alert} onAcknowledge={onAcknowledge} />);
    await userEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    expect(onAcknowledge).toHaveBeenCalledWith(alert);
  });

  it("disables the button and says so while the request is in flight", () => {
    renderWithProviders(<AlertItem alert={makeAlert()} onAcknowledge={() => {}} acknowledging />);
    const button = screen.getByRole("button", { name: "Acknowledging…" });
    expect(button).toBeDisabled();
  });

  it("has no button on acknowledged or resolved alerts", () => {
    const { rerender } = renderWithProviders(
      <AlertItem alert={makeAlert({ status: "acknowledged", acknowledged_at: "2026-03-01T12:05:00Z" })} onAcknowledge={() => {}} />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expectStamp("Acknowledged", "2026-03-01T12:05:00Z");
    rerender(<div />);
  });

  it("shows the resolution time and note for a resolved alert", () => {
    renderWithProviders(
      <AlertItem
        alert={makeAlert({
          status: "resolved",
          resolved_at: "2026-03-01T12:30:00Z",
          details: { resolution: "batch_finished" },
          kind: "silent_sensor",
          measurement: null,
        })}
      />,
    );
    expectStamp("Resolved", "2026-03-01T12:30:00Z");
    expect(screen.getByText("Resolved because the batch was finished")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the error of a failed acknowledgement", () => {
    renderWithProviders(<AlertItem alert={makeAlert()} onAcknowledge={() => {}} error="This alert was already resolved." />);
    expect(screen.getByRole("alert")).toHaveTextContent("This alert was already resolved.");
  });
});

describe("AlertList", () => {
  it("renders one item per alert", () => {
    renderWithProviders(<AlertList alerts={[makeAlert({ id: "a1" }), makeAlert({ id: "a2" })]} />);
    const list = screen.getByRole("list", { name: "Alerts" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });

  it("marks only the alert in flight, and routes the error to its alert", () => {
    renderWithProviders(
      <AlertList
        alerts={[makeAlert({ id: "a1" }), makeAlert({ id: "a2" })]}
        onAcknowledge={() => {}}
        acknowledgingId="a2"
        error={{ id: "a1", message: "boom" }}
      />,
    );
    const [first, second] = screen.getAllByRole("listitem");
    expect(within(first!).getByRole("button", { name: "Acknowledge" })).toBeEnabled();
    expect(within(first!).getByRole("alert")).toHaveTextContent("boom");
    expect(within(second!).getByRole("button", { name: "Acknowledging…" })).toBeDisabled();
  });
});
