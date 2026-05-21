import { lazy, Suspense } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Toaster, toast } from "sonner"
import { useAuthStore } from "@/store/auth"
import { Layout } from "@/components/layout"
import { ThemeProvider } from "@/components/theme-provider"
import { TooltipProvider } from "@/components/ui/tooltip"
import { CommandPalette } from "@/components/command-palette"
import { LoginPage } from "@/pages/login"
import { DashboardPage } from "@/pages/dashboard"

// Heavy pages — lazy load so initial bundle stays small
const ProjectsPage = lazy(() => import("@/pages/projects").then(m => ({ default: m.ProjectsPage })))
const ProjectDetailPage = lazy(() => import("@/pages/project-detail").then(m => ({ default: m.ProjectDetailPage })))
const TasksPage = lazy(() => import("@/pages/tasks").then(m => ({ default: m.TasksPage })))
const TaskDetailPage = lazy(() => import("@/pages/task-detail").then(m => ({ default: m.TaskDetailPage })))
const WorkersPage = lazy(() => import("@/pages/workers").then(m => ({ default: m.WorkersPage })))
const WorkerGroupsPage = lazy(() => import("@/pages/worker-groups").then(m => ({ default: m.WorkerGroupsPage })))
const EnvironmentsPage = lazy(() => import("@/pages/environments").then(m => ({ default: m.EnvironmentsPage })))
const PythonVersionsPage = lazy(() => import("@/pages/python-versions").then(m => ({ default: m.PythonVersionsPage })))
const MirrorSourcesPage = lazy(() => import("@/pages/mirror-sources").then(m => ({ default: m.MirrorSourcesPage })))
const EnvVarsPage = lazy(() => import("@/pages/env-vars").then(m => ({ default: m.EnvVarsPage })))
const UsersPage = lazy(() => import("@/pages/users").then(m => ({ default: m.UsersPage })))
const NotificationsPage = lazy(() => import("@/pages/notifications").then(m => ({ default: m.NotificationsPage })))
const FilesPage = lazy(() => import("@/pages/files").then(m => ({ default: m.FilesPage })))
const LogsPage = lazy(() => import("@/pages/logs").then(m => ({ default: m.LogsPage })))
const SettingsPage = lazy(() => import("@/pages/settings").then(m => ({ default: m.SettingsPage })))
const AuditPage = lazy(() => import("@/pages/audit").then(m => ({ default: m.AuditPage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
    mutations: {
      onError: (err: any) => {
        const msg = err?.response?.data?.detail || err?.message || "操作失败"
        toast.error(typeof msg === "string" ? msg : "操作失败")
      },
    },
  },
})

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
      加载中…
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={300}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route
                path="projects"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <ProjectsPage />
                  </Suspense>
                }
              />
              <Route
                path="projects/:projectId"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <ProjectDetailPage />
                  </Suspense>
                }
              />
              <Route
                path="tasks"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <TasksPage />
                  </Suspense>
                }
              />
              <Route
                path="tasks/:taskId"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <TaskDetailPage />
                  </Suspense>
                }
              />
              <Route
                path="workers"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <WorkersPage />
                  </Suspense>
                }
              />
              <Route
                path="worker-groups"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <WorkerGroupsPage />
                  </Suspense>
                }
              />
              <Route
                path="environments"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <EnvironmentsPage />
                  </Suspense>
                }
              />
              <Route
                path="python-versions"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <PythonVersionsPage />
                  </Suspense>
                }
              />
              <Route
                path="mirror-sources"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <MirrorSourcesPage />
                  </Suspense>
                }
              />
              <Route
                path="env-vars"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <EnvVarsPage />
                  </Suspense>
                }
              />
              <Route
                path="users"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <UsersPage />
                  </Suspense>
                }
              />
              <Route
                path="notifications"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <NotificationsPage />
                  </Suspense>
                }
              />
              <Route
                path="files"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <FilesPage />
                  </Suspense>
                }
              />
              <Route
                path="logs"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <LogsPage />
                  </Suspense>
                }
              />
              <Route
                path="settings"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <SettingsPage />
                  </Suspense>
                }
              />
              <Route
                path="audit"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <AuditPage />
                  </Suspense>
                }
              />
            </Route>
          </Routes>
          <CommandPalette />
        </BrowserRouter>
        <Toaster richColors position="top-right" closeButton />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
