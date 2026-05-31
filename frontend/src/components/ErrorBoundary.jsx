import React from "react";
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="m-4 rounded-md border border-red-200 bg-red-50 p-4 text-red-700">
          Something went wrong. Please refresh or try again.
        </div>
      );
    }
    return this.props.children;
  }
}
