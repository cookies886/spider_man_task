import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Command } from "cmdk"
import { toast } from "sonner"
import {
  listTasks,
  listProjects,
  listWorkers,
  listWorkerGroups,
  runTaskNow,
  pauseTask,
  resumeTask,
} from "@/api/client"
import {
  ListTodo,
  FolderGit2,
  Server,
  Network,
  Play,
  PauseCircle,
  PlayCircle,
} from "lucide-react"

/**
 * Global Cmd+K / Ctrl+K command palette.
 *
 * Sources:
 * - Recent projects / tasks / workers / groups (navigate)
 * - Actions: 立即运行 X / 暂停 X / 启用 X
 *
 * Data uses react-query cache so opening is instant when caches are warm.
 */
export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const navigate = useNavigate()
  const qc = useQueryClient()

  // Cmd+K / Ctrl+K toggle
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen((o) => !o)
      }
      if (e.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const tasksQ = useQuery({
    queryKey: ["tasks"],
    queryFn: () => listTasks({ page_size: 100 }),
    enabled: open,
  })
  const projectsQ = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects({ page_size: 100 }),
    enabled: open,
  })
  const workersQ = useQuery({
    queryKey: ["workers"],
    queryFn: listWorkers,
    enabled: open,
  })
  const groupsQ = useQuery({
    queryKey: ["worker-groups"],
    queryFn: listWorkerGroups,
    enabled: open,
  })

  const close = () => {
    setOpen(false)
    setSearch("")
  }

  const go = (path: string) => {
    navigate(path)
    close()
  }

  const runTask = async (id: string, name: string) => {
    try {
      await runTaskNow(id)
      toast.success(`已触发：${name}`)
    } catch (e: any) {
      toast.error(`触发失败：${e?.response?.data?.detail || e.message}`)
    } finally {
      qc.invalidateQueries({ queryKey: ["tasks"] })
      close()
    }
  }

  const togglePause = async (id: string, name: string, active: boolean) => {
    try {
      if (active) {
        await pauseTask(id)
        toast.success(`已暂停：${name}`)
      } else {
        await resumeTask(id)
        toast.success(`已启用：${name}`)
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message)
    } finally {
      qc.invalidateQueries({ queryKey: ["tasks"] })
      close()
    }
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] bg-black/40"
      onClick={close}
    >
      <Command
        className="w-full max-w-xl rounded-lg border bg-popover shadow-xl"
        onClick={(e) => e.stopPropagation()}
        label="命令面板"
      >
        <Command.Input
          value={search}
          onValueChange={setSearch}
          placeholder="搜索任务 / 项目 / 节点... 或输入操作"
          className="w-full px-4 py-3 bg-transparent outline-none border-b text-sm"
          autoFocus
        />
        <Command.List className="max-h-[400px] overflow-y-auto p-2">
          <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
            没有匹配项
          </Command.Empty>

          {projectsQ.data?.items.length ? (
            <Command.Group heading="📁 项目">
              {projectsQ.data.items.map((p) => (
                <Command.Item
                  key={p.id}
                  value={`project ${p.name}`}
                  onSelect={() => go(`/projects/${p.id}`)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer text-sm aria-selected:bg-accent"
                >
                  <FolderGit2 className="h-4 w-4 text-blue-600" />
                  <span>{p.name}</span>
                </Command.Item>
              ))}
            </Command.Group>
          ) : null}

          {tasksQ.data?.items.length ? (
            <Command.Group heading="⏰ 任务">
              {tasksQ.data.items.map((t) => (
                <Command.Item
                  key={t.id}
                  value={`task ${t.name}`}
                  onSelect={() => go(`/tasks/${t.id}`)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer text-sm aria-selected:bg-accent"
                >
                  <ListTodo className="h-4 w-4 text-emerald-600" />
                  <span>{t.name}</span>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {t.is_active ? "活跃" : "暂停"}
                  </span>
                </Command.Item>
              ))}
            </Command.Group>
          ) : null}

          {workersQ.data?.items.length ? (
            <Command.Group heading="🖥 节点">
              {workersQ.data.items.map((w) => (
                <Command.Item
                  key={w.id}
                  value={`worker ${w.name} ${w.hostname}`}
                  onSelect={() => go(`/workers`)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer text-sm aria-selected:bg-accent"
                >
                  <Server className="h-4 w-4 text-violet-600" />
                  <span>{w.name}</span>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {w.status}
                  </span>
                </Command.Item>
              ))}
            </Command.Group>
          ) : null}

          {groupsQ.data?.length ? (
            <Command.Group heading="🏷 节点组">
              {groupsQ.data.map((g) => (
                <Command.Item
                  key={g.id}
                  value={`group ${g.name}`}
                  onSelect={() => go(`/worker-groups`)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer text-sm aria-selected:bg-accent"
                >
                  <Network className="h-4 w-4 text-amber-600" />
                  <span>{g.name}</span>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {g.worker_count} 节点
                  </span>
                </Command.Item>
              ))}
            </Command.Group>
          ) : null}

          {tasksQ.data?.items.length ? (
            <Command.Group heading="⚡ 任务操作">
              {tasksQ.data.items.slice(0, 10).map((t) => (
                <Command.Item
                  key={`run-${t.id}`}
                  value={`run trigger 立即运行 ${t.name}`}
                  onSelect={() => runTask(t.id, t.name)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer text-sm aria-selected:bg-accent"
                >
                  <Play className="h-4 w-4 text-emerald-600" />
                  <span>立即运行 — {t.name}</span>
                </Command.Item>
              ))}
              {tasksQ.data.items.slice(0, 10).map((t) => (
                <Command.Item
                  key={`pause-${t.id}`}
                  value={`${t.is_active ? "暂停" : "启用"} ${t.name}`}
                  onSelect={() => togglePause(t.id, t.name, t.is_active)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer text-sm aria-selected:bg-accent"
                >
                  {t.is_active ? (
                    <PauseCircle className="h-4 w-4 text-amber-600" />
                  ) : (
                    <PlayCircle className="h-4 w-4 text-emerald-600" />
                  )}
                  <span>
                    {t.is_active ? "暂停" : "启用"} — {t.name}
                  </span>
                </Command.Item>
              ))}
            </Command.Group>
          ) : null}
        </Command.List>
        <div className="border-t px-3 py-1.5 text-xs text-muted-foreground flex items-center justify-between">
          <span>↑↓ 导航 · ↵ 选择 · esc 关闭</span>
          <span className="font-mono">⌘K</span>
        </div>
      </Command>
    </div>
  )
}
