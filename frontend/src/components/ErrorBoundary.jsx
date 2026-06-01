import React from "react";

/**
 * ErrorBoundary — catches render crashes, reports them to the backend
 * telemetry endpoint (with correlation ID when available), and shows a
 * premium fallback UI with a "Retry" action.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorMessage: "", errorId: null };
    this._handleRetry = this._handleRetry.bind(this);
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      errorMessage: error?.message || "Unknown render error",
      errorId: `err-${Date.now().toString(36)}`,
    };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary] Uncaught render error:", error, info);
    this._reportToTelemetry(error, info);
  }

  _reportToTelemetry(error, info) {
    try {
      const payload = {
        event_type: "ui_render_error",
        source: "error_boundary",
        payload: {
          error_id: this.state.errorId,
          message: error?.message || "Unknown",
          stack: error?.stack?.slice(0, 1000),
          component_stack: info?.componentStack?.slice(0, 500),
          url: window.location.href,
          timestamp: new Date().toISOString(),
        },
      };
      // Fire-and-forget — do not block UI
      fetch("/api/telemetry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).catch(() => {});
    } catch (_) {
      // silently ignore telemetry failures
    }
  }

  _handleRetry() {
    this.setState({ hasError: false, errorMessage: "", errorId: null });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-fallback">
          <div className="error-boundary-icon">⚠️</div>
          <h2 className="error-boundary-title">Something went wrong</h2>
          <p className="error-boundary-body">
            An unexpected error occurred while rendering this section.
          </p>
          {this.state.errorMessage && (
            <code className="error-boundary-code">{this.state.errorMessage}</code>
          )}
          <div className="error-boundary-actions">
            <button
              id="error-boundary-retry-btn"
              className="error-boundary-btn-primary"
              onClick={this._handleRetry}
            >
              ↺ Retry
            </button>
            <button
              className="error-boundary-btn-secondary"
              onClick={() => window.location.reload()}
            >
              Reload Page
            </button>
          </div>
          {this.state.errorId && (
            <p className="error-boundary-id">Error ID: {this.state.errorId}</p>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}
