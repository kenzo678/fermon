import type { SocketLike } from "../shared/realtime/reconnectingSocket";

/** Hand-written WebSocket stand-in; tests drive it with open()/message()/close(). */
export class FakeSocket implements SocketLike {
  onopen: SocketLike["onopen"] = null;
  onmessage: SocketLike["onmessage"] = null;
  onclose: SocketLike["onclose"] = null;
  onerror: SocketLike["onerror"] = null;
  closedByClient = false;

  constructor(readonly url: string) {}

  open(): void {
    this.onopen?.(new Event("open"));
  }

  message(data: string): void {
    this.onmessage?.({ data } as MessageEvent);
  }

  /** Simulates the server (or network) closing the connection. */
  serverClose(code = 1006): void {
    this.onclose?.({ code } as CloseEvent);
  }

  /** What the code under test calls. */
  close(): void {
    this.closedByClient = true;
  }
}

/** Factory that records every socket it creates, per URL, so tests can drive them. */
export function createFakeSocketHub() {
  const sockets: FakeSocket[] = [];
  return {
    sockets,
    factory: (url: string): FakeSocket => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket;
    },
    /** The most recent socket opened for a URL ending with `suffix`. */
    latest: (suffix: string): FakeSocket => {
      const found = sockets.filter((s) => s.url.endsWith(suffix)).at(-1);
      if (found === undefined) throw new Error(`no socket for ${suffix}`);
      return found;
    },
  };
}
