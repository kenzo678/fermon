import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { sessionKeys } from "../features/auth/api";
import type { User } from "../shared/api";
import { RealtimeProvider } from "../shared/realtime";
import type { SocketLike } from "../shared/realtime";
import { FakeSocket } from "./fakeSocket";
import { makeUser } from "./fixtures";

interface Options {
  route?: string;
  queryClient?: QueryClient;
  /** Defaults to an inert fake socket that never opens, so no test touches the network. */
  socketFactory?: (url: string) => SocketLike;
  /**
   * The signed-in user seeded into the session cache (an admin by default, so pages render their
   * full UI); `null` seeds "signed out", and `undefined` with `seedSession: false` leaves the
   * session unknown so the page fetches `/auth/me` itself.
   */
  user?: User | null;
  seedSession?: boolean;
}

/** A client with retries disabled so failing queries settle immediately. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

export function renderWithProviders(
  ui: ReactElement,
  {
    route = "/",
    queryClient = createTestQueryClient(),
    socketFactory = (url) => new FakeSocket(url),
    user = makeUser(),
    seedSession = true,
  }: Options = {},
) {
  if (seedSession) queryClient.setQueryData(sessionKeys.current(), user);
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RealtimeProvider socketFactory={socketFactory}>
          <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
        </RealtimeProvider>
      </QueryClientProvider>,
    ),
  };
}
