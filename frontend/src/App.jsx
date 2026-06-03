import React from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "@xyflow/react/dist/style.css";
import "./styles.css";

import ErrorToastHost from "./components/ErrorToast";
import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import { ToastProvider } from "./components/ToastProvider";
import AgentsPage from "./pages/AgentsPage";
import AgentConfigPage from "./pages/AgentConfig";
import DashboardPage from "./pages/DashboardPage";
import MonitorPage from "./pages/Monitor";
import SettingsPage from "./pages/SettingsPage";
import WorkflowsPage from "./pages/WorkflowsPage";

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <BrowserRouter>
          <ErrorToastHost />
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/agents/config" element={<AgentConfigPage />} />
              <Route path="/workflows" element={<WorkflowsPage />} />
              <Route path="/monitor" element={<MonitorPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </ErrorBoundary>
  );
}
