import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  listTasks,
  listProjects,
  createTask,
  deleteTask,
  pauseTask,
  resumeTask,
  runTaskNow,
  listWorkerGroups,
  batchPauseTasks,
  batchResumeTasks,
  batchDeleteTasks,
  type TaskCreateBody,
  type TaskSummary,
} from "@/api/client"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { TruncatedTooltip } from "@/components/ui/tooltip"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export function TasksPage() {
  const qc = useQueryClient()
  const tasksQ = useQuery({
    queryKey: ["tasks"],
    queryFn: () => listTasks({ page_size: 100 }),
  })
  const [createOpen, setCreateOpen] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const deleteMut = useMutation({
    mutationFn: deleteTask,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  })
  const pauseMut = useMutation({
    mutationFn: pauseTask,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  })
  const resumeMut = useMutation({
    mutationFn: resumeTask,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  })
  const runMut = useMutation({
    mutationFn: runTaskNow,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  })

  const batchPause = useMutation({
    mutationFn: () => batchPauseTasks(Array.from(selected)),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["tasks"] })
      toast.success(`已暂停 ${d.affected}，跳过 ${d.skipped}`)
      setSelected(new Set())
    },
  })
  const batchResume = useMutation({
    mutationFn: () => batchResumeTasks(Array.from(selected)),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["tasks"] })
      toast.success(`已启用 ${d.affected}，跳过 ${d.skipped}`)
      setSelected(new Set())
    },
  })
  const batchDel = useMutation({
    mutationFn: () => batchDeleteTasks(Array.from(selected)),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["tasks"] })
      toast.success(`已删除 ${d.deleted}，跳过 ${d.skipped}`)
      setSelected(new Set())
    },
  })

  const allIds = tasksQ.data?.items.map((t) => t.id) ?? []
  const allSelected = allIds.length > 0 && allIds.every((id) => selected.has(id))

  const toggleAll = () => {
    if (allSelected) setSelected(new Set())
    else setSelected(new Set(allIds))
  }
  const toggleOne = (id: string) => {
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">任务列表</h1>
        <Button onClick={() => setCreateOpen(true)}>新建任务</Button>
      </div>

      {selected.size > 0 && (
        <Card>
          <CardContent className="p-3 flex items-center gap-2">
            <span className="text-sm">已选 {selected.size} 项</span>
            <Button size="sm" variant="outline" onClick={() => batchResume.mutate()}>
              批量启用
            </Button>
            <Button size="sm" variant="outline" onClick={() => batchPause.mutate()}>
              批量暂停
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-destructive"
              onClick={() => {
                if (confirm(`确认删除 ${selected.size} 个任务？`)) batchDel.mutate()
              }}
            >
              批量删除
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
              取消选择
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>所有任务</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-2 w-8">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                  />
                </th>
                <th>名称</th>
                <th>调度</th>
                <th>命令</th>
                <th>策略</th>
                <th>状态</th>
                <th className="text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {tasksQ.data?.items.map((t) => (
                <TaskRow
                  key={t.id}
                  t={t}
                  checked={selected.has(t.id)}
                  onToggle={() => toggleOne(t.id)}
                  onPauseToggle={() =>
                    t.is_active ? pauseMut.mutate(t.id) : resumeMut.mutate(t.id)
                  }
                  onRun={() => runMut.mutate(t.id)}
                  onDelete={() => {
                    if (confirm(`删除任务 ${t.name}?`)) deleteMut.mutate(t.id)
                  }}
                />
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <CreateTaskDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => qc.invalidateQueries({ queryKey: ["tasks"] })}
      />
    </div>
  )
}

function describeSchedule(t: TaskSummary): string {
  const cfg = t.schedule_config ?? {}
  switch (t.schedule_type) {
    case "cron":
      return `cron: ${(cfg as any).cron ?? "?"}`
    case "interval":
      return `每 ${(cfg as any).interval_seconds ?? "?"}s`
    case "once":
      return `一次: ${(cfg as any).run_at ?? "?"}`
    case "immediate":
      return "立即（手动）"
    default:
      return t.schedule_type
  }
}

function TaskRow({
  t,
  checked,
  onToggle,
  onPauseToggle,
  onRun,
  onDelete,
}: {
  t: TaskSummary
  checked: boolean
  onToggle: () => void
  onPauseToggle: () => void
  onRun: () => void
  onDelete: () => void
}) {
  return (
    <tr className="border-t">
      <td className="py-2 w-8">
        <input type="checkbox" checked={checked} onChange={onToggle} />
      </td>
      <td className="py-2 font-medium">
        <Link to={`/tasks/${t.id}`} className="text-primary hover:underline">
          {t.name}
        </Link>
      </td>
      <td className="text-xs">{describeSchedule(t)}</td>
      <td className="font-mono text-xs max-w-[18rem] truncate">
        <TruncatedTooltip full={t.command} className="truncate max-w-full">
          {t.command}
        </TruncatedTooltip>
      </td>
      <td className="text-xs">{t.node_strategy}</td>
      <td>
        {t.is_active ? (
          <span className="text-green-600">活跃中</span>
        ) : (
          <span className="text-muted-foreground">已暂停</span>
        )}
      </td>
      <td className="text-right space-x-1">
        <Button size="sm" variant="ghost" onClick={onRun}>
          立即运行
        </Button>
        <Button size="sm" variant="ghost" onClick={onPauseToggle}>
          {t.is_active ? "暂停" : "启用"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="text-destructive"
          onClick={onDelete}
        >
          删除
        </Button>
      </td>
    </tr>
  )
}

interface FormState {
  name: string
  description: string
  project_id: string
  command: string
  schedule_type: "immediate" | "interval" | "once" | "cron"
  cron_expr: string
  interval_seconds: string
  run_at: string
  node_strategy: "auto" | "master" | "specific" | "platform" | "group" | "mixed"
  specific_node_id: string
  platform_target: string
  group_id: string
  max_concurrent: string
  concurrent_policy: "skip" | "queue"
  max_retries: string
  timeout_sec: string
  tags: string
}

function CreateTaskDialog(props: {
  open: boolean
  onOpenChange: (o: boolean) => void
  onCreated: () => void
}) {
  const projectsQ = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects({ page_size: 100 }),
    enabled: props.open,
  })
  const groupsQ = useQuery({
    queryKey: ["worker-groups"],
    queryFn: listWorkerGroups,
    enabled: props.open,
  })
  const [form, setForm] = useState<FormState>({
    name: "",
    description: "",
    project_id: "",
    command: "",
    schedule_type: "cron",
    cron_expr: "0 * * * *",
    interval_seconds: "60",
    run_at: "",
    node_strategy: "auto",
    specific_node_id: "",
    platform_target: "linux",
    group_id: "",
    max_concurrent: "1",
    concurrent_policy: "skip",
    max_retries: "0",
    timeout_sec: "3600",
    tags: "",
  })
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState("")

  const handleSubmit = async () => {
    setErr("")
    setSubmitting(true)
    try {
      const body: TaskCreateBody = {
        name: form.name,
        description: form.description || null,
        project_id: form.project_id,
        command: form.command,
        schedule_type: form.schedule_type,
        node_strategy: form.node_strategy,
        max_concurrent: parseInt(form.max_concurrent || "1", 10),
        concurrent_policy: form.concurrent_policy,
        max_retries: parseInt(form.max_retries || "0", 10),
        timeout_sec: parseInt(form.timeout_sec || "3600", 10),
        tags: form.tags
          ? form.tags
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
      }
      if (form.schedule_type === "cron") body.schedule_config = { cron: form.cron_expr }
      else if (form.schedule_type === "interval")
        body.schedule_config = { interval_seconds: parseInt(form.interval_seconds, 10) }
      else if (form.schedule_type === "once")
        body.schedule_config = { run_at: form.run_at }
      else body.schedule_config = {}

      if (form.node_strategy === "specific")
        body.node_target = { node_id: form.specific_node_id }
      else if (form.node_strategy === "platform")
        body.node_target = { platform: form.platform_target }
      else if (form.node_strategy === "group" || form.node_strategy === "mixed") {
        if (form.group_id) body.node_target = { group_id: form.group_id }
      }

      await createTask(body)
      props.onCreated()
      props.onOpenChange(false)
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e.message || String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>新建任务</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
          <Input
            placeholder="任务名"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Input
            placeholder="描述"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <select
            className="w-full p-2 rounded border bg-background"
            value={form.project_id}
            onChange={(e) => setForm({ ...form, project_id: e.target.value })}
          >
            <option value="">— 选择项目 —</option>
            {projectsQ.data?.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <Input
            placeholder="执行命令（如 python main.py）"
            value={form.command}
            onChange={(e) => setForm({ ...form, command: e.target.value })}
          />

          <div>
            <div className="text-sm mb-1">调度方式</div>
            <div className="grid grid-cols-4 gap-1">
              {(["immediate", "interval", "once", "cron"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`py-1.5 text-xs rounded border ${
                    form.schedule_type === t ? "bg-primary text-primary-foreground" : "bg-muted"
                  }`}
                  onClick={() => setForm({ ...form, schedule_type: t })}
                >
                  {t}
                </button>
              ))}
            </div>
            <div className="mt-2">
              {form.schedule_type === "cron" && (
                <>
                  <Input
                    placeholder="Cron 表达式（如 0 * * * *）"
                    value={form.cron_expr}
                    onChange={(e) => setForm({ ...form, cron_expr: e.target.value })}
                  />
                  <CronPreview expr={form.cron_expr} />
                </>
              )}
              {form.schedule_type === "interval" && (
                <Input
                  placeholder="间隔（秒）"
                  value={form.interval_seconds}
                  onChange={(e) =>
                    setForm({ ...form, interval_seconds: e.target.value })
                  }
                />
              )}
              {form.schedule_type === "once" && (
                <Input
                  placeholder="ISO 时间（如 2026-05-20T10:00:00）"
                  value={form.run_at}
                  onChange={(e) => setForm({ ...form, run_at: e.target.value })}
                />
              )}
            </div>
          </div>

          <div>
            <div className="text-sm mb-1">节点策略</div>
            <div className="grid grid-cols-3 gap-1">
              {(
                ["auto", "master", "specific", "platform", "group", "mixed"] as const
              ).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`py-1.5 text-xs rounded border ${
                    form.node_strategy === s ? "bg-primary text-primary-foreground" : "bg-muted"
                  }`}
                  onClick={() => setForm({ ...form, node_strategy: s })}
                >
                  {s}
                </button>
              ))}
            </div>
            {form.node_strategy === "specific" && (
              <Input
                className="mt-2"
                placeholder="node_id"
                value={form.specific_node_id}
                onChange={(e) =>
                  setForm({ ...form, specific_node_id: e.target.value })
                }
              />
            )}
            {form.node_strategy === "platform" && (
              <select
                className="w-full p-2 rounded border bg-background mt-2"
                value={form.platform_target}
                onChange={(e) =>
                  setForm({ ...form, platform_target: e.target.value })
                }
              >
                <option value="linux">linux</option>
                <option value="darwin">darwin</option>
                <option value="win32">windows</option>
              </select>
            )}
            {(form.node_strategy === "group" || form.node_strategy === "mixed") && (
              <select
                className="w-full p-2 rounded border bg-background mt-2"
                value={form.group_id}
                onChange={(e) => setForm({ ...form, group_id: e.target.value })}
              >
                <option value="">— 选择节点组 —</option>
                {groupsQ.data?.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name} ({g.worker_count})
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="grid grid-cols-3 gap-2">
            <Input
              placeholder="并发上限"
              value={form.max_concurrent}
              onChange={(e) =>
                setForm({ ...form, max_concurrent: e.target.value })
              }
            />
            <Input
              placeholder="重试次数"
              value={form.max_retries}
              onChange={(e) => setForm({ ...form, max_retries: e.target.value })}
            />
            <Input
              placeholder="超时秒"
              value={form.timeout_sec}
              onChange={(e) => setForm({ ...form, timeout_sec: e.target.value })}
            />
          </div>
          <div>
            <div className="text-sm mb-1">并发策略</div>
            <div className="grid grid-cols-2 gap-1">
              {(["skip", "queue"] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`py-1.5 text-xs rounded border ${
                    form.concurrent_policy === p ? "bg-primary text-primary-foreground" : "bg-muted"
                  }`}
                  onClick={() => setForm({ ...form, concurrent_policy: p })}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          <Input
            placeholder="标签（逗号分隔）"
            value={form.tags}
            onChange={(e) => setForm({ ...form, tags: e.target.value })}
          />
          {err && <p className="text-sm text-destructive">{err}</p>}
        </div>
        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "创建中..." : "创建"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

import cronstrue from "cronstrue/i18n"
import { CronExpressionParser } from "cron-parser"

function CronPreview({ expr }: { expr: string }) {
  if (!expr || expr.trim().length === 0) {
    return <div className="mt-1 text-xs text-muted-foreground">输入 cron 表达式以查看预览</div>
  }
  let human = ""
  let next: Date[] = []
  let err = ""
  try {
    human = cronstrue.toString(expr, { locale: "zh_CN" })
  } catch (e: any) {
    err = e?.message || "无法解析"
  }
  if (!err) {
    try {
      const it = CronExpressionParser.parse(expr)
      for (let i = 0; i < 5; i++) next.push(it.next().toDate())
    } catch (e: any) {
      err = e?.message || "时间无法计算"
    }
  }
  if (err) {
    return <div className="mt-1 text-xs text-destructive">⚠ {err}</div>
  }
  return (
    <div className="mt-1 space-y-0.5">
      <div className="text-xs text-emerald-600">✓ {human}</div>
      <div className="text-xs text-muted-foreground">
        接下来 5 次：
        <ul className="font-mono ml-3">
          {next.map((d, i) => (
            <li key={i}>{d.toLocaleString()}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}
