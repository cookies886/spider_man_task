import { useEffect, useRef, useState } from "react"
import { useParams, Link, useNavigate } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import ReactECharts from "echarts-for-react"
import { useReconnectingWs, type WsStatus } from "@/hooks/use-reconnecting-ws"
import {
  getTask,
  getTaskDag,
  listTaskRuns,
  runTaskNow,
  pauseTask,
  resumeTask,
  killRun,
  type TaskRunSummary,
  type RunStatus,
} from "@/api/client"
import api from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"

type LogLevel = "ALL" | "INFO" | "ERROR"

interface FilterState {
  level: LogLevel
  keyword: string
  autoScroll: boolean
}

export function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const qc = useQueryClient()

  const taskQ = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => getTask(taskId!),
    enabled: !!taskId,
  })
  const runsQ = useQuery({
    queryKey: ["task-runs", taskId],
    queryFn: () => listTaskRuns(taskId!, { page_size: 20 }),
    enabled: !!taskId,
    refetchInterval: 3000,
  })

  const runMut = useMutation({
    mutationFn: () => runTaskNow(taskId!),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["task-runs", taskId] })
      setActiveRunId(data.run_id)
      toast.success("已触发新一次运行")
    },
  })
  const pauseToggle = useMutation({
    mutationFn: () =>
      taskQ.data?.is_active ? pauseTask(taskId!) : resumeTask(taskId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  })

  const [activeRunId, setActiveRunId] = useState<string | null>(null)

  if (!taskId) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/tasks" className="text-sm text-muted-foreground hover:underline">
            ← 任务列表
          </Link>
          <h1 className="text-2xl font-semibold mt-1">
            {taskQ.data?.name ?? "..."}
          </h1>
        </div>
        <div className="space-x-2">
          <Button onClick={() => runMut.mutate()} disabled={runMut.isPending}>
            立即运行
          </Button>
          <Button variant="outline" onClick={() => pauseToggle.mutate()}>
            {taskQ.data?.is_active ? "暂停调度" : "启用调度"}
          </Button>
        </div>
      </div>

      {taskId && <DagCard taskId={taskId} />}

      {taskQ.data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">配置</CardTitle>
          </CardHeader>
          <CardContent className="text-sm grid grid-cols-2 gap-2">
            <div>命令: <span className="font-mono">{taskQ.data.command}</span></div>
            <div>调度: {taskQ.data.schedule_type}</div>
            <div>调度配置: <span className="font-mono">{JSON.stringify(taskQ.data.schedule_config)}</span></div>
            <div>节点策略: {taskQ.data.node_strategy}</div>
            <div>并发: {taskQ.data.max_concurrent} ({taskQ.data.concurrent_policy})</div>
            <div>重试: {taskQ.data.max_retries}</div>
            <div>超时: {taskQ.data.timeout_sec}s</div>
            <div>下次执行: {taskQ.data.next_run_at ? new Date(taskQ.data.next_run_at).toLocaleString() : "-"}</div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">执行历史</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-2">时间</th>
                <th>触发</th>
                <th>状态</th>
                <th>退出码</th>
                <th>重试</th>
                <th className="text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {runsQ.data?.items.map((r) => (
                <RunRow
                  key={r.id}
                  r={r}
                  active={r.id === activeRunId}
                  onPick={() => setActiveRunId(r.id)}
                  onRerun={() => runMut.mutate()}
                />
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {activeRunId && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center justify-between">
              <span>实时日志 — <span className="font-mono text-xs">{activeRunId}</span></span>
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive"
                onClick={() => {
                  if (confirm("强制终止这个 run?")) killRun(activeRunId)
                }}
              >
                强制终止
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LiveLog runId={activeRunId} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

const STATUS_COLOR: Record<RunStatus, string> = {
  pending: "text-muted-foreground",
  dispatching: "text-blue-600",
  running: "text-blue-600",
  success: "text-green-600",
  failed: "text-destructive",
  timeout: "text-amber-600",
  killed: "text-amber-600",
  skipped: "text-muted-foreground",
}

const TERMINAL_STATUSES: RunStatus[] = ["success", "failed", "timeout", "killed", "skipped"]

function RunRow({
  r,
  active,
  onPick,
  onRerun,
}: {
  r: TaskRunSummary
  active: boolean
  onPick: () => void
  onRerun: () => void
}) {
  const isFinished = TERMINAL_STATUSES.includes(r.status)
  return (
    <tr className={`border-t ${active ? "bg-muted/50" : ""}`}>
      <td className="py-2 text-xs text-muted-foreground">
        {new Date(r.created_at).toLocaleString()}
      </td>
      <td className="text-xs">{r.triggered_by ?? "-"}</td>
      <td className={`text-xs font-medium ${STATUS_COLOR[r.status]}`}>
        {r.status}
      </td>
      <td className="text-xs">{r.exit_code ?? "-"}</td>
      <td className="text-xs">{r.retry_no}</td>
      <td className="text-right space-x-1">
        {isFinished && (
          <Button size="sm" variant="ghost" onClick={onRerun} title="用相同配置再跑一次">
            重跑
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onPick}>
          查看日志
        </Button>
      </td>
    </tr>
  )
}

interface LogEntry {
  ts: string
  stream: string
  level: "INFO" | "ERROR"
  line: string
  /** Synthetic event marker — task_done / task_killed terminator. */
  marker?: string
}

const streamToLevel = (stream: string | undefined): "INFO" | "ERROR" =>
  stream === "stderr" ? "ERROR" : "INFO"

function matchesFilter(entry: LogEntry, filter: FilterState): boolean {
  if (entry.marker) return true // always show terminator markers
  if (filter.level !== "ALL" && entry.level !== filter.level) return false
  if (filter.keyword) {
    const kw = filter.keyword.toLowerCase()
    if (!entry.line.toLowerCase().includes(kw)) return false
  }
  return true
}

function LiveLog({ runId }: { runId: string }) {
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [filter, setFilter] = useState<FilterState>({
    level: "ALL",
    keyword: "",
    autoScroll: true,
  })
  const [historyLoading, setHistoryLoading] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  // Load historical first
  useEffect(() => {
    setEntries([])
    setHistoryLoading(true)
    api
      .get<{ items: LogEntry[]; total: number }>(`/tasks/runs/${runId}/logs`, {
        params: { limit: 5000 },
      })
      .then((r) => setEntries(r.data.items))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }, [runId])

  // Reconnecting WS for live tail
  const proto = window.location.protocol === "https:" ? "wss" : "ws"
  const wsUrl = `${proto}://${window.location.host}/ws/runs/${runId}/logs`
  const wsStatus = useReconnectingWs(wsUrl, {
    onMessage: (data) => {
      try {
        const frame = JSON.parse(data)
        if (frame.event === "task_done") {
          setEntries((p) => [
            ...p,
            {
              ts: frame.ts ?? new Date().toISOString(),
              stream: "stdout",
              level: "INFO",
              line: `[done] exit=${frame.exit_code}`,
              marker: "done",
            },
          ])
        } else if (frame.event === "task_killed") {
          setEntries((p) => [
            ...p,
            {
              ts: frame.ts ?? new Date().toISOString(),
              stream: "stderr",
              level: "ERROR",
              line: `[killed] reason=${frame.reason ?? ""}`,
              marker: "killed",
            },
          ])
        } else if (frame.line !== undefined) {
          setEntries((p) => [
            ...p,
            {
              ts: frame.ts ?? new Date().toISOString(),
              stream: frame.stream ?? "stdout",
              level: streamToLevel(frame.stream),
              line: frame.line,
            },
          ])
        }
      } catch {
        // ignore non-JSON
      }
    },
  })

  const visible = entries.filter((e) => matchesFilter(e, filter))

  useEffect(() => {
    if (filter.autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [visible.length, filter.autoScroll])

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <Input
          placeholder="按关键词筛选"
          value={filter.keyword}
          onChange={(e) => setFilter({ ...filter, keyword: e.target.value })}
          className="max-w-xs"
        />
        <select
          className="p-2 rounded border bg-background text-sm"
          value={filter.level}
          onChange={(e) =>
            setFilter({ ...filter, level: e.target.value as LogLevel })
          }
        >
          <option value="ALL">全部</option>
          <option value="INFO">INFO</option>
          <option value="ERROR">ERROR</option>
        </select>
        <label className="flex items-center gap-1 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={filter.autoScroll}
            onChange={(e) =>
              setFilter({ ...filter, autoScroll: e.target.checked })
            }
          />
          自动滚动
        </label>
        <WsBadge status={wsStatus} />
        <span className="text-xs text-muted-foreground ml-auto">
          {historyLoading ? "加载历史…" : `${visible.length} / ${entries.length} 行`}
        </span>
      </div>
      <div
        ref={containerRef}
        className="h-[40vh] overflow-auto bg-zinc-950 text-zinc-100 font-mono text-xs p-3 rounded"
      >
        {visible.length === 0 ? (
          <div className="text-zinc-500">
            {historyLoading
              ? "加载中…"
              : entries.length === 0
              ? "等待日志…"
              : "当前筛选条件下无匹配行。"}
          </div>
        ) : (
          visible.map((e, i) => (
            <div
              key={i}
              className={`whitespace-pre-wrap break-all ${
                e.level === "ERROR" ? "text-rose-400" : ""
              }`}
            >
              <span className="text-zinc-500">
                {e.ts ? new Date(e.ts).toLocaleTimeString() : "--:--:--"}
              </span>{" "}
              <span className="text-zinc-400">[{e.stream}]</span> {e.line}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ---------- DAG visualization ----------

function DagCard({ taskId }: { taskId: string }) {
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: ["task-dag", taskId],
    queryFn: () => getTaskDag(taskId),
    refetchInterval: 30000,
  })
  if (q.isLoading) return null
  const dag = q.data
  if (!dag || dag.edges.length === 0) return null // no upstream/downstream → don't render

  const ROLE_COLOR: Record<string, string> = {
    self: "#3b82f6",       // 蓝
    upstream: "#22c55e",   // 绿
    downstream: "#a855f7", // 紫
  }

  const opt = {
    tooltip: {
      formatter: (p: any) => {
        if (p.dataType === "edge") {
          return `依赖条件: ${p.data.on_status}`
        }
        const role =
          p.data.role === "self" ? "当前任务" : p.data.role === "upstream" ? "上游" : "下游"
        return `${p.data.name}<br/>${role}<br/>${p.data.is_active ? "✓ 启用" : "⏸ 暂停"}`
      },
    },
    legend: {
      data: [
        { name: "当前", icon: "circle", itemStyle: { color: ROLE_COLOR.self } },
        { name: "上游", icon: "circle", itemStyle: { color: ROLE_COLOR.upstream } },
        { name: "下游", icon: "circle", itemStyle: { color: ROLE_COLOR.downstream } },
      ],
      bottom: 0,
    },
    series: [
      {
        type: "graph",
        layout: "force",
        symbolSize: 40,
        roam: true,
        force: { repulsion: 200, edgeLength: 100 },
        label: { show: true, position: "bottom", fontSize: 11 },
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: 8,
        lineStyle: { color: "#888", width: 1.5, opacity: 0.7 },
        emphasis: { focus: "adjacency" },
        data: dag.nodes.map((n) => ({
          id: n.id,
          name: n.name,
          role: n.role,
          is_active: n.is_active,
          itemStyle: { color: ROLE_COLOR[n.role] },
          symbolSize: n.role === "self" ? 50 : 36,
        })),
        links: dag.edges.map((e) => ({
          source: e.source,
          target: e.target,
          on_status: e.on_status,
        })),
      },
    ],
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">依赖拓扑（点击节点跳转）</CardTitle>
      </CardHeader>
      <CardContent className="p-2">
        <ReactECharts
          option={opt}
          style={{ height: 280 }}
          onEvents={{
            click: (params: any) => {
              if (params.dataType === "node" && params.data?.id && params.data.role !== "self") {
                navigate(`/tasks/${params.data.id}`)
              }
            },
          }}
        />
      </CardContent>
    </Card>
  )
}

function WsBadge({ status }: { status: WsStatus }) {
  const map: Record<WsStatus, { label: string; cls: string }> = {
    connecting: { label: "连接中", cls: "bg-zinc-200 text-zinc-700" },
    open: { label: "● 已连接", cls: "bg-emerald-100 text-emerald-700" },
    reconnecting: { label: "重连中…", cls: "bg-amber-100 text-amber-700" },
    closed: { label: "已断开", cls: "bg-zinc-200 text-zinc-600" },
  }
  const m = map[status]
  return <span className={`text-[10px] px-2 py-0.5 rounded ${m.cls}`}>{m.label}</span>
}
