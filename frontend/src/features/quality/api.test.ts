import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import { server } from "../../test/server";
import {
  createQualityProfile,
  fetchQualityParameters,
  fetchQualityProfile,
  fetchQualityProfiles,
  fetchQualityTemplates,
  removeQualitySpec,
  saveQualitySpec,
} from "./api";

describe("quality api", () => {
  it("reads the catalog, templates and profiles", async () => {
    server.use(
      http.get(`${API_URL}/quality-parameters`, () => HttpResponse.json([{ code: "ph" }])),
      http.get(`${API_URL}/quality-profile-templates`, () => HttpResponse.json([{ template: "pale_lager" }])),
      http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json([{ id: "p1" }])),
      http.get(`${API_URL}/quality-profiles/p%2F1`, () => HttpResponse.json({ id: "p/1" })),
    );
    await expect(fetchQualityParameters()).resolves.toEqual([{ code: "ph" }]);
    await expect(fetchQualityTemplates()).resolves.toEqual([{ template: "pale_lager" }]);
    await expect(fetchQualityProfiles()).resolves.toEqual([{ id: "p1" }]);
    await expect(fetchQualityProfile("p/1")).resolves.toEqual({ id: "p/1" });
  });

  it("creates a profile with the CSRF header", async () => {
    let seen: { header: string | null; body: unknown } | undefined;
    server.use(
      http.post(`${API_URL}/quality-profiles`, async ({ request }) => {
        seen = { header: request.headers.get("x-requested-with"), body: await request.json() };
        return HttpResponse.json({ id: "p1" }, { status: 201 });
      }),
    );
    await createQualityProfile({ name: "House", template: "pale_lager" });
    expect(seen).toEqual({ header: "fermon", body: { name: "House", template: "pale_lager" } });
  });

  it("saves a spec with PUT and removes it with DELETE, both with the CSRF header", async () => {
    const seen: Array<{ method: string; header: string | null; body: unknown }> = [];
    server.use(
      http.all(`${API_URL}/quality-profiles/p1/specs/bright_beer/ph`, async ({ request }) => {
        const text = await request.text();
        seen.push({
          method: request.method,
          header: request.headers.get("x-requested-with"),
          body: text === "" ? null : JSON.parse(text),
        });
        return request.method === "DELETE"
          ? new HttpResponse(null, { status: 204 })
          : HttpResponse.json({ stage: "bright_beer", parameter: "ph" });
      }),
    );
    const body = { acceptance: { min: 4.1, max: 4.7 }, internal: null, target: null };
    await saveQualitySpec("p1", "bright_beer", "ph", body);
    await removeQualitySpec("p1", "bright_beer", "ph");
    expect(seen).toEqual([
      { method: "PUT", header: "fermon", body },
      { method: "DELETE", header: "fermon", body: null },
    ]);
  });
});
