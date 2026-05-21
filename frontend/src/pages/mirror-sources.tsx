import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { listMirrors, createMirror, deleteMirror } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export function MirrorSourcesPage() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ["mirrors"], queryFn: listMirrors })
  const [createOpen, setCreateOpen] = useState(false)

  const del = useMutation({
    mutationFn: deleteMirror,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["mirrors"] })
      toast.success("已删除")
    },
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">PyPI 镜像源</h1>
        <Button onClick={() => setCreateOpen(true)}>+ 新增镜像源</Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground border-b">
              <tr>
                <th className="py-3 pl-4">名称</th>
                <th>URL</th>
                <th>默认</th>
                <th>类型</th>
                <th className="text-right pr-4">操作</th>
              </tr>
            </thead>
            <tbody>
              {q.isLoading && (
                <tr>
                  <td colSpan={5} className="p-4 text-center text-muted-foreground">
                    加载中…
                  </td>
                </tr>
              )}
              {q.data?.map((m) => (
                <tr key={m.id} className="border-t">
                  <td className="py-2 pl-4 font-medium">{m.name}</td>
                  <td className="font-mono text-xs">{m.url}</td>
                  <td>
                    {m.is_default && <Badge variant="default">默认</Badge>}
                  </td>
                  <td>
                    {m.is_builtin ? (
                      <Badge variant="secondary">内置</Badge>
                    ) : (
                      <Badge variant="outline">自定义</Badge>
                    )}
                  </td>
                  <td className="text-right pr-4">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive"
                      disabled={m.is_builtin}
                      onClick={() => {
                        if (confirm(`删除镜像源 ${m.name}?`)) del.mutate(m.id)
                      }}
                      title={m.is_builtin ? "内置镜像源不可删除" : ""}
                    >
                      删除
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <CreateMirrorDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSaved={() => qc.invalidateQueries({ queryKey: ["mirrors"] })}
      />
    </div>
  )
}

function CreateMirrorDialog(props: {
  open: boolean
  onOpenChange: (o: boolean) => void
  onSaved: () => void
}) {
  const [name, setName] = useState("")
  const [url, setUrl] = useState("")
  const [isDefault, setIsDefault] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState("")

  const handleSubmit = async () => {
    setErr("")
    setSubmitting(true)
    try {
      await createMirror({ name: name.trim(), url: url.trim(), is_default: isDefault })
      toast.success("镜像源已新增")
      props.onSaved()
      props.onOpenChange(false)
      setName(""); setUrl(""); setIsDefault(false)
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e.message || String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>新增 PyPI 镜像源</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="名称（如 公司内部镜像）"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            placeholder="URL（如 https://mirrors.example.com/pypi/simple/）"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
            />
            设为默认镜像源
          </label>
          {err && <p className="text-sm text-destructive">{err}</p>}
        </div>
        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !name || !url}>
            {submitting ? "保存中…" : "保存"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
