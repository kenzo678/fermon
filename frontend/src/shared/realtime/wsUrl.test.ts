import { describe, expect, it } from "vitest";
import { wsUrlFor } from "./wsUrl";

describe("wsUrlFor", () => {
  it("maps http to ws and https to wss", () => {
    expect(wsUrlFor("/ws/tanks/t1", "http://api:8000")).toBe("ws://api:8000/ws/tanks/t1");
    expect(wsUrlFor("/ws/tanks/t1", "https://example.com")).toBe("wss://example.com/ws/tanks/t1");
  });

  it("keeps a base path prefix and tolerates slashes", () => {
    expect(wsUrlFor("ws/tanks/t1", "https://example.com/fermon/")).toBe(
      "wss://example.com/fermon/ws/tanks/t1",
    );
  });

  it("uses the page origin for an empty or relative base", () => {
    const origin = window.location.origin.replace(/^http/, "ws");
    expect(wsUrlFor("/ws/tanks/t1", "")).toBe(`${origin}/ws/tanks/t1`);
    expect(wsUrlFor("/ws/tanks/t1", "/api")).toBe(`${origin}/api/ws/tanks/t1`);
  });

  it("rejects an invalid base like buildUrl does", () => {
    expect(() => wsUrlFor("/ws/tanks/t1", "localhost:8000")).toThrow(/Invalid API URL/);
  });
});
