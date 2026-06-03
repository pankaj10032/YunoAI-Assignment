import React, { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "@xyflow/react/dist/style.css";
import "./styles.css";

import ErrorToastHost from "./components/ErrorToast";
import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import { ToastProvider } from "./components/ToastProvider";

const AgentsPage = lazy(() => import("./pages/AgentsPage"));
const AgentConfigPage = lazy(() => import("./pages/AgentConfig"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const MonitorPage = lazy(() => import("./pages/Monitor"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const WorkflowsPage = lazy(() => import("./pages/WorkflowsPage"));

function PageLoader() {
  return (
    <div className="rounded-md border border-line bg-surface px-4 py-3 text-sm text-muted transition-colors">
      Loading...
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <BrowserRouter>
          <ErrorToastHost />
          <Suspense fallback={<PageLoader />}>
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
          </Suspense>
        </BrowserRouter>
      </ToastProvider>
    </ErrorBoundary>
  );
}
