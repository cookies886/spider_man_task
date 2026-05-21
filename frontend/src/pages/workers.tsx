import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  type WorkerSummary,
  type WorkerCreated,
  createWorker,
  deleteWorker,
  listWorkerGroups,
  listWorkers,
  updateWorker,
} from "@/api/client"

const statusVariant = (status: string) => {
  switch (status) {
    case "online":
      return "success" as const
    case "busy":
      return "warning" as const
    case "offline":
      return "destructive" as const
    default:
      return "outline" as const
  }
}

export function WorkersPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ["workers"],
    queryFn: listWorkers,
  })
  const groupsQ = useQuery({ queryKey: ["worker-groups"], queryFn: listWorkerGroups })
  const groupNameMap = new Map(groupsQ.data?.map((g) => [g.id, g.name]) ?? [])

  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<WorkerSummary | null>(null)
  const [createdSecret, setCreatedSecret] = useState<WorkerCreated | null>(null)

  const delMut = useMutation({
    mutationFn: deleteWorker,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workers"] }),
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Worker 节点</h1>
        <Button onClick={() => setCreating(true)}>+ 添加节点</Button>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">加载中...</p>
      ) : (data?.items.length ?? 0) === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground">暂无注册的 Worker 节点</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data?.items.map((worker) => (
            <Card key={worker.id}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between mb-3">
                  <span className="font-medium">{worker.hostname}</span>
                  <Badge variant={statusVariant(worker.status)}>
                    {worker.status}
                  </Badge>
                </div>
                <div className="space-y-1 text-sm text-muted-foreground">
                  <p>
                    名称: {worker.name}
                    {worker.group_id && (
                      <Badge variant="secondary" className="ml-2">
                        {groupNameMap.get(worker.group_id) ?? "组"}
                      </Badge>
                    )}
                  </p>
                  <p>类型: {worker.type}</p>
                  <p>
                    地址: {worker.ip}:{worker.port}
                  </p>
                  <p>
                    负载: {worker.current_tasks}/{worker.max_slots}
                  </p>
                  <p>
                    CPU: {worker.cpu_usage.toFixed(1)}% | 内存:{" "}
                    {worker.mem_usage.toFixed(1)}%
                  </p>
                  <p>
                    最后心跳:{" "}
                    {worker.last_heartbeat
                      ? new Date(worker.last_heartbeat).toLocaleString()
                      : "从未"}
                  </p>
                </div>
                <div className="flex gap-2 mt-3">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditing(worker)}
                  >
                    编辑
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={worker.type === "master_local"}
                    onClick={() => {
                      if (
                        confirm(`删除节点 "${worker.hostname}"？此操作不可恢复。`)
                      ) {
                        delMut.mutate(worker.id)
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

      <WorkerDialog
        open={creating}
        onOpenChange={setCreating}
        worker={null}
        groups={groupsQ.data ?? []}
        onCreated={(w) => {
          qc.invalidateQueries({ queryKey: ["workers"] })
          setCreatedSecret(w)
        }}
        onEdited={() => qc.invalidateQueries({ queryKey: ["workers"] })}
      />
      <WorkerDialog
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        worker={editing}
        groups={groupsQ.data ?? []}
        onCreated={() => {}}
        onEdited={() => qc.invalidateQueries({ queryKey: ["workers"] })}
      />

      <ApiKeyDialog
        worker={createdSecret}
        onClose={() => setCreatedSecret(null)}
      />
    </div>
  )
}

function WorkerDialog(props: {
  open: boolean
  onOpenChange: (o: boolean) => void
  worker: WorkerSummary | null
  groups: { id: string; name: string }[]
  onCreated: (w: WorkerCreated) => void
  onEdited: () => void
}) {
  const [name, setName] = useState("")
  const [hostname, setHostname] = useState("")
  const [ip, setIp] = useState("")
  const [port, setPort] = useState("8001")
  const [maxSlots, setMaxSlots] = useState("4")
  const [groupId, setGroupId] = useState<string>("")
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState("")

  useEffect(() => {
    if (!props.open) return
    setErr("")
    if (props.worker) {
      setName(props.worker.name)
      setHostname(props.worker.hostname)
      setIp(props.worker.ip)
      setPort(String(props.worker.port))
      setMaxSlots(String(props.worker.max_slots))
      setGroupId(props.worker.group_id ?? "")
    } else {
      setName("")
      setHostname("")
      setIp("")
      setPort("8001")
      setMaxSlots("4")
      setGroupId("")
    }
  }, [props.open, props.worker])

  const isEdit = !!props.worker

  const handleSubmit = async () => {
    setErr("")
    setSubmitting(true)
    try {
      if (isEdit) {
        await updateWorker(props.worker!.id, {
          name: name.trim(),
          hostname: hostname.trim(),
          ip: ip.trim(),
          port: parseInt(port, 10),
          max_slots: parseInt(maxSlots, 10),
          group_id: groupId || null,
        })
        props.onEdited()
      } else {
        const created = await createWorker({
          name: name.trim(),
          hostname: hostname.trim(),
          ip: ip.trim(),
          port: parseInt(port, 10),
          max_slots: parseInt(maxSlots, 10),
          group_id: groupId || null,
        })
        props.onCreated(created)
      }
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
          <DialogTitle>{isEdit ? "编辑节点" : "添加节点"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="名称"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            placeholder="hostname"
            value={hostname}
            onChange={(e) => setHostname(e.target.value)}
          />
          <Input
            placeholder="IP 地址"
            value={ip}
            onChange={(e) => setIp(e.target.value)}
          />
          <div className="grid grid-cols-2 gap-2">
            <Input
              placeholder="端口"
              value={port}
              onChange={(e) => setPort(e.target.value)}
            />
            <Input
              placeholder="最大并发"
              value={maxSlots}
              onChange={(e) => setMaxSlots(e.target.value)}
            />
          </div>
          <select
            className="w-full p-2 rounded border bg-background"
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
          >
            <option value="">— 不分组 —</option>
            {props.groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
          {err && <p className="text-sm text-destructive">{err}</p>}
        </div>
        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "保存中..." : "保存"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ApiKeyDialog(props: {
  worker: WorkerCreated | null
  onClose: () => void
}) {
  if (!props.worker) return null
  return (
    <Dialog open={!!props.worker} onOpenChange={(o) => !o && props.onClose()}>
      <DialogContent className="max-w-md" open={true} onClose={props.onClose}>
        <DialogHeader>
          <DialogTitle>节点已创建 — 请保存 API Key</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            此 API Key 仅在此处显示一次，关闭后无法再次查看。请保管好它并配置到对应工作节点上。
          </p>
          <div className="space-y-1 text-sm">
            <div>
              <span className="font-medium">node_id:</span>{" "}
              <code className="bg-muted px-1.5 py-0.5 rounded">
                {props.worker.node_id}
              </code>
            </div>
            <div>
              <span className="font-medium">API Key:</span>
            </div>
            <pre className="bg-muted p-2 rounded text-xs whitespace-pre-wrap break-all">
              {props.worker.api_key}
            </pre>
          </div>
        </div>
        <div className="flex justify-end pt-3">
          <Button onClick={props.onClose}>我已保存</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
