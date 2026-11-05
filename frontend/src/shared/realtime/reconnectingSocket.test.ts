import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createReconnectingSocket } from "./reconnectingSocket";
import type { SocketStatus } from "./reconnectingSocket";
import { FakeSocket } from "../../test/fakeSocket";

function setup() {
  const sockets: FakeSocket[] = [];
  const statuses: SocketStatus[] = [];
  const messages: unknown[] = [];
  const opens: boolean[] = [];
  const socket = createReconnectingSocket({
    url: "ws://x/ws",
    socketFactory: (url) => {
      const s = new FakeSocket(url);
      sockets.push(s);
      return s;
    },
    onMessage: (m) => messages.push(m),
    onStatus: (s) => statuses.push(s),
    onOpen: (isReconnect) => opens.push(isReconnect),
  });
  const sock = (i: number): FakeSocket => {
    const found = sockets[i];
    if (found === undefined) throw new Error(`no socket #${i}`);
    return found;
  };
  return { sockets, sock, statuses, messages, opens, socket };
}

describe("createReconnectingSocket", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("connects, reports open and parses JSON messages", () => {
    const { sock, statuses, messages, opens } = setup();
    expect(statuses).toEqual(["connecting"]);
    sock(0).open();
    expect(statuses.at(-1)).toBe("open");
    expect(opens).toEqual([false]);
    sock(0).message('{"a":1}');
    expect(messages).toEqual([{ a: 1 }]);
  });

  it("drops malformed messages with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { sock, messages } = setup();
    sock(0).open();
    sock(0).message("not json");
    expect(messages).toEqual([]);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("reports a consumer error as such, not as a malformed message", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const sockets: FakeSocket[] = [];
    createReconnectingSocket({
      url: "ws://x/ws",
      socketFactory: (url) => {
        const s = new FakeSocket(url);
        sockets.push(s);
        return s;
      },
      onMessage: () => {
        throw new Error("cache update bug");
      },
    });
    sockets[0]?.open();
    sockets[0]?.message('{"a":1}');
    expect(warn).not.toHaveBeenCalledWith("Dropping malformed realtime message", expect.anything());
    expect(error).toHaveBeenCalledWith("Realtime message handler failed", expect.any(Error));
    warn.mockRestore();
    error.mockRestore();
  });

  it("reconnects with 1, 2, 4... seconds backoff capped at 30", () => {
    const { sock, sockets, statuses } = setup();
    const delays = [1000, 2000, 4000, 8000, 16000, 30000, 30000];
    delays.forEach((delay, i) => {
      sock(i).serverClose(1006);
      expect(statuses.at(-1)).toBe("reconnecting");
      vi.advanceTimersByTime(delay - 1);
      expect(sockets).toHaveLength(i + 1);
      vi.advanceTimersByTime(1);
      expect(sockets).toHaveLength(i + 2);
    });
  });

  it("resets the backoff after a successful open and flags reconnects", () => {
    const { sock, sockets, opens } = setup();
    sock(0).serverClose(1006);
    vi.advanceTimersByTime(1000);
    sock(1).serverClose(1006);
    vi.advanceTimersByTime(2000);
    sock(2).open();
    sock(2).serverClose(1006);
    vi.advanceTimersByTime(1000);
    expect(sockets).toHaveLength(4);
    sock(3).open();
    expect(opens).toEqual([false, true]);
  });

  it("reconnects after a 1011 internal error", () => {
    const { sock, sockets } = setup();
    sock(0).serverClose(1011);
    vi.advanceTimersByTime(1000);
    expect(sockets).toHaveLength(2);
  });

  it.each([
    [4403, "forbidden"],
    [4404, "not_found"],
  ] as const)("does not reconnect after %i", (code, status) => {
    const { sock, sockets, statuses } = setup();
    sock(0).serverClose(code);
    expect(statuses.at(-1)).toBe(status);
    vi.advanceTimersByTime(60_000);
    expect(sockets).toHaveLength(1);
  });

  it("treats a throwing socket factory as a failed attempt and backs off", () => {
    const statuses: SocketStatus[] = [];
    let calls = 0;
    const socket = createReconnectingSocket({
      url: "not a url",
      socketFactory: () => {
        calls += 1;
        throw new SyntaxError("bad url");
      },
      onMessage: () => {},
      onStatus: (s) => statuses.push(s),
    });
    expect(calls).toBe(1);
    expect(statuses).toEqual(["connecting", "reconnecting"]);
    vi.advanceTimersByTime(999);
    expect(calls).toBe(1);
    vi.advanceTimersByTime(1);
    expect(calls).toBe(2);
    vi.advanceTimersByTime(1999);
    expect(calls).toBe(2);
    vi.advanceTimersByTime(1);
    expect(calls).toBe(3);

    socket.close();
    vi.advanceTimersByTime(60_000);
    expect(calls).toBe(3);
    expect(statuses.at(-1)).toBe("closed");
  });

  it("close() stops reconnecting and closes the socket", () => {
    const { sock, sockets, statuses, socket } = setup();
    sock(0).serverClose(1006);
    socket.close();
    vi.advanceTimersByTime(60_000);
    expect(sockets).toHaveLength(1);
    expect(statuses.at(-1)).toBe("closed");

    const second = setup();
    second.sock(0).open();
    second.socket.close();
    expect(second.sock(0).closedByClient).toBe(true);
    second.sock(0).message('{"late":true}');
    expect(second.messages).toEqual([]);
  });
});
