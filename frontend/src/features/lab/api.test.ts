import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import { server } from "../../test/server";
import { createLabAnalysis, fetchLabAnalyses, fetchLabAnalysis } from "./api";

describe("lab api", () => {
  it("lists the analyses of a batch, optionally of one stage", async () => {
    const urls: string[] = [];
    server.use(
      http.get(`${API_URL}/batches/b%2F1/lab-analyses`, ({ request }) => {
        urls.push(new URL(request.url).search);
        return HttpResponse.json([{ id: "l1" }]);
      }),
    );
    await expect(fetchLabAnalyses("b/1")).resolves.toEqual([{ id: "l1" }]);
    await fetchLabAnalyses("b/1", "maturation");
    expect(urls).toEqual(["", "?stage=maturation"]);
  });

  it("reads one analysis", async () => {
    server.use(http.get(`${API_URL}/lab-analyses/l1`, () => HttpResponse.json({ id: "l1" })));
    await expect(fetchLabAnalysis("l1")).resolves.toEqual({ id: "l1" });
  });

  it("records an analysis with the CSRF header", async () => {
    let seen: { header: string | null; body: unknown } | undefined;
    server.use(
      http.post(`${API_URL}/batches/b1/lab-analyses`, async ({ request }) => {
        seen = { header: request.headers.get("x-requested-with"), body: await request.json() };
        return HttpResponse.json({ id: "l1" }, { status: 201 });
      }),
    );
    const body = { stage: "brewhouse" as const, values: { ph: 5.3 }, analyst: "Ana" };
    await expect(createLabAnalysis("b1", body)).resolves.toEqual({ id: "l1" });
    expect(seen).toEqual({ header: "fermon", body });
  });
});
