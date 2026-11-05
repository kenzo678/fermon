export type SocketStatus =
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed"
  | "forbidden"
  | "not_found";

/** The subset of the browser WebSocket this module needs (also what test fakes implement). */
export interface SocketLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  close: () => void;
}

export interface ReconnectingSocketOptions {
  url: string;
  onMessage: (data: unknown) => void;
  onStatus?: (status: SocketStatus) => void;
  /** Called on every successful open; `isReconnect` is true from the second open on. */
  onOpen?: (isReconnect: boolean) => void;
  socketFactory?: (url: string) => SocketLike;
}

export interface ReconnectingSocket {
  close: () => void;
}

const FIRST_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;
const CLOSE_FORBIDDEN_ORIGIN = 4403;
const CLOSE_TANK_NOT_FOUND = 4404;

const defaultFactory = (url: string): SocketLike => new WebSocket(url);

/**
 * WebSocket that reconnects with exponential backoff (1 s doubling up to 30 s, reset after an
 * open). Close codes 4403/4404 are terminal; any other close, including 1011, reconnects.
 */
export function createReconnectingSocket({
  url,
  onMessage,
  onStatus,
  onOpen,
  socketFactory = defaultFactory,
}: ReconnectingSocketOptions): ReconnectingSocket {
  let socket: SocketLike | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;
  let hasOpened = false;
  let stopped = false;

  const setStatus = (status: SocketStatus) => onStatus?.(status);

  function scheduleReconnect(): void {
    setStatus("reconnecting");
    const delay = Math.min(FIRST_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
    attempt += 1;
    timer = setTimeout(connect, delay);
  }

  function connect(): void {
    timer = undefined;
    let current: SocketLike;
    try {
      current = socketFactory(url);
    } catch {
      scheduleReconnect();
      return;
    }
    socket = current;
    current.onopen = () => {
      attempt = 0;
      const isReconnect = hasOpened;
      hasOpened = true;
      setStatus("open");
      onOpen?.(isReconnect);
    };
    current.onmessage = (event) => {
      let message: unknown;
      try {
        message = JSON.parse(String(event.data));
      } catch (error) {
        console.warn("Dropping malformed realtime message", error);
        return;
      }
      // Parse and consume are separate so a consumer bug is never reported as a bad payload.
      try {
        onMessage(message);
      } catch (error) {
        console.error("Realtime message handler failed", error);
      }
    };
    current.onclose = (event) => {
      socket = null;
      if (event.code === CLOSE_FORBIDDEN_ORIGIN) setStatus("forbidden");
      else if (event.code === CLOSE_TANK_NOT_FOUND) setStatus("not_found");
      else scheduleReconnect();
    };
  }

  setStatus("connecting");
  connect();

  return {
    close() {
      if (stopped) return;
      stopped = true;
      clearTimeout(timer);
      if (socket !== null) {
        socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null;
        socket.close();
        socket = null;
      }
      setStatus("closed");
    },
  };
}
