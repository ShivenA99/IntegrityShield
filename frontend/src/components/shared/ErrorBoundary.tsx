import React from "react";

interface ErrorBoundaryState {
  hasError: boolean;
  message?: string;
}

class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  public state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("UI crashed", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <h2>Something went wrong.</h2>
          <p>{this.state.message ?? "Unexpected error"}</p>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
