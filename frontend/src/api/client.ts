import axios from "axios"

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      const refreshToken = localStorage.getItem("refresh_token")
      if (refreshToken) {
        try {
          const { data } = await axios.post("/api/v1/auth/refresh", {
            refresh_token: refreshToken,
          })
          localStorage.setItem("access_token", data.access_token)
          localStorage.setItem("refresh_token", data.refresh_token)
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`
          return api(originalRequest)
        } catch {
          localStorage.removeItem("access_token")
          localStorage.removeItem("refresh_token")
          window.location.href = "/login"
        }
      } else {
        window.location.href = "/login"
      }
    }
    return Promise.reject(error)
  }
)

export default api

import type { Me } from "@/store/auth"

export interface UserSummary {
  id: string
  username: string
  email: string | null
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  must_change_password: boolean
  last_login_at: string | null
  role_codes: string[]
  page_acls: string[]
  created_at: string
  updated_at: string
}

export interface RoleSummary {
  id: string
  code: string
  name: string
  description: string | null
  is_system: boolean
  permission_codes: string[]
  created_at: string
  updated_at: string
}

export interface UserCreateBody {
  username: string
  password: string
  email?: string | null
  full_name?: string | null
  is_active?: boolean
  role_codes?: string[]
  page_acls?: string[]
}

export interface UserUpdateBody {
  email?: string | null
  full_name?: string | null
  is_active?: boolean
  role_codes?: string[]
  page_acls?: string[]
}

export const fetchMe = () =>
  api.get<Me>("/me").then((r) => r.data)

export const listUsers = (params: { page?: number; page_size?: number } = {}) =>
  api
    .get<{ items: UserSummary[]; total: number; page: number; page_size: number; pages: number }>(
      "/users",
      { params }
    )
    .then((r) => r.data)

export const createUser = (body: UserCreateBody) =>
  api.post<UserSummary>("/users", body).then((r) => r.data)

export const updateUser = (id: string, body: UserUpdateBody) =>
  api.put<UserSummary>(`/users/${id}`, body).then((r) => r.data)

export const deleteUser = (id: string) =>
  api.delete(`/users/${id}`).then(() => undefined)

export const resetUserPassword = (id: string) =>
  api
    .post<{ new_password: string }>(`/users/${id}/reset-password`)
    .then((r) => r.data)

export const listRoles = () =>
  api.get<RoleSummary[]>("/roles").then((r) => r.data)

export const changeMyPassword = (oldPw: string, newPw: string) =>
  api
    .post("/me/change-password", { old_password: oldPw, new_password: newPw })
    .then(() => undefined)

// ===== Projects =====

export type SourceType = "zip" | "git"
export type DistributionStatus = "pending" | "synced" | "failed" | "stale"

export interface ProjectSummary {
  id: string
  name: string
  description: string | null
  source_type: SourceType
  work_path: string
  owner_id: string | null
  default_node_id: string | null
  default_env_id: string | null
  tags: string[] | null
  current_hash: string | null
  created_at: string
  updated_at: string
}

export interface GitRepoInfo {
  url: string
  branch: string
  username: string | null
  sync_interval_seconds: number | null
  last_sync_at: string | null
  last_commit: string | null
  last_error: string | null
}

export interface DistributionInfo {
  node_id: string
  status: DistributionStatus
  last_synced_at: string | null
  current_hash: string | null
  last_error: string | null
}

export interface ProjectDetail extends ProjectSummary {
  git: GitRepoInfo | null
  distributions: DistributionInfo[]
}

export interface ProjectCreateBody {
  name: string
  description?: string | null
  source_type: SourceType
  work_path?: string
  default_node_id?: string | null
  default_env_id?: string | null
  tags?: string[]
  git?: {
    url: string
    branch?: string
    username?: string | null
    password?: string | null
    sync_interval_seconds?: number | null
  }
}

export interface ProjectUpdateBody {
  description?: string | null
  work_path?: string
  default_node_id?: string | null
  default_env_id?: string | null
  tags?: string[]
}

export interface ProjectFileEntry {
  name: string
  path: string
  is_dir: boolean
  size: number
  mtime: string
}

export const listProjects = (params: { page?: number; page_size?: number; search?: string } = {}) =>
  api
    .get<{ items: ProjectSummary[]; total: number; page: number; page_size: number; pages: number }>(
      "/projects",
      { params }
    )
    .then((r) => r.data)

export const getProject = (id: string) =>
  api.get<ProjectDetail>(`/projects/${id}`).then((r) => r.data)

export const createGitProject = (body: ProjectCreateBody) =>
  api.post<ProjectDetail>("/projects", body).then((r) => r.data)

export const createZipProject = (body: ProjectCreateBody, file: File) => {
  const fd = new FormData()
  fd.append("body", JSON.stringify(body))
  fd.append("file", file)
  return api
    .post<ProjectDetail>("/projects", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data)
}

export const updateProject = (id: string, body: ProjectUpdateBody) =>
  api.put<ProjectDetail>(`/projects/${id}`, body).then((r) => r.data)

export const deleteProject = (id: string) =>
  api.delete(`/projects/${id}`).then(() => undefined)

export const listProjectFiles = (id: string, path = "") =>
  api
    .get<ProjectFileEntry[]>(`/projects/${id}/files`, { params: { path } })
    .then((r) => r.data)

export const readProjectFile = (id: string, path: string) =>
  api
    .get<{ path: string; content: string }>(`/projects/${id}/file`, { params: { path } })
    .then((r) => r.data)

export const writeProjectFile = (id: string, path: string, content: string) =>
  api
    .put<{ path: string; hash: string }>(`/projects/${id}/file`, { content }, { params: { path } })
    .then((r) => r.data)

export const deleteProjectFile = (id: string, path: string) =>
  api
    .delete<{ path: string; hash: string }>(`/projects/${id}/file`, { params: { path } })
    .then((r) => r.data)

export const triggerGitSync = (id: string) =>
  api
    .post<{ last_commit: string; last_sync_at: string; files_changed: number }>(
      `/projects/${id}/git/sync`
    )
    .then((r) => r.data)

// ===== Tasks =====

export type ScheduleType = "immediate" | "interval" | "once" | "cron"
export type NodeStrategy = "auto" | "master" | "specific" | "group" | "platform" | "mixed"
export type ConcurrentPolicy = "skip" | "queue"
export type RunStatus =
  | "pending"
  | "dispatching"
  | "running"
  | "success"
  | "failed"
  | "timeout"
  | "killed"
  | "skipped"

export interface TaskSummary {
  id: string
  name: string
  description: string | null
  project_id: string
  env_id: string | null
  command: string
  schedule_type: ScheduleType
  schedule_config: Record<string, unknown> | null
  node_strategy: NodeStrategy
  node_target: Record<string, unknown> | null
  max_concurrent: number
  concurrent_policy: ConcurrentPolicy
  max_retries: number
  timeout_sec: number
  is_active: boolean
  tags: string[] | null
  owner_id: string | null
  created_at: string
  updated_at: string
}

export interface TaskDetail extends TaskSummary {
  depends_on: string[]
  next_run_at: string | null
}

export interface TaskRunSummary {
  id: string
  task_id: string
  node_id: string | null
  status: RunStatus
  started_at: string | null
  finished_at: string | null
  exit_code: number | null
  retry_no: number
  error_msg: string | null
  triggered_by: string | null
  created_at: string
  updated_at: string
}

export interface TaskCreateBody {
  name: string
  description?: string | null
  project_id: string
  env_id?: string | null
  command: string
  schedule_type: ScheduleType
  schedule_config?: Record<string, unknown>
  node_strategy?: NodeStrategy
  node_target?: Record<string, unknown>
  max_concurrent?: number
  concurrent_policy?: ConcurrentPolicy
  max_retries?: number
  timeout_sec?: number
  is_active?: boolean
  tags?: string[]
  depends_on?: string[]
}

export const listTasks = (params: { page?: number; page_size?: number; project_id?: string; search?: string } = {}) =>
  api
    .get<{ items: TaskSummary[]; total: number; page: number; page_size: number; pages: number }>(
      "/tasks",
      { params }
    )
    .then((r) => r.data)

export const getTask = (id: string) =>
  api.get<TaskDetail>(`/tasks/${id}`).then((r) => r.data)

export interface TaskDagNode {
  id: string
  name: string
  is_active: boolean
  role: "self" | "upstream" | "downstream"
}
export interface TaskDagEdge {
  source: string
  target: string
  on_status: string
}
export const getTaskDag = (id: string) =>
  api
    .get<{ nodes: TaskDagNode[]; edges: TaskDagEdge[] }>(`/tasks/${id}/dag`)
    .then((r) => r.data)

export const createTask = (body: TaskCreateBody) =>
  api.post<TaskDetail>("/tasks", body).then((r) => r.data)

export const updateTask = (id: string, body: Partial<TaskCreateBody>) =>
  api.put<TaskDetail>(`/tasks/${id}`, body).then((r) => r.data)

export const deleteTask = (id: string) =>
  api.delete(`/tasks/${id}`).then(() => undefined)

export const runTaskNow = (id: string) =>
  api.post<{ run_id: string }>(`/tasks/${id}/run`).then((r) => r.data)

export const batchPauseTasks = (ids: string[]) =>
  api
    .post<{ affected: number; skipped: number }>("/tasks/batch/pause", { ids })
    .then((r) => r.data)
export const batchResumeTasks = (ids: string[]) =>
  api
    .post<{ affected: number; skipped: number }>("/tasks/batch/resume", { ids })
    .then((r) => r.data)
export const batchDeleteTasks = (ids: string[]) =>
  api
    .post<{ deleted: number; skipped: number }>("/tasks/batch/delete", { ids })
    .then((r) => r.data)

export const pauseTask = (id: string) =>
  api.post<TaskDetail>(`/tasks/${id}/pause`).then((r) => r.data)

export const resumeTask = (id: string) =>
  api.post<TaskDetail>(`/tasks/${id}/resume`).then((r) => r.data)

export const listTaskRuns = (id: string, params: { page?: number; page_size?: number } = {}) =>
  api
    .get<{ items: TaskRunSummary[]; total: number; page: number; page_size: number; pages: number }>(
      `/tasks/${id}/runs`,
      { params }
    )
    .then((r) => r.data)

export const killRun = (runId: string) =>
  api.post(`/tasks/runs/${runId}/kill`).then(() => undefined)

// ===== Python Versions / Mirrors / Environments =====

export type PyVerStatus = "downloading" | "building" | "ready" | "failed"
export type EnvStatus = "creating" | "ready" | "updating" | "failed"

export interface PythonVersionInfo {
  id: string
  version: string
  status: PyVerStatus
  tarball_url: string | null
  install_path: string | null
  is_default: boolean
  error_msg: string | null
  created_at: string
  updated_at: string
}

export interface MirrorInfo {
  id: string
  name: string
  url: string
  is_default: boolean
  is_builtin: boolean
  created_at: string
  updated_at: string
}

export interface EnvironmentInfo {
  id: string
  name: string
  description: string | null
  node_id: string | null
  python_version_id: string | null
  mirror_id: string | null
  requirements: string | null
  venv_path: string | null
  status: EnvStatus
  tags: string[] | null
  error_msg: string | null
  owner_id: string | null
  created_at: string
  updated_at: string
}

export const listPyVers = () =>
  api.get<PythonVersionInfo[]>("/python-versions").then((r) => r.data)

export const createPyVer = (version: string, tarball_url: string) =>
  api
    .post<PythonVersionInfo>("/python-versions", { version, tarball_url })
    .then((r) => r.data)

export const deletePyVer = (id: string) =>
  api.delete(`/python-versions/${id}`).then(() => undefined)

export const setDefaultPyVer = (id: string) =>
  api.post<PythonVersionInfo>(`/python-versions/${id}/set-default`).then((r) => r.data)

export const listMirrors = () =>
  api.get<MirrorInfo[]>("/mirror-sources").then((r) => r.data)

export const createMirror = (body: { name: string; url: string; is_default?: boolean }) =>
  api.post<MirrorInfo>("/mirror-sources", body).then((r) => r.data)

export const deleteMirror = (id: string) =>
  api.delete(`/mirror-sources/${id}`).then(() => undefined)

export const listEnvironments = (params: { page?: number; page_size?: number } = {}) =>
  api
    .get<{ items: EnvironmentInfo[]; total: number; page: number; page_size: number; pages: number }>(
      "/environments",
      { params }
    )
    .then((r) => r.data)

export const createEnvironment = (body: {
  name: string
  description?: string | null
  node_id?: string | null
  python_version_id?: string | null
  mirror_id?: string | null
  requirements?: string | null
  tags?: string[]
}) =>
  api.post<EnvironmentInfo>("/environments", body).then((r) => r.data)

export const rebuildEnvironment = (id: string) =>
  api.post<EnvironmentInfo>(`/environments/${id}/rebuild`).then((r) => r.data)

export const deleteEnvironment = (id: string) =>
  api.delete(`/environments/${id}`).then(() => undefined)

// ===== Dashboard =====

export interface DashOverview {
  total_projects: number
  total_tasks: number
  active_tasks: number
  paused_tasks: number
  total_envs: number
  total_workers: number
  online_workers: number
  running_runs: number
  today_total: number
  today_success: number
  success_rate: number
  cluster_health: "healthy" | "degraded" | "down"
  uptime_seconds: number
  services: { master: string; postgres: string; redis: string }
  recent_failures: {
    run_id: string
    task_id: string
    task_name: string
    status: string
    finished_at: string | null
    error_msg: string | null
  }[]
}

export interface DashPerfStats {
  peak: number
  avg: number
  anomaly_count: number
}

export interface DashPerf {
  series: {
    ts: string
    cpu: number
    mem: number
    disk: number
    net_in: number
    net_out: number
  }[]
  stats: {
    cpu: DashPerfStats
    mem: DashPerfStats
    disk: DashPerfStats
    net_in: DashPerfStats
    net_out: DashPerfStats
  }
  per_node: {
    node_id: string
    name: string
    cpu: number
    mem: number
    disk: number
  }[]
  workers: { node_id: string; cpu: number; mem: number; status: string }[]
}

export type Granularity = "hour" | "day" | "month"

export interface DashTasks {
  summary: {
    total: number
    success: number
    failed: number
    timeout: number
    killed: number
    skipped: number
    running: number
    pending: number
    dispatching: number
    paused_tasks: number
    success_rate: number
    avg_duration_sec: number
  }
  granularity: Granularity
  trend: { bucket: string | null; total: number; success: number }[]
  hour_distribution: { hour: number; count: number }[]
  calendar: { date: string; count: number }[]
  duration_histogram: { bucket: string; count: number }[]
  node_distribution: {
    node_id: string
    name: string
    total: number
    success: number
    success_rate: number
  }[]
  project_ranking: {
    project_id: string
    name: string
    total: number
    success: number
    success_rate: number
  }[]
}

export interface DashWorkerItem {
  id: string
  node_id: string
  name: string
  type: "master_local" | "remote"
  status: string
  hostname: string
  ip: string
  port: number
  os: string | null
  arch: string | null
  python_version: string | null
  labels: string[]
  group_id: string | null
  group_name: string | null
  max_slots: number
  current_tasks: number
  cpu_usage: number
  mem_usage: number
  last_heartbeat: string | null
  uptime_seconds: number
  connection_quality: "excellent" | "good" | "poor" | "lost" | "never"
  history: { ts: string; cpu: number; mem: number; disk: number }[]
  task_summary: {
    total: number
    success: number
    failed: number
    success_rate: number
  }
}

export interface DashCharts {
  granularity: Granularity
  execution_volume: {
    bucket: string | null
    total: number
    success: number
    success_rate: number
  }[]
  task_type_distribution: { name: string; value: number }[]
  project_load: { name: string; value: number }[]
  node_load: { name: string; value: number }[]
}

export interface DashGanttItem {
  run_id: string
  task_id: string
  task_name: string
  started_at: string | null
  finished_at: string | null
  status: RunStatus
  node_id: string | null
}

export const fetchOverview = () =>
  api.get<DashOverview>("/dashboard/overview").then((r) => r.data)

export const fetchPerf = (range: string = "1h") =>
  api.get<DashPerf>("/dashboard/perf", { params: { range } }).then((r) => r.data)

export const fetchTasksDash = (
  range: string = "24h",
  granularity: Granularity = "hour"
) =>
  api
    .get<DashTasks>("/dashboard/tasks", { params: { range, granularity } })
    .then((r) => r.data)

export const fetchWorkersDash = () =>
  api
    .get<{ items: DashWorkerItem[] }>("/dashboard/workers")
    .then((r) => r.data)

export const fetchCharts = (
  range: string = "24h",
  granularity: Granularity = "hour"
) =>
  api
    .get<DashCharts>("/dashboard/charts", { params: { range, granularity } })
    .then((r) => r.data)

export const fetchGantt = (date?: string) =>
  api
    .get<{ date: string; items: DashGanttItem[] }>("/dashboard/gantt", {
      params: date ? { date } : undefined,
    })
    .then((r) => r.data)

// ===== Ops =====

export type ChannelType = "dingtalk" | "feishu" | "wecom" | "email"
export type EventType =
  | "task_failed"
  | "task_timeout"
  | "task_killed"
  | "worker_offline"

export interface NotificationChannel {
  id: string
  type: ChannelType
  name: string
  is_enabled: boolean
  has_secret: boolean
  template: string | null
  created_at: string
  updated_at: string
}

export interface NotificationRule {
  id: string
  channel_id: string
  event: EventType
  filter: Record<string, unknown> | null
  created_at: string
}

export const listChannels = () =>
  api.get<NotificationChannel[]>("/notification-channels").then((r) => r.data)

export const createChannel = (body: {
  type: ChannelType
  name: string
  config: Record<string, unknown>
  is_enabled?: boolean
  template?: string | null
}) =>
  api.post<NotificationChannel>("/notification-channels", body).then((r) => r.data)

export const updateChannel = (
  id: string,
  body: {
    name?: string
    config?: Record<string, unknown>
    is_enabled?: boolean
    template?: string | null
  }
) => api.put<NotificationChannel>(`/notification-channels/${id}`, body).then((r) => r.data)

export const deleteChannel = (id: string) =>
  api.delete(`/notification-channels/${id}`).then(() => undefined)

export const testChannel = (id: string) =>
  api.post(`/notification-channels/${id}/test`).then(() => undefined)

export const listRules = () =>
  api.get<NotificationRule[]>("/notification-rules").then((r) => r.data)

export const createRule = (body: {
  channel_id: string
  event: EventType
  filter?: Record<string, unknown>
}) => api.post<NotificationRule>("/notification-rules", body).then((r) => r.data)

export const deleteRule = (id: string) =>
  api.delete(`/notification-rules/${id}`).then(() => undefined)

export interface SmtpSettings {
  host: string | null
  port: number
  username: string | null
  from_addr: string | null
  use_tls: boolean
  is_enabled: boolean
}

export const getSmtp = () => api.get<SmtpSettings>("/smtp-settings").then((r) => r.data)

export const updateSmtp = (body: SmtpSettings & { password?: string | null }) =>
  api.put<SmtpSettings>("/smtp-settings", body).then((r) => r.data)

export interface PersistentFile {
  name: string
  path: string
  is_dir: boolean
  size: number
  mtime: string
}

export const listPersistentFiles = (path = "") =>
  api.get<PersistentFile[]>("/files", { params: { path } }).then((r) => r.data)

export const makePersistentFolder = (path: string) =>
  api.post(`/files/folder`, null, { params: { path } }).then(() => undefined)

export const uploadPersistentFile = (path: string, file: File) => {
  const fd = new FormData()
  fd.append("file", file)
  return api
    .post<{ path: string; script_path: string }>(`/files/upload`, fd, {
      params: { path },
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data)
}

export const deletePersistentFile = (path: string) =>
  api.delete(`/files`, { params: { path } }).then(() => undefined)

export interface LogFileEntry {
  run_id: string
  task_id: string | null
  task_name: string | null
  file_name: string
  size: number
  created_at: string
}

export const listLogs = (limit = 100) =>
  api.get<LogFileEntry[]>("/logs", { params: { limit } }).then((r) => r.data)

export const deleteLog = (run_id: string) =>
  api.delete(`/logs/${run_id}`).then(() => undefined)

export const getLogRetention = () =>
  api
    .get<{ days_to_keep: number; is_enabled: boolean; last_run_at: string | null }>(
      "/logs/retention"
    )
    .then((r) => r.data)

export const setLogRetention = (body: { days_to_keep: number; is_enabled: boolean }) =>
  api.put("/logs/retention", body).then(() => undefined)

export const cleanupLogsNow = () =>
  api
    .post<{ deleted: number; older_than_days: number }>("/logs/cleanup")
    .then((r) => r.data)

// ===== Workers / Worker Groups =====

export interface WorkerSummary {
  id: string
  node_id: string
  name: string
  hostname: string
  ip: string
  port: number
  type: "master_local" | "remote"
  os: string | null
  arch: string | null
  python_version: string | null
  status: string
  current_tasks: number
  max_slots: number
  labels: string[] | null
  cpu_usage: number
  mem_usage: number
  last_heartbeat: string | null
  group_id: string | null
}

export interface WorkerCreateBody {
  name: string
  hostname: string
  ip: string
  port?: number
  type?: "remote" | "master_local"
  labels?: string[]
  max_slots?: number
  group_id?: string | null
}

export interface WorkerCreated extends WorkerSummary {
  api_key: string
}

export interface WorkerUpdateBody {
  name?: string
  hostname?: string
  ip?: string
  port?: number
  labels?: string[]
  max_slots?: number
  group_id?: string | null
}

export const listWorkers = () =>
  api
    .get<{ items: WorkerSummary[]; total: number; page: number; pages: number }>(
      "/workers"
    )
    .then((r) => r.data)

export const createWorker = (body: WorkerCreateBody) =>
  api.post<WorkerCreated>("/workers", body).then((r) => r.data)

export const updateWorker = (id: string, body: WorkerUpdateBody) =>
  api.patch<WorkerSummary>(`/workers/${id}`, body).then((r) => r.data)

export const deleteWorker = (id: string) =>
  api.delete(`/workers/${id}`).then(() => undefined)

export interface WorkerGroup {
  id: string
  name: string
  description: string | null
  tags: string[]
  worker_count: number
  created_at: string
  updated_at: string
}

export const listWorkerGroups = () =>
  api.get<WorkerGroup[]>("/worker-groups").then((r) => r.data)

export const createWorkerGroup = (body: {
  name: string
  description?: string | null
  tags?: string[]
}) => api.post<WorkerGroup>("/worker-groups", body).then((r) => r.data)

export const updateWorkerGroup = (
  id: string,
  body: { name?: string; description?: string | null; tags?: string[] }
) => api.patch<WorkerGroup>(`/worker-groups/${id}`, body).then((r) => r.data)

export const deleteWorkerGroup = (id: string) =>
  api.delete(`/worker-groups/${id}`).then(() => undefined)

// ===== Collaborators =====

export interface CollaboratorRow {
  user_id: string
  username: string
  full_name: string | null
  added_at: string
}

export const listProjectCollaborators = (projectId: string) =>
  api
    .get<CollaboratorRow[]>(`/projects/${projectId}/collaborators`)
    .then((r) => r.data)

export const addProjectCollaborator = (projectId: string, userId: string) =>
  api
    .post(`/projects/${projectId}/collaborators`, { user_id: userId })
    .then((r) => r.data)

export const removeProjectCollaborator = (projectId: string, userId: string) =>
  api
    .delete(`/projects/${projectId}/collaborators/${userId}`)
    .then(() => undefined)

export const listEnvCollaborators = (envId: string) =>
  api
    .get<CollaboratorRow[]>(`/environments/${envId}/collaborators`)
    .then((r) => r.data)

export const addEnvCollaborator = (envId: string, userId: string) =>
  api
    .post(`/environments/${envId}/collaborators`, { user_id: userId })
    .then((r) => r.data)

export const removeEnvCollaborator = (envId: string, userId: string) =>
  api
    .delete(`/environments/${envId}/collaborators/${userId}`)
    .then(() => undefined)
