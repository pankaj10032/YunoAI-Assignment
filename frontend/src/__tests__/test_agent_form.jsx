import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import AgentForm from "../components/AgentForm";

describe("AgentForm", () => {
  it("validates guardrail JSON before submit", async () => {
    const onSubmit = vi.fn();
    render(<AgentForm onSubmit={onSubmit} onCancel={() => {}} isSaving={false} />);

    await userEvent.type(screen.getByLabelText("Name"), "Tester");
    await userEvent.click(screen.getByRole("tab", { name: "Guardrails" }));
    await userEvent.clear(screen.getByLabelText("Guardrails JSON"));
    await userEvent.click(screen.getByLabelText("Guardrails JSON"));
    await userEvent.paste("{bad");
    await userEvent.click(screen.getByRole("button", { name: "Save Agent" }));

    expect(await screen.findByText("Guardrails must be valid JSON.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits a valid agent payload", async () => {
    const onSubmit = vi.fn();
    render(<AgentForm onSubmit={onSubmit} onCancel={() => {}} isSaving={false} />);

    await userEvent.type(screen.getByLabelText("Name"), "Tester");
    await userEvent.click(screen.getByRole("button", { name: "Save Agent" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].name).toBe("Tester");
  });
});
