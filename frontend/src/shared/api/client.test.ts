import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { ApiError } from "./errors";
import { API_URL, apiGet, buildUrl } from "./client";
import type { Tank } from "./types";

const BASE = API_URL;

const tank: Tank = {
  id: "tank-1",
  display_name: null,
  first_seen_at: "2026-01-01T00:00:00Z",
  latest: {
    temperature: {
      tank_id: "tank-1",
      sensor_id: "s1",
      measurement: "temperature",
      value: 18.5,
      unit: "C",
      recorded_at: "2026-01-01T00:00:00Z",
    },
    pressure: null,
    alcohol: null,
  },
};

describe("apiGet", () => {
  it("parses a successful JSON response", async () => {
    server.use(http.get(`${BASE}/tanks`, () => HttpResponse.json([tank])));
    await expect(apiGet<Tank[]>("/tanks")).resolves.toEqual([tank]);
  });

  it("sends query params, skipping undefined and expanding arrays", async () => {
    let url = "";
    server.use(
      http.get(`${BASE}/tanks/t/readings/aggregated`, ({ request }) => {
        url = request.url;
        return HttpResponse.json({});
      }),
    );
    await apiGet("/tanks/t/readings/aggregated", {
      params: { bucket: "1m", skip: undefined, measurement: ["temperature", "alcohol"] },
    });
    const q = new URL(url).searchParams;
    expect(q.get("bucket")).toBe("1m");
    expect(q.has("skip")).toBe(false);
    expect(q.getAll("measurement")).toEqual(["temperature", "alcohol"]);
  });

  it("maps the unified 422 error body to ApiError", async () => {
    const detail = [{ field: "start", message: "Field required" }];
    server.use(http.get(`${BASE}/x`, () => HttpResponse.json({ detail }, { status: 422 })));
    const error = await apiGet("/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, detail });
  });

  it("maps a 404 error body to ApiError", async () => {
    const detail = [{ field: null, message: "Tank not found" }];
    server.use(http.get(`${BASE}/tanks/nope`, () => HttpResponse.json({ detail }, { status: 404 })));
    const error = await apiGet("/tanks/nope").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, detail, message: "Tank not found" });
  });

  it("wraps a non-JSON error response in ApiError with empty detail", async () => {
    server.use(http.get(`${BASE}/boom`, () => new HttpResponse("oops", { status: 500 })));
    const error = await apiGet("/boom").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 500, detail: [] });
  });

  it("wraps a network failure in ApiError with status 0", async () => {
    server.use(http.get(`${BASE}/down`, () => HttpResponse.error()));
    const error = await apiGet("/down").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0 });
  });

  it("pins the base URL from the Vitest env, not the developer machine", () => {
    expect(API_URL).toBe("http://api.test");
  });

  it("wraps a 2xx response with a non-JSON body in ApiError", async () => {
    server.use(http.get(`${BASE}/html`, () => new HttpResponse("<html></html>", { status: 200 })));
    const error = await apiGet("/html").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 200, detail: [], message: "Invalid JSON response" });
  });

  it("wraps a 204 empty response in ApiError (every consumed endpoint returns JSON)", async () => {
    server.use(http.get(`${BASE}/empty`, () => new HttpResponse(null, { status: 204 })));
    const error = await apiGet("/empty").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 204, message: "Invalid JSON response" });
  });

  it("rejects with an AbortError when aborted without a reason", async () => {
    server.use(
      http.get(`${BASE}/slow`, async () => {
        await delay(200);
        return HttpResponse.json({});
      }),
    );
    const controller = new AbortController();
    const pending = apiGet("/slow", { signal: controller.signal }).catch((e: unknown) => e);
    controller.abort();
    const error = await pending;
    expect(error).not.toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ name: "AbortError" });
  });

  it("rejects with the custom reason when aborted with one, never ApiError", async () => {
    server.use(
      http.get(`${BASE}/slow`, async () => {
        await delay(200);
        return HttpResponse.json({});
      }),
    );
    const reason = new Error("superseded");
    const controller = new AbortController();
    const pending = apiGet("/slow", { signal: controller.signal }).catch((e: unknown) => e);
    controller.abort(reason);
    const error = await pending;
    expect(error).not.toBeInstanceOf(ApiError);
    expect(error).toBe(reason);
  });

  // A body that starts streaming but never finishes: headers arrive, the body read hangs.
  const hangingBody = (status: number) => () =>
    new HttpResponse(
      new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode('{"partial":'));
        },
      }),
      { status, headers: { "Content-Type": "application/json" } },
    );

  it("propagates an abort that happens while reading a success body", async () => {
    server.use(http.get(`${BASE}/stream`, hangingBody(200)));
    const reason = new Error("superseded");
    const controller = new AbortController();
    const pending = apiGet("/stream", { signal: controller.signal }).catch((e: unknown) => e);
    await delay(50);
    controller.abort(reason);
    const error = await pending;
    expect(error).not.toBeInstanceOf(ApiError);
    expect(error).toBe(reason);
  });

  it("propagates an abort that happens while reading an error body", async () => {
    server.use(http.get(`${BASE}/stream-error`, hangingBody(500)));
    const reason = new Error("superseded");
    const controller = new AbortController();
    const pending = apiGet("/stream-error", { signal: controller.signal }).catch((e: unknown) => e);
    await delay(50);
    controller.abort(reason);
    const error = await pending;
    expect(error).not.toBeInstanceOf(ApiError);
    expect(error).toBe(reason);
  });
});

describe("buildUrl", () => {
  it("keeps a path prefix on an absolute base", () => {
    expect(buildUrl("/tanks", undefined, "http://host/api")).toBe("http://host/api/tanks");
  });

  it("tolerates trailing slashes on the base and missing leading slash on the path", () => {
    expect(buildUrl("tanks", undefined, "http://host/api//")).toBe("http://host/api/tanks");
    expect(buildUrl("/tanks", undefined, "http://host")).toBe("http://host/tanks");
  });

  it("treats an empty base as same origin (relative URL)", () => {
    expect(buildUrl("/tanks", { a: 1 }, "")).toBe("/tanks?a=1");
  });

  it("supports a relative base with a path prefix", () => {
    expect(buildUrl("/tanks", { m: ["x", "y"], s: undefined }, "/api/")).toBe("/api/tanks?m=x&m=y");
  });

  it("converts URL construction errors into ApiError(0)", () => {
    const error = (() => {
      try {
        return buildUrl("/tanks", undefined, "http://[bad");
      } catch (e) {
        return e;
      }
    })();
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0 });
  });

  it("rejects a scheme-less base such as host:port instead of resolving it against the page", () => {
    expect(() => buildUrl("/tanks", undefined, "localhost:8000")).toThrow(ApiError);
    expect(() => buildUrl("/tanks", undefined, "api.example.com/v1")).toThrow(ApiError);
  });
});
