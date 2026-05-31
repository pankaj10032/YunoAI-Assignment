import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../services/api", () => ({
  getRuns: vi.fn(() => Promise.resolve([])),
  getWorkflows: vi.fn(() => Promise.resolve([])),
  getAgents: vi.fn(() => Promise.resolve([])),
  getAllMessages: vi.fn(() => Promise.resolve([])),
  getMessages: vi.fn(() => Promise.resolve([])),
}));

vi.mock("../services/websocket", () => ({
  connectRunSocket: vi.fn(() => ({
    on: vi.fn(() => vi.fn()),
    close: vi.fn(),
  })),
}));

import MonitorPage from "../pages/MonitorPage";

describe("MonitorPage", () => {
  it("renders monitoring tabs", async () => {
    render(<MonitorPage />);

    expect(await screen.findByRole("button", { name: "Active Runs" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Message History" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Token Usage" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "System Logs" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("No workflow runs yet.")).toBeInTheDocument());
  });
});
