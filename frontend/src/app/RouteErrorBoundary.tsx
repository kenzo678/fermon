import { Component, type ErrorInfo, type ReactNode } from "react";
import { Link, useLocation } from "react-router";

interface Props {
  children: ReactNode;
}

interface State {
  failed: boolean;
}

/**
 * Catches render errors of a lazily loaded route (e.g. a chunk removed by a redeploy or a flaky
 * mobile connection) so the app shell stays up with a way to recover.
 */
export class RouteErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Route failed to render", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-900">
        <p className="text-sm font-medium">This page failed to load. Check your connection and try again.</p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-md bg-red-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-800"
          >
            Reload
          </button>
          <Link to="/" className="self-center text-sm underline">
            Back to tanks
          </Link>
        </div>
      </div>
    );
  }
}

/** Error boundary that resets on navigation, so a failure on one tank doesn't stick to the next. */
export function RouteBoundary({ children }: Props) {
  const { pathname } = useLocation();
  return <RouteErrorBoundary key={pathname}>{children}</RouteErrorBoundary>;
}
