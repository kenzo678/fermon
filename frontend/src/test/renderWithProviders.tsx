import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { RealtimeProvider } from "../shared/realtime";
import type { SocketLike } from "../shared/realtime";
import { FakeSocket } from "./fakeSocket";

interface Options {
  route?: string;
  queryClient?: QueryClient;
  /** Defaults to an inert fake socket that never opens, so no test touches the network. */
  socketFactory?: (url: string) => SocketLike;
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
  }: Options = {},
) {
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
