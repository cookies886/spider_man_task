import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  listEnvironments,
  listPyVers,
  listMirrors,
  createEnvironment,
  rebuildEnvironment,
  deleteEnvironment,
  type EnvStatus,
  type EnvironmentInfo,
} from "@/api/client"
import { useAuthStore } from "@/store/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { CollaboratorsCard } from "@/components/collaborators-card"

const STATUS_COLOR: Record<EnvStatus, string> = {
  creating: "text-blue-600",
  ready: "text-green-600",
  updating: "text-blue-600",
  failed: "text-destructive",
}

export function EnvironmentsPage() {
  const qc = useQueryClient()
  const me = useAuthStore((s) => s.me)
  const envsQ = useQuery({
    queryKey: ["environments"],
    queryFn: () => listEnvironments({ page_size: 100 }),
    refetchInterval: 5000,
  })
  const [createOpen, setCreateOpen] = useState(false)
  const [collabEnv, setCollabEnv] = useState<EnvironmentInfo | null>(null)

  const deleteMut = useMutation({
    mutationFn: deleteEnvironment,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["environments"] }),
  })
  const rebuildMut = useMutation({
    mutationFn: rebuildEnvironment,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["environments"] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">环境管理</h1>
        <Button onClick={() => setCreateOpen(true)}>新建环境</Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>虚拟环境列表</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-2">名称</th>
                <th>状态</th>
                <th>路径</th>
                <th>更新</th>
                <th className="text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {envsQ.data?.items.map((e) => (
                <EnvRow
                  key={e.id}
                  e={e}
                  onRebuild={() => rebuildMut.mutate(e.id)}
                  onDelete={() => {
                    if (confirm(`删除环境 ${e.name}?`)) deleteMut.mutate(e.id)
                  }}
                  onShare={() => setCollabEnv(e)}
                />
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <CreateEnvDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => qc.invalidateQueries({ queryKey: ["environments"] })}
      />

      <Dialog open={!!collabEnv} onOpenChange={(o) => !o && setCollabEnv(null)}>
        <DialogContent
          className="max-w-2xl"
          open={!!collabEnv}
          onClose={() => setCollabEnv(null)}
        >
          <DialogHeader>
            <DialogTitle>
              环境「{collabEnv?.name}」协同人员
            </DialogTitle>
          </DialogHeader>
          {collabEnv && (
            <CollaboratorsCard
              resource="environment"
              resourceId={collabEnv.id}
              canManage={
                !!me?.is_superuser ||
                (!!me?.id && me.id === collabEnv.owner_id)
              }
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function EnvRow({
  e,
  onRebuild,
  onDelete,
  onShare,
}: {
  e: EnvironmentInfo
  onRebuild: () => void
  onDelete: () => void
  onShare: () => void
}) {
  return (
    <tr className="border-t">
      <td className="py-2 font-medium">{e.name}</td>
      <td className={`text-xs font-medium ${STATUS_COLOR[e.status]}`}>
        {e.status}
        {e.error_msg && (
          <span className="ml-2 text-xs text-destructive" title={e.error_msg}>
            ⚠
          </span>
        )}
      </td>
      <td className="font-mono text-xs text-muted-foreground truncate max-w-[20rem]">
        {e.venv_path ?? "-"}
      </td>
      <td className="text-muted-foreground">
        {new Date(e.updated_at).toLocaleString()}
      </td>
      <td className="text-right space-x-1">
        <a
          href={`/api/v1/environments/${e.id}/log`}
          className="text-xs underline text-muted-foreground"
        >
          安装日志
        </a>
        <Button size="sm" variant="ghost" onClick={onShare}>
          协同人员
        </Button>
        <Button size="sm" variant="ghost" onClick={onRebuild}>
          重建
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

function CreateEnvDialog(props: {
  open: boolean
  onOpenChange: (o: boolean) => void
  onCreated: () => void
}) {
  const pyversQ = useQuery({
    queryKey: ["python-versions"],
    queryFn: listPyVers,
    enabled: props.open,
  })
  const mirrorsQ = useQuery({
    queryKey: ["mirror-sources"],
    queryFn: listMirrors,
    enabled: props.open,
  })

  const [form, setForm] = useState({
    name: "",
    description: "",
    python_version_id: "",
    mirror_id: "",
    requirements: "",
    tags: "",
  })
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState("")

  const handleSubmit = async () => {
    setErr("")
    setSubmitting(true)
    try {
      await createEnvironment({
        name: form.name,
        description: form.description || null,
        python_version_id: form.python_version_id || null,
        mirror_id: form.mirror_id || null,
        requirements: form.requirements || null,
        tags: form.tags
          ? form.tags
              .split(",")
              .map((t) => t.trim())
              .filter(Boolean)
          : [],
      })
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
          <DialogTitle>新建虚拟环境</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
          <Input
            placeholder="环境名"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Input
            placeholder="描述（可选）"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <select
            className="w-full p-2 rounded border bg-background"
            value={form.python_version_id}
            onChange={(e) =>
              setForm({ ...form, python_version_id: e.target.value })
            }
          >
            <option value="">— 使用系统默认 Python —</option>
            {pyversQ.data?.filter((v) => v.status === "ready").map((v) => (
              <option key={v.id} value={v.id}>
                {v.version} {v.is_default ? "★" : ""}
              </option>
            ))}
          </select>
          <select
            className="w-full p-2 rounded border bg-background"
            value={form.mirror_id}
            onChange={(e) => setForm({ ...form, mirror_id: e.target.value })}
          >
            <option value="">— 使用 PyPI 默认 —</option>
            {mirrorsQ.data?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} {m.is_default ? "★" : ""}
              </option>
            ))}
          </select>
          <Textarea
            placeholder="requirements.txt 内容（每行一个包）"
            rows={6}
            value={form.requirements}
            onChange={(e) =>
              setForm({ ...form, requirements: e.target.value })
            }
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
