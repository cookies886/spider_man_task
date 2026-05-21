import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import ReactECharts from "echarts-for-react"
import { Link } from "react-router-dom"
import {
  fetchOverview,
  fetchPerf,
  fetchTasksDash,
  fetchWorkersDash,
  fetchCharts,
  fetchGantt,
  type DashWorkerItem,
  type Granularity,
} from "@/api/client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  FolderGit2,
  ListTodo,
  Server,
  Box,
  Activity,
  CheckCircle2,
  PauseCircle,
  Clock,
  Cpu,
  HardDrive,
  Wifi,
  type LucideIcon,
} from "lucide-react"

type Range = "1h" | "6h" | "24h" | "7d" | "30d"
type Tab = "overview" | "perf" | "tasks" | "workers" | "charts" | "gantt"

// ---------- helpers ----------

const STATUS_COLOR: Record<string, string> = {
  success: "#22c55e",
  failed: "#ef4444",
  timeout: "#f59e0b",
  killed: "#a855f7",
  running: "#3b82f6",
  pending: "#9ca3af",
  dispatching: "#3b82f6",
  skipped: "#d1d5db",
}

function formatUptime(seconds: number): string {
  if (seconds <= 0) return "-"
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m ${seconds % 60}s`
}

function formatBps(bps: number): string {
  if (bps < 1024) return `${bps} B/s`
  if (bps < 1024 * 1024) return `${(bps / 1024).toFixed(1)} KB/s`
  return `${(bps / 1024 / 1024).toFixed(1)} MB/s`
}

function formatRelTime(iso: string | null): string {
  if (!iso) return "从未"
  const t = new Date(iso).getTime()
  const sec = Math.max(0, (Date.now() - t) / 1000)
  if (sec < 60) return `${Math.floor(sec)}秒前`
  if (sec < 3600) return `${Math.floor(sec / 60)}分钟前`
  if (sec < 86400) return `${Math.floor(sec / 3600)}小时前`
  return `${Math.floor(sec / 86400)}天前`
}

// ---------- top-level ----------

export function DashboardPage() {
  const [tab, setTab] = useState<Tab>("overview")
  const tabs: { key: Tab; label: string }[] = [
    { key: "overview", label: "概览" },
    { key: "perf", label: "性能指标" },
    { key: "tasks", label: "任务统计" },
    { key: "workers", label: "工作节点" },
    { key: "charts", label: "指标图表" },
    { key: "gantt", label: "甘特图" },
  ]
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-semibold">仪表盘</h1>
        <div className="flex gap-1 flex-wrap">
          {tabs.map((t) => (
            <Button
              key={t.key}
              variant={tab === t.key ? "default" : "ghost"}
              size="sm"
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </Button>
          ))}
        </div>
      </div>
      {tab === "overview" && <OverviewTab />}
      {tab === "perf" && <PerfTab />}
      {tab === "tasks" && <TasksTab />}
      {tab === "workers" && <WorkersTab />}
      {tab === "charts" && <ChartsTab />}
      {tab === "gantt" && <GanttTab />}
    </div>
  )
}

// ---------- shared widgets ----------

function StatCard(props: {
  title: string
  value: string | number
  icon?: LucideIcon
  hint?: string
  color?: string
}) {
  const Icon = props.icon
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">{props.title}</span>
          {Icon && <Icon className={`h-4 w-4 ${props.color ?? "text-muted-foreground"}`} />}
        </div>
        <div className="text-2xl font-semibold mt-2">{props.value}</div>
        {props.hint && (
          <div className="text-xs text-muted-foreground mt-1">{props.hint}</div>
        )}
      </CardContent>
    </Card>
  )
}

function RangePicker(props: { value: Range; onChange: (r: Range) => void }) {
  const opts: Range[] = ["1h", "6h", "24h", "7d", "30d"]
  return (
    <div className="flex gap-1">
      {opts.map((r) => (
        <button
          key={r}
          className={`px-2 py-1 text-xs rounded border ${
            props.value === r ? "bg-primary text-primary-foreground" : "bg-muted"
          }`}
          onClick={() => props.onChange(r)}
        >
          {r}
        </button>
      ))}
    </div>
  )
}

function GranularityPicker(props: {
  value: Granularity
  onChange: (g: Granularity) => void
}) {
  const opts: { v: Granularity; label: string }[] = [
    { v: "hour", label: "小时" },
    { v: "day", label: "天" },
    { v: "month", label: "月" },
  ]
  return (
    <div className="flex gap-1">
      {opts.map((o) => (
        <button
          key={o.v}
          className={`px-2 py-1 text-xs rounded border ${
            props.value === o.v ? "bg-primary text-primary-foreground" : "bg-muted"
          }`}
          onClick={() => props.onChange(o.v)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function ServiceBadge({ name, status }: { name: string; status: string }) {
  const cls =
    status === "healthy"
      ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
      : "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${cls}`}>
      {name}: {status}
    </span>
  )
}

// ---------- overview tab ----------

function OverviewTab() {
  const q = useQuery({
    queryKey: ["dash-overview"],
    queryFn: fetchOverview,
    refetchInterval: 10000,
  })
  const d = q.data
  const clusterColor =
    d?.cluster_health === "healthy"
      ? "text-green-600"
      : d?.cluster_health === "degraded"
      ? "text-amber-600"
      : "text-destructive"

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="总项目数" value={d?.total_projects ?? 0} icon={FolderGit2} color="text-blue-600" />
        <StatCard title="总任务数" value={d?.total_tasks ?? 0} icon={ListTodo} color="text-emerald-600" />
        <StatCard title="活跃任务" value={d?.active_tasks ?? 0} icon={Activity} color="text-cyan-600" />
        <StatCard title="虚拟环境数" value={d?.total_envs ?? 0} icon={Box} color="text-violet-600" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          title="在线节点"
          value={`${d?.online_workers ?? 0}/${d?.total_workers ?? 0}`}
          icon={Server}
          color={clusterColor}
          hint={d?.cluster_health}
        />
        <StatCard
          title="系统运行时长"
          value={formatUptime(d?.uptime_seconds ?? 0)}
          icon={Clock}
          color="text-blue-600"
        />
        <StatCard
          title="集群健康度"
          value={d?.cluster_health === "healthy" ? "✓ 健康" : d?.cluster_health === "degraded" ? "△ 降级" : "✗ 故障"}
          icon={Activity}
          color={clusterColor}
        />
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground mb-2">服务可用性</div>
            <div className="flex flex-col gap-1">
              <ServiceBadge name="master" status={d?.services?.master ?? "?"} />
              <ServiceBadge name="postgres" status={d?.services?.postgres ?? "?"} />
              <ServiceBadge name="redis" status={d?.services?.redis ?? "?"} />
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="今日总执行" value={d?.today_total ?? 0} icon={ListTodo} />
        <StatCard
          title="今日成功率"
          value={d ? `${(d.success_rate * 100).toFixed(1)}%` : "-"}
          icon={CheckCircle2}
          color="text-green-600"
        />
        <StatCard title="当前运行中" value={d?.running_runs ?? 0} icon={Activity} color="text-orange-500" />
        <StatCard title="已暂停任务" value={d?.paused_tasks ?? 0} icon={PauseCircle} color="text-muted-foreground" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">最近失败 / 超时 / 终止</CardTitle>
        </CardHeader>
        <CardContent>
          {(d?.recent_failures ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">最近没有异常运行 ✓</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-muted-foreground">
                <tr>
                  <th className="py-2">任务</th>
                  <th>状态</th>
                  <th>结束时间</th>
                  <th>错误</th>
                </tr>
              </thead>
              <tbody>
                {d!.recent_failures.map((r) => (
                  <tr key={r.run_id} className="border-t">
                    <td className="py-2">
                      <Link className="hover:underline" to={`/tasks/${r.task_id}`}>
                        {r.task_name}
                      </Link>
                    </td>
                    <td>
                      <span style={{ color: STATUS_COLOR[r.status] ?? "#888" }}>{r.status}</span>
                    </td>
                    <td className="text-muted-foreground text-xs">
                      {r.finished_at ? new Date(r.finished_at).toLocaleString() : "-"}
                    </td>
                    <td className="text-xs text-muted-foreground truncate max-w-[24rem]">
                      {r.error_msg ?? "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ---------- perf tab ----------

function PerfTab() {
  const [range, setRange] = useState<Range>("1h")
  const q = useQuery({
    queryKey: ["dash-perf", range],
    queryFn: () => fetchPerf(range),
    refetchInterval: 10000,
  })
  const d = q.data
  const series = d?.series ?? []
  const xs = series.map((s) => new Date(s.ts).toLocaleTimeString())
  const lineOpt = {
    tooltip: { trigger: "axis" },
    legend: { data: ["CPU", "内存", "磁盘"] },
    grid: { left: 40, right: 16, top: 30, bottom: 30 },
    xAxis: { type: "category", data: xs, axisLabel: { fontSize: 10 } },
    yAxis: { type: "value", max: 100 },
    series: [
      { name: "CPU", type: "line", smooth: true, data: series.map((s) => s.cpu) },
      { name: "内存", type: "line", smooth: true, data: series.map((s) => s.mem) },
      { name: "磁盘", type: "line", smooth: true, data: series.map((s) => s.disk) },
    ],
  }
  const netOpt = {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: number) => formatBps(Number(v)),
    },
    legend: { data: ["入站", "出站"] },
    grid: { left: 60, right: 16, top: 30, bottom: 30 },
    xAxis: { type: "category", data: xs, axisLabel: { fontSize: 10 } },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => formatBps(v) } },
    series: [
      {
        name: "入站",
        type: "line",
        smooth: true,
        areaStyle: {},
        data: series.map((s) => s.net_in),
      },
      {
        name: "出站",
        type: "line",
        smooth: true,
        areaStyle: {},
        data: series.map((s) => s.net_out),
      },
    ],
  }

  const latest = series[series.length - 1]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">资源使用率（%）</span>
        <RangePicker value={range} onChange={setRange} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          title="CPU"
          value={latest ? `${latest.cpu.toFixed(1)}%` : "-"}
          icon={Cpu}
          color="text-blue-600"
          hint={d?.stats ? `峰值 ${d.stats.cpu.peak}% · 均值 ${d.stats.cpu.avg}%` : undefined}
        />
        <StatCard
          title="内存"
          value={latest ? `${latest.mem.toFixed(1)}%` : "-"}
          icon={Activity}
          color="text-emerald-600"
          hint={d?.stats ? `峰值 ${d.stats.mem.peak}% · 均值 ${d.stats.mem.avg}%` : undefined}
        />
        <StatCard
          title="磁盘"
          value={latest ? `${latest.disk.toFixed(1)}%` : "-"}
          icon={HardDrive}
          color="text-amber-600"
          hint={d?.stats ? `峰值 ${d.stats.disk.peak}% · 均值 ${d.stats.disk.avg}%` : undefined}
        />
        <StatCard
          title="网络"
          value={latest ? formatBps(latest.net_in + latest.net_out) : "-"}
          icon={Wifi}
          color="text-cyan-600"
          hint={d?.stats ? `峰值 in ${formatBps(d.stats.net_in.peak)}` : undefined}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">CPU / 内存 / 磁盘 时序</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          <ReactECharts option={lineOpt} style={{ height: 300 }} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">网络流量</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          <ReactECharts option={netOpt} style={{ height: 250 }} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">峰值 / 均值 / 异常</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            <table className="w-full text-sm">
              <thead className="text-left text-muted-foreground">
                <tr>
                  <th className="py-2 pl-2">指标</th>
                  <th>峰值</th>
                  <th>均值</th>
                  <th>异常</th>
                </tr>
              </thead>
              <tbody>
                {(["cpu", "mem", "disk"] as const).map((k) => {
                  const s = d?.stats?.[k]
                  return (
                    <tr key={k} className="border-t">
                      <td className="py-2 pl-2 capitalize">{k}</td>
                      <td>{s?.peak ?? "-"}%</td>
                      <td>{s?.avg ?? "-"}%</td>
                      <td>{s?.anomaly_count ?? "-"}</td>
                    </tr>
                  )
                })}
                {(["net_in", "net_out"] as const).map((k) => {
                  const s = d?.stats?.[k]
                  return (
                    <tr key={k} className="border-t">
                      <td className="py-2 pl-2">{k === "net_in" ? "网络入" : "网络出"}</td>
                      <td>{s ? formatBps(s.peak) : "-"}</td>
                      <td>{s ? formatBps(s.avg) : "-"}</td>
                      <td>{s?.anomaly_count ?? "-"}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">节点资源排行</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            {(d?.per_node ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground p-3">暂无数据</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th className="py-2 pl-2">节点</th>
                    <th>CPU</th>
                    <th>内存</th>
                    <th>磁盘</th>
                  </tr>
                </thead>
                <tbody>
                  {d!.per_node.map((p) => (
                    <tr key={p.node_id} className="border-t">
                      <td className="py-2 pl-2 font-mono text-xs">{p.name}</td>
                      <td>{p.cpu.toFixed(1)}%</td>
                      <td>{p.mem.toFixed(1)}%</td>
                      <td>{p.disk.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ---------- tasks tab ----------

function TasksTab() {
  const [range, setRange] = useState<Range>("24h")
  const [granularity, setGranularity] = useState<Granularity>("hour")
  const q = useQuery({
    queryKey: ["dash-tasks", range, granularity],
    queryFn: () => fetchTasksDash(range, granularity),
    refetchInterval: 15000,
  })
  const sum = q.data?.summary
  const trend = q.data?.trend ?? []
  const dist = q.data?.hour_distribution ?? []
  const cal = q.data?.calendar ?? []
  const hist = q.data?.duration_histogram ?? []
  const nodeDist = q.data?.node_distribution ?? []
  const projRank = q.data?.project_ranking ?? []

  const trendOpt = {
    tooltip: { trigger: "axis" },
    legend: { data: ["总数", "成功"] },
    grid: { left: 40, right: 16, top: 30, bottom: 30 },
    xAxis: {
      type: "category",
      data: trend.map((t) => (t.bucket ? new Date(t.bucket).toLocaleString() : "-")),
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: "value" },
    series: [
      { name: "总数", type: "line", areaStyle: {}, data: trend.map((t) => t.total) },
      { name: "成功", type: "line", areaStyle: {}, data: trend.map((t) => t.success) },
    ],
  }
  const pieOpt = {
    tooltip: { trigger: "item" },
    legend: { orient: "vertical", left: "left", textStyle: { fontSize: 10 } },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        data: sum
          ? [
              { name: "成功", value: sum.success, itemStyle: { color: STATUS_COLOR.success } },
              { name: "失败", value: sum.failed, itemStyle: { color: STATUS_COLOR.failed } },
              { name: "超时", value: sum.timeout, itemStyle: { color: STATUS_COLOR.timeout } },
              { name: "终止", value: sum.killed, itemStyle: { color: STATUS_COLOR.killed } },
              { name: "跳过", value: sum.skipped, itemStyle: { color: STATUS_COLOR.skipped } },
              { name: "运行", value: sum.running, itemStyle: { color: STATUS_COLOR.running } },
            ]
          : [],
      },
    ],
  }
  const distOpt = {
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 16, top: 20, bottom: 30 },
    xAxis: { type: "category", data: dist.map((d) => `${d.hour}h`) },
    yAxis: { type: "value" },
    series: [{ type: "bar", data: dist.map((d) => d.count) }],
  }
  const histOpt = {
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 16, top: 20, bottom: 40 },
    xAxis: {
      type: "category",
      data: hist.map((h) => h.bucket),
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: "value" },
    series: [
      {
        type: "bar",
        data: hist.map((h) => h.count),
        itemStyle: { color: "#3b82f6" },
      },
    ],
  }

  // Calendar heatmap (60d)
  const calMap = Object.fromEntries(cal.map((c) => [c.date, c.count]))
  const today = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 60)
  const calData: [string, number][] = []
  for (let dd = new Date(start); dd <= today; dd.setDate(dd.getDate() + 1)) {
    const ds = dd.toISOString().slice(0, 10)
    calData.push([ds, calMap[ds] ?? 0])
  }
  const calOpt = {
    tooltip: {},
    visualMap: {
      min: 0,
      max: Math.max(...calData.map((c) => c[1]), 1),
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      inRange: { color: ["#e5e7eb", "#22c55e"] },
    },
    calendar: {
      range: [start.toISOString().slice(0, 10), today.toISOString().slice(0, 10)],
      cellSize: ["auto", 14],
      yearLabel: { show: false },
    },
    series: [{ type: "heatmap", coordinateSystem: "calendar", data: calData }],
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <span className="text-sm text-muted-foreground">任务执行统计</span>
        <div className="flex gap-3">
          <GranularityPicker value={granularity} onChange={setGranularity} />
          <RangePicker value={range} onChange={setRange} />
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard title="总执行" value={sum?.total ?? 0} />
        <StatCard title="成功" value={sum?.success ?? 0} color="text-green-600" />
        <StatCard title="失败" value={sum?.failed ?? 0} color="text-destructive" />
        <StatCard
          title="成功率"
          value={sum ? `${(sum.success_rate * 100).toFixed(1)}%` : "-"}
          color="text-green-600"
        />
        <StatCard
          title="平均耗时"
          value={sum ? `${sum.avg_duration_sec.toFixed(1)}s` : "-"}
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="运行中" value={sum?.running ?? 0} icon={Activity} color="text-orange-500" />
        <StatCard title="等待执行" value={sum?.pending ?? 0} icon={Clock} color="text-muted-foreground" />
        <StatCard title="调度中" value={sum?.dispatching ?? 0} icon={Activity} color="text-blue-600" />
        <StatCard title="已暂停" value={sum?.paused_tasks ?? 0} icon={PauseCircle} color="text-muted-foreground" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              执行趋势（{granularity === "hour" ? "小时" : granularity === "day" ? "天" : "月"}）
            </CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            <ReactECharts option={trendOpt} style={{ height: 280 }} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">状态分布</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            <ReactECharts option={pieOpt} style={{ height: 280 }} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">执行时长分布</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            <ReactECharts option={histOpt} style={{ height: 220 }} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">24 小时分布（近 7 天累计）</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            <ReactECharts option={distOpt} style={{ height: 220 }} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">日历热力图（近 60 天）</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          <ReactECharts option={calOpt} style={{ height: 220 }} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">节点执行分布</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            {nodeDist.length === 0 ? (
              <p className="text-sm text-muted-foreground p-3">暂无数据</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th className="py-2 pl-2">节点</th>
                    <th>执行</th>
                    <th>成功</th>
                    <th>成功率</th>
                  </tr>
                </thead>
                <tbody>
                  {nodeDist.map((n) => (
                    <tr key={n.node_id} className="border-t">
                      <td className="py-2 pl-2 font-mono text-xs">{n.name}</td>
                      <td>{n.total}</td>
                      <td>{n.success}</td>
                      <td>{(n.success_rate * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">项目执行排行 TOP 10</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            {projRank.length === 0 ? (
              <p className="text-sm text-muted-foreground p-3">暂无数据</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th className="py-2 pl-2">项目</th>
                    <th>执行</th>
                    <th>成功</th>
                    <th>成功率</th>
                  </tr>
                </thead>
                <tbody>
                  {projRank.map((p) => (
                    <tr key={p.project_id} className="border-t">
                      <td className="py-2 pl-2">
                        <Link className="hover:underline" to={`/projects/${p.project_id}`}>
                          {p.name}
                        </Link>
                      </td>
                      <td>{p.total}</td>
                      <td>{p.success}</td>
                      <td>{(p.success_rate * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ---------- workers tab ----------

function WorkersTab() {
  const q = useQuery({
    queryKey: ["dash-workers"],
    queryFn: fetchWorkersDash,
    refetchInterval: 10000,
  })
  return (
    <div className="space-y-3">
      <div className="text-sm text-muted-foreground">
        节点详情（按状态排序，每 10 秒刷新）
      </div>
      {q.isLoading && <p className="text-muted-foreground">加载中...</p>}
      {q.data?.items.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground text-sm">
            暂无 Worker 节点
          </CardContent>
        </Card>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {q.data?.items.map((w) => (
          <WorkerCard key={w.id} w={w} />
        ))}
      </div>
    </div>
  )
}

function WorkerCard({ w }: { w: DashWorkerItem }) {
  const statusColor =
    w.status === "online"
      ? "success"
      : w.status === "busy"
      ? "warning"
      : "destructive"
  const connColor: Record<string, string> = {
    excellent: "text-green-600",
    good: "text-emerald-600",
    poor: "text-amber-600",
    lost: "text-destructive",
    never: "text-muted-foreground",
  }
  const xs = w.history.map((h) => new Date(h.ts).toLocaleTimeString())
  const miniOpt = {
    tooltip: { trigger: "axis", textStyle: { fontSize: 10 } },
    grid: { left: 30, right: 10, top: 5, bottom: 20 },
    xAxis: { type: "category", data: xs, axisLabel: { show: false } },
    yAxis: { type: "value", max: 100, axisLabel: { fontSize: 9 } },
    series: [
      { name: "CPU", type: "line", smooth: true, data: w.history.map((h) => h.cpu), showSymbol: false },
      { name: "内存", type: "line", smooth: true, data: w.history.map((h) => h.mem), showSymbol: false },
    ],
  }
  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="font-semibold">{w.name}</div>
          <div className="flex gap-1">
            <Badge variant={statusColor as any}>{w.status}</Badge>
            <Badge variant="outline">{w.type}</Badge>
            {w.group_name && <Badge variant="secondary">{w.group_name}</Badge>}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <div className="text-muted-foreground">主机</div>
          <div className="font-mono">{w.hostname} · {w.ip}:{w.port}</div>
          <div className="text-muted-foreground">系统</div>
          <div>{w.os ?? "-"} {w.arch ?? ""}</div>
          <div className="text-muted-foreground">Python</div>
          <div>{w.python_version ?? "-"}</div>
          <div className="text-muted-foreground">运行时长</div>
          <div>{formatUptime(w.uptime_seconds)}</div>
          <div className="text-muted-foreground">最后心跳</div>
          <div>{formatRelTime(w.last_heartbeat)}</div>
          <div className="text-muted-foreground">连接质量</div>
          <div className={connColor[w.connection_quality]}>{w.connection_quality}</div>
        </div>

        <div className="grid grid-cols-3 gap-2 text-xs">
          <ResourceBar label="CPU" pct={w.cpu_usage} />
          <ResourceBar label="内存" pct={w.mem_usage} />
          <ResourceBar
            label="任务"
            pct={(w.current_tasks / Math.max(1, w.max_slots)) * 100}
            display={`${w.current_tasks}/${w.max_slots}`}
          />
        </div>

        {w.history.length > 0 && (
          <div className="border-t pt-2">
            <div className="text-xs text-muted-foreground mb-1">最近 1 小时 CPU/内存</div>
            <ReactECharts option={miniOpt} style={{ height: 90 }} />
          </div>
        )}

        <div className="border-t pt-2 grid grid-cols-3 gap-2 text-xs text-center">
          <div>
            <div className="text-muted-foreground">24h 执行</div>
            <div className="font-semibold">{w.task_summary.total}</div>
          </div>
          <div>
            <div className="text-muted-foreground">成功</div>
            <div className="font-semibold text-green-600">{w.task_summary.success}</div>
          </div>
          <div>
            <div className="text-muted-foreground">成功率</div>
            <div className="font-semibold">
              {w.task_summary.total ? `${(w.task_summary.success_rate * 100).toFixed(0)}%` : "-"}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function ResourceBar({ label, pct, display }: { label: string; pct: number; display?: string }) {
  const v = Math.min(100, Math.max(0, pct))
  const color = v >= 80 ? "bg-destructive" : v >= 60 ? "bg-amber-500" : "bg-emerald-500"
  return (
    <div>
      <div className="flex justify-between mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span>{display ?? `${v.toFixed(0)}%`}</span>
      </div>
      <div className="h-1.5 bg-muted rounded">
        <div className={`h-1.5 rounded ${color}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  )
}

// ---------- charts tab ----------

function ChartsTab() {
  const [range, setRange] = useState<Range>("24h")
  const [granularity, setGranularity] = useState<Granularity>("hour")
  const q = useQuery({
    queryKey: ["dash-charts", range, granularity],
    queryFn: () => fetchCharts(range, granularity),
    refetchInterval: 15000,
  })
  const d = q.data
  const ev = d?.execution_volume ?? []

  const volOpt = {
    tooltip: { trigger: "axis" },
    legend: { data: ["执行量", "成功率"] },
    grid: { left: 40, right: 50, top: 30, bottom: 30 },
    xAxis: {
      type: "category",
      data: ev.map((e) => (e.bucket ? new Date(e.bucket).toLocaleString() : "-")),
      axisLabel: { fontSize: 10 },
    },
    yAxis: [
      { type: "value", name: "次数" },
      { type: "value", name: "%", min: 0, max: 100 },
    ],
    series: [
      { name: "执行量", type: "bar", data: ev.map((e) => e.total) },
      {
        name: "成功率",
        type: "line",
        yAxisIndex: 1,
        data: ev.map((e) => +(e.success_rate * 100).toFixed(1)),
        smooth: true,
        itemStyle: { color: "#22c55e" },
      },
    ],
  }
  const taskTypeOpt = {
    tooltip: { trigger: "item" },
    legend: { orient: "vertical", left: "left" },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        data: d?.task_type_distribution ?? [],
      },
    ],
  }
  const projectOpt = {
    tooltip: { trigger: "item" },
    legend: { orient: "vertical", left: "left", textStyle: { fontSize: 10 } },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        data: d?.project_load ?? [],
      },
    ],
  }
  const nodeBarOpt = {
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 16, top: 20, bottom: 60 },
    xAxis: {
      type: "category",
      data: (d?.node_load ?? []).map((n) => n.name),
      axisLabel: { fontSize: 10, rotate: 30 },
    },
    yAxis: { type: "value" },
    series: [
      {
        type: "bar",
        data: (d?.node_load ?? []).map((n) => n.value),
        itemStyle: { color: "#8b5cf6" },
      },
    ],
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <span className="text-sm text-muted-foreground">指标图表</span>
        <div className="flex gap-3">
          <GranularityPicker value={granularity} onChange={setGranularity} />
          <RangePicker value={range} onChange={setRange} />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">任务执行量 + 成功率</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          <ReactECharts option={volOpt} style={{ height: 320 }} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">任务类型分布</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            {(d?.task_type_distribution.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground p-3">暂无数据</p>
            ) : (
              <ReactECharts option={taskTypeOpt} style={{ height: 280 }} />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">项目负载分布</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            {(d?.project_load.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground p-3">暂无数据</p>
            ) : (
              <ReactECharts option={projectOpt} style={{ height: 280 }} />
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">节点负载</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          {(d?.node_load.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground p-3">暂无数据</p>
          ) : (
            <ReactECharts option={nodeBarOpt} style={{ height: 260 }} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ---------- gantt tab (kept) ----------

function GanttTab() {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const q = useQuery({
    queryKey: ["dash-gantt", date],
    queryFn: () => fetchGantt(date),
    refetchInterval: 15000,
  })
  const items = q.data?.items ?? []

  const data = items
    .filter((it) => it.started_at)
    .map((it) => {
      const start = new Date(it.started_at!).getTime()
      const end = it.finished_at ? new Date(it.finished_at).getTime() : Date.now()
      return {
        name: it.task_name,
        value: [it.task_name, start, end, it.status],
        itemStyle: { color: STATUS_COLOR[it.status] ?? "#888" },
      }
    })

  const tasks = Array.from(new Set(data.map((d) => d.name)))

  const opt = {
    tooltip: {
      formatter: (p: any) =>
        `${p.value[0]}<br/>${new Date(p.value[1]).toLocaleString()} - ${new Date(
          p.value[2]
        ).toLocaleString()}<br/>状态: ${p.value[3]}`,
    },
    grid: { left: 200, right: 20, top: 20, bottom: 40 },
    xAxis: { type: "time" },
    yAxis: { type: "category", data: tasks, axisLabel: { fontSize: 10 } },
    series: [
      {
        type: "custom",
        renderItem: (_params: any, api: any) => {
          const cat = api.value(0)
          const start = api.coord([api.value(1), cat])
          const end = api.coord([api.value(2), cat])
          const h = api.size([0, 1])[1] * 0.6
          return {
            type: "rect",
            shape: { x: start[0], y: start[1] - h / 2, width: Math.max(end[0] - start[0], 2), height: h },
            style: { fill: api.visual("color") },
          }
        },
        encode: { x: [1, 2], y: 0 },
        data,
      },
    ],
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="px-2 py-1 rounded border bg-background text-sm"
        />
        <span className="text-sm text-muted-foreground">{items.length} 个 run</span>
      </div>
      <Card>
        <CardContent className="p-2">
          {data.length === 0 ? (
            <p className="p-6 text-center text-muted-foreground text-sm">该日无任务执行记录</p>
          ) : (
            <ReactECharts option={opt} style={{ height: Math.max(220, 30 * tasks.length + 60) }} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
