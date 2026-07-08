import { Component, type ReactNode, type ErrorInfo } from "react";
import { AlertTriangle } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  label?: string;
}

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(err: unknown): State {
    const msg = err instanceof Error ? err.message : "An unexpected error occurred.";
    return { hasError: true, message: msg };
  }

  componentDidCatch(err: unknown, info: ErrorInfo) {
    // Log to the server or monitoring service in production
    void info;
    void err;
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div
          role="alert"
          className="flex flex-col items-center justify-center gap-3 p-8 text-center"
        >
          <AlertTriangle className="h-10 w-10 text-danger" aria-hidden="true" />
          <p className="text-base font-medium text-foreground">
            {this.props.label ?? "Something went wrong"}
          </p>
          <p className="text-sm text-muted-foreground max-w-sm">
            {this.state.message}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, message: "" })}
            className="mt-2 px-4 py-2 text-sm rounded-md bg-surface border border-border hover:bg-surface-hover transition-colors"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
