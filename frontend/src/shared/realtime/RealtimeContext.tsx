import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import type { SocketLike } from "./reconnectingSocket";

type SocketFactory = (url: string) => SocketLike;

const defaultFactory: SocketFactory = (url) => new WebSocket(url);

const SocketFactoryContext = createContext<SocketFactory>(defaultFactory);

/**
 * Dependency injection point for the WebSocket implementation. The app uses the native
 * WebSocket by default; tests wrap the tree in a provider with a fake factory.
 */
export function RealtimeProvider({
  socketFactory,
  children,
}: {
  socketFactory: SocketFactory;
  children: ReactNode;
}) {
  return <SocketFactoryContext.Provider value={socketFactory}>{children}</SocketFactoryContext.Provider>;
}

export function useSocketFactory(): SocketFactory {
  return useContext(SocketFactoryContext);
}
