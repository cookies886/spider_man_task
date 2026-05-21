import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import {
  type CollaboratorRow,
  listUsers,
  listProjectCollaborators,
  addProjectCollaborator,
  removeProjectCollaborator,
  listEnvCollaborators,
  addEnvCollaborator,
  removeEnvCollaborator,
} from "@/api/client"

type Resource = "project" | "environment"

interface Props {
  resource: Resource
  resourceId: string
  /** Whether the current user can manage (add/remove). Owner or superuser only. */
  canManage: boolean
}

const fns = {
  project: {
    list: listProjectCollaborators,
    add: addProjectCollaborator,
    remove: removeProjectCollaborator,
  },
  environment: {
    list: listEnvCollaborators,
    add: addEnvCollaborator,
    remove: removeEnvCollaborator,
  },
}

export function CollaboratorsCard({ resource, resourceId, canManage }: Props) {
  const qc = useQueryClient()
  const key = ["collaborators", resource, resourceId]
  const { data, isLoading } = useQuery({
    queryKey: key,
    queryFn: () => fns[resource].list(resourceId),
  })

  const [showAdd, setShowAdd] = useState(false)
  const removeMut = useMutation({
    mutationFn: (userId: string) => fns[resource].remove(resourceId, userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  })

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="font-semibold">协同人员</h3>
            <p className="text-xs text-muted-foreground">
              协同人员可读写但不能删除。只有 owner / 管理员能管理协同人员。
            </p>
          </div>
          {canManage && (
            <Button size="sm" onClick={() => setShowAdd(true)}>
              + 添加
            </Button>
          )}
        </div>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">加载中...</p>
        ) : (data?.length ?? 0) === 0 ? (
          <p className="text-sm text-muted-foreground">尚无协同人员</p>
        ) : (
          <ul className="space-y-2">
            {data?.map((c) => (
              <li
                key={c.user_id}
                className="flex items-center justify-between rounded border px-3 py-2"
              >
                <div>
                  <span className="font-medium">{c.username}</span>
                  {c.full_name && (
                    <span className="text-sm text-muted-foreground ml-2">
                      ({c.full_name})
                    </span>
                  )}
                  <Badge variant="secondary" className="ml-2 text-xs">
                    {new Date(c.added_at).toLocaleDateString()}
                  </Badge>
                </div>
                {canManage && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => removeMut.mutate(c.user_id)}
                  >
                    移除
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}

        <AddCollaboratorDialog
          open={showAdd}
          onOpenChange={setShowAdd}
          existing={data ?? []}
          onAdd={async (userId) => {
            await fns[resource].add(resourceId, userId)
            qc.invalidateQueries({ queryKey: key })
          }}
        />
      </CardContent>
    </Card>
  )
}

function AddCollaboratorDialog(props: {
  open: boolean
  onOpenChange: (o: boolean) => void
  existing: CollaboratorRow[]
  onAdd: (userId: string) => Promise<void>
}) {
  const usersQ = useQuery({
    queryKey: ["users-for-collab"],
    queryFn: () => listUsers({ page_size: 100 }),
    enabled: props.open,
  })
  const [pick, setPick] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState("")

  const existingIds = new Set(props.existing.map((c) => c.user_id))
  const candidates =
    usersQ.data?.items.filter(
      (u) => !existingIds.has(u.id) && !u.is_superuser
    ) ?? []

  const handleSubmit = async () => {
    if (!pick) return
    setErr("")
    setSubmitting(true)
    try {
      await props.onAdd(pick)
      props.onOpenChange(false)
      setPick("")
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
          <DialogTitle>添加协同人员</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <select
            className="w-full p-2 rounded border bg-background"
            value={pick}
            onChange={(e) => setPick(e.target.value)}
          >
            <option value="">— 选择用户 —</option>
            {candidates.map((u) => (
              <option key={u.id} value={u.id}>
                {u.username}
                {u.full_name ? ` (${u.full_name})` : ""}
              </option>
            ))}
          </select>
          {err && <p className="text-sm text-destructive">{err}</p>}
        </div>
        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !pick}>
            {submitting ? "添加中..." : "添加"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
