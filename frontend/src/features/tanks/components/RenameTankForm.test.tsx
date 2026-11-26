import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { API_URL } from "../../../shared/api";
import { makeTank } from "../../../test/fixtures";
import { renderWithProviders } from "../../../test/renderWithProviders";
import { server } from "../../../test/server";
import { tankKeys } from "../api";
import { RenameTankForm } from "./RenameTankForm";

const url = `${API_URL}/tanks/tank-1`;

function setup(displayName: string | null = null) {
  const tank = makeTank("tank-1", { display_name: displayName });
  const onDone = vi.fn();
  const sent: unknown[] = [];
  server.use(
    http.patch(url, async ({ request }) => {
      const body = (await request.json()) as { display_name: string | null };
      sent.push(body);
      return HttpResponse.json({ ...tank, display_name: body.display_name });
    }),
  );
  const view = renderWithProviders(<RenameTankForm tank={tank} onDone={onDone} />);
  view.queryClient.setQueryData(tankKeys.detail("tank-1"), tank);
  view.queryClient.setQueryData(tankKeys.list(), [tank, makeTank("tank-2")]);
  return { ...view, onDone, sent };
}

describe("RenameTankForm", () => {
  it("starts from the current name and sends the trimmed new one", async () => {
    const { sent, onDone } = setup("Old name");
    const input = screen.getByLabelText("Display name");
    expect(input).toHaveValue("Old name");
    await userEvent.clear(input);
    await userEvent.type(input, "  Fermenter A  ");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(sent).toEqual([{ display_name: "Fermenter A" }]);
  });

  it("updates the detail and list caches with the answer", async () => {
    const { queryClient, onDone } = setup();
    await userEvent.type(screen.getByLabelText("Display name"), "Fermenter A");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(queryClient.getQueryData<{ display_name: string }>(tankKeys.detail("tank-1"))?.display_name).toBe("Fermenter A");
    const list = queryClient.getQueryData<Array<{ id: string; display_name: string | null }>>(tankKeys.list());
    expect(list?.map((tank) => tank.display_name)).toEqual(["Fermenter A", null]);
  });

  it("rejects a blank name without calling the API", async () => {
    const { sent } = setup();
    await userEvent.type(screen.getByLabelText("Display name"), "   ");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Enter a name, or use Clear name")).toBeInTheDocument();
    expect(sent).toEqual([]);
  });

  it("rejects a name longer than 64 characters without calling the API", async () => {
    const { sent } = setup();
    await userEvent.type(screen.getByLabelText("Display name"), "x".repeat(65));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Use at most 64 characters")).toBeInTheDocument();
    expect(sent).toEqual([]);
  });

  it("shows a 422 on the field", async () => {
    setup();
    server.use(
      http.patch(url, () =>
        HttpResponse.json({ detail: [{ field: "display_name", message: "Name is invalid" }] }, { status: 422 }),
      ),
    );
    await userEvent.type(screen.getByLabelText("Display name"), "Bad");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Name is invalid")).toBeInTheDocument();
    expect(screen.getByLabelText("Display name")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows other failures in an alert and keeps the form open", async () => {
    const { onDone } = setup();
    server.use(
      http.patch(url, () => HttpResponse.json({ detail: [{ field: null, message: "Boom" }] }, { status: 500 })),
    );
    await userEvent.type(screen.getByLabelText("Display name"), "Name");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Boom");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("clears the name by sending null, only offered when there is one", async () => {
    const { sent, onDone } = setup("Old name");
    await userEvent.click(screen.getByRole("button", { name: "Clear name" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(sent).toEqual([{ display_name: null }]);
  });

  it("offers no Clear name when the tank has no display name", () => {
    setup();
    expect(screen.queryByRole("button", { name: "Clear name" })).not.toBeInTheDocument();
  });

  it("closes without saving on Cancel", async () => {
    const { sent, onDone } = setup("Old name");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onDone).toHaveBeenCalled();
    expect(sent).toEqual([]);
  });
});
