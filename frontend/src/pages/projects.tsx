import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  listProjects,
  createGitProject,
  createZipProject,
  deleteProject,
  triggerGitSync,
  type ProjectCreateBody,
  type ProjectSummary,
} from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export function ProjectsPage() {
  const qc = useQueryClient()
  const projectsQ = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects({ page_size: 100 }),
  })
  const [createOpen, setCreateOpen] = useState(false)

  const deleteMut = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  })
  const syncMut = useMutation({
    mutationFn: triggerGitSync,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">项目管理</h1>
        <Button onClick={() => setCreateOpen(true)}>新建项目</Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>项目列表</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-2">名称</th>
                <th>来源</th>
                <th>工作路径</th>
                <th>当前哈希</th>
                <th>更新时间</th>
                <th className="text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {projectsQ.data?.items.map((p) => (
                <ProjectRow
                  key={p.id}
                  p={p}
                  onDelete={() => {
                    if (confirm(`删除项目 ${p.name}?`)) deleteMut.mutate(p.id)
                  }}
                  onSync={() => syncMut.mutate(p.id)}
                />
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <CreateProjectDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => qc.invalidateQueries({ queryKey: ["projects"] })}
      />
    </div>
  )
}

function ProjectRow({
  p,
  onDelete,
  onSync,
}: {
  p: ProjectSummary
  onDelete: () => void
  onSync: () => void
}) {
  return (
    <tr className="border-t">
      <td className="py-2 font-medium">
        <Link to={`/projects/${p.id}`} className="text-primary hover:underline">
          {p.name}
        </Link>
      </td>
      <td>
        <span
          className={`px-1.5 py-0.5 rounded text-xs ${
            p.source_type === "git"
              ? "bg-blue-100 text-blue-700"
              : "bg-amber-100 text-amber-700"
          }`}
        >
          {p.source_type}
        </span>
      </td>
      <td className="font-mono text-xs">{p.work_path}</td>
      <td className="font-mono text-xs text-muted-foreground">
        {p.current_hash ? p.current_hash.slice(0, 8) : "-"}
      </td>
      <td className="text-muted-foreground">
        {new Date(p.updated_at).toLocaleString()}
      </td>
      <td className="text-right space-x-1">
        {p.source_type === "git" && (
          <Button size="sm" variant="ghost" onClick={onSync}>
            拉取
          </Button>
        )}
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
  source_type: "zip" | "git"
  work_path: string
  tags: string
  git_url: string
  git_branch: string
  git_username: string
  git_password: string
  zip_file: File | null
}

function CreateProjectDialog(props: {
  open: boolean
  onOpenChange: (o: boolean) => void
  onCreated: () => void
}) {
  const [form, setForm] = useState<FormState>({
    name: "",
    description: "",
    source_type: "zip",
    work_path: "/",
    tags: "",
    git_url: "",
    git_branch: "main",
    git_username: "",
    git_password: "",
    zip_file: null,
  })
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState("")

  const handleSubmit = async () => {
    setErr("")
    setSubmitting(true)
    try {
      const body: ProjectCreateBody = {
        name: form.name,
        description: form.description || null,
        source_type: form.source_type,
        work_path: form.work_path,
        tags: form.tags
          ? form.tags
              .split(",")
              .map((t) => t.trim())
              .filter(Boolean)
          : [],
      }
      if (form.source_type === "zip") {
        if (!form.zip_file) {
          setErr("请选择 ZIP 文件")
          setSubmitting(false)
          return
        }
        await createZipProject(body, form.zip_file)
      } else {
        body.git = {
          url: form.git_url,
          branch: form.git_branch || "main",
          username: form.git_username || null,
          password: form.git_password || null,
        }
        await createGitProject(body)
      }
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
          <DialogTitle>新建项目</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="项目名"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Input
            placeholder="描述（可选）"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <div className="flex gap-2">
            <button
              type="button"
              className={`flex-1 py-2 rounded border ${
                form.source_type === "zip" ? "bg-primary text-primary-foreground" : "bg-muted"
              }`}
              onClick={() => setForm({ ...form, source_type: "zip" })}
            >
              ZIP 上传
            </button>
            <button
              type="button"
              className={`flex-1 py-2 rounded border ${
                form.source_type === "git" ? "bg-primary text-primary-foreground" : "bg-muted"
              }`}
              onClick={() => setForm({ ...form, source_type: "git" })}
            >
              Git 仓库
            </button>
          </div>

          {form.source_type === "zip" ? (
            <input
              type="file"
              accept=".zip"
              onChange={(e) =>
                setForm({ ...form, zip_file: e.target.files?.[0] ?? null })
              }
              className="block w-full text-sm"
            />
          ) : (
            <div className="space-y-2">
              <Input
                placeholder="Git URL（HTTPS）"
                value={form.git_url}
                onChange={(e) => setForm({ ...form, git_url: e.target.value })}
              />
              <Input
                placeholder="分支（默认 main）"
                value={form.git_branch}
                onChange={(e) =>
                  setForm({ ...form, git_branch: e.target.value })
                }
              />
              <Input
                placeholder="用户名（私有仓库）"
                value={form.git_username}
                onChange={(e) =>
                  setForm({ ...form, git_username: e.target.value })
                }
              />
              <Input
                type="password"
                placeholder="密码 / Token（私有仓库）"
                value={form.git_password}
                onChange={(e) =>
                  setForm({ ...form, git_password: e.target.value })
                }
              />
            </div>
          )}

          <Input
            placeholder="工作路径（默认 /，ZIP 自动推断）"
            value={form.work_path}
            onChange={(e) => setForm({ ...form, work_path: e.target.value })}
          />
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
