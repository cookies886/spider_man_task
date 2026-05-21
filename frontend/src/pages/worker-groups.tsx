import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import {
  type WorkerGroup,
  createWorkerGroup,
  deleteWorkerGroup,
  listWorkerGroups,
  updateWorkerGroup,
} from "@/api/client"

export function WorkerGroupsPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ["worker-groups"],
    queryFn: listWorkerGroups,
  })
  const [editing, setEditing] = useState<WorkerGroup | null>(null)
  const [creating, setCreating] = useState(false)

  const delMut = useMutation({
    mutationFn: deleteWorkerGroup,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["worker-groups"] }),
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">节点组</h1>
        <Button onClick={() => setCreating(true)}>+ 新建节点组</Button>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">加载中...</p>
      ) : (data?.length ?? 0) === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground">
              还没有节点组。建立分组后，可以在创建任务时按组调度。
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data?.map((g) => (
            <Card key={g.id}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium">{g.name}</span>
                  <Badge variant="outline">{g.worker_count} 节点</Badge>
                </div>
                {g.description && (
                  <p className="text-sm text-muted-foreground mb-2">
                    {g.description}
                  </p>
                )}
                {g.tags && g.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-3">
                    {g.tags.map((t) => (
                      <Badge key={t} variant="secondary">
                        {t}
                      </Badge>
                    ))}
                  </div>
                )}
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditing(g)}
                  >
                    编辑
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (confirm(`删除节点组 "${g.name}"？组内 worker 会变为未分组。`)) {
                        delMut.mutate(g.id)
                      }
                    }}
                  >
                    删除
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <GroupDialog
        open={creating}
        onOpenChange={setCreating}
        group={null}
        onSaved={() => qc.invalidateQueries({ queryKey: ["worker-groups"] })}
      />
      <GroupDialog
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        group={editing}
        onSaved={() => qc.invalidateQueries({ queryKey: ["worker-groups"] })}
      />
    </div>
  )
}

function GroupDialog(props: {
  open: boolean
  onOpenChange: (o: boolean) => void
  group: WorkerGroup | null
  onSaved: () => void
}) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [tags, setTags] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState("")

  // Reset form on open
  useResetOnOpen(props.open, () => {
    setName(props.group?.name ?? "")
    setDescription(props.group?.description ?? "")
    setTags((props.group?.tags ?? []).join(","))
    setErr("")
  })

  const handleSubmit = async () => {
    setErr("")
    setSubmitting(true)
    try {
      const body = {
        name: name.trim(),
        description: description.trim() || null,
        tags: tags
          ? tags
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
      }
      if (props.group) {
        await updateWorkerGroup(props.group.id, body)
      } else {
        await createWorkerGroup(body)
      }
      props.onSaved()
      props.onOpenChange(false)
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e.message || String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent
        className="max-w-md"
        open={props.open}
        onClose={() => props.onOpenChange(false)}
      >
        <DialogHeader>
          <DialogTitle>{props.group ? "编辑节点组" : "新建节点组"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="组名（如 windows-cluster）"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            placeholder="描述（可选）"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Input
            placeholder="标签（逗号分隔）"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
          {err && <p className="text-sm text-destructive">{err}</p>}
        </div>
        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !name.trim()}>
            {submitting ? "保存中..." : "保存"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

import { useEffect } from "react"

function useResetOnOpen(open: boolean, fn: () => void) {
  useEffect(() => {
    if (open) fn()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
}
