import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Plus, Pencil, Trash2, Eye, EyeOff, Lock } from "lucide-react"
import api from "@/api/client"

interface EnvVar {
  id: string
  project_id: string
  key: string
  value: string
  description: string | null
  is_secret: boolean
  created_at: string
  updated_at: string
}

interface Project {
  id: string
  name: string
}

interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pages: number
}

interface EnvVarForm {
  project_id: string
  key: string
  value: string
  description: string
  is_secret: boolean
}

const defaultForm: EnvVarForm = {
  project_id: "",
  key: "",
  value: "",
  description: "",
  is_secret: true,
}

export function EnvVarsPage() {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<EnvVarForm>(defaultForm)
  const [selectedProject, setSelectedProject] = useState<string>("")
  const [revealedValues, setRevealedValues] = useState<Record<string, string>>({})

  const { data: projectsData } = useQuery<PaginatedResponse<Project>>({
    queryKey: ["projects"],
    queryFn: async () => (await api.get("/projects")).data,
  })

  const { data: envVarsData, isLoading } = useQuery<PaginatedResponse<EnvVar>>({
    queryKey: ["env-vars", selectedProject],
    queryFn: async () => {
      if (!selectedProject) return { items: [], total: 0, page: 1, pages: 0 }
      return (await api.get(`/env-vars?project_id=${selectedProject}`)).data
    },
    enabled: !!selectedProject,
  })

  const createMutation = useMutation({
    mutationFn: async (data: EnvVarForm) => {
      return (await api.post("/env-vars", data)).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["env-vars"] })
      closeDialog()
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<EnvVarForm> }) => {
      return (await api.patch(`/env-vars/${id}`, data)).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["env-vars"] })
      closeDialog()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      return (await api.delete(`/env-vars/${id}`)).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["env-vars"] })
    },
  })

  const revealValue = async (id: string) => {
    if (revealedValues[id]) {
      setRevealedValues((prev) => {
        const copy = { ...prev }
        delete copy[id]
        return copy
      })
      return
    }
    try {
      const response = await api.get(`/env-vars/${id}/reveal`)
      setRevealedValues((prev) => ({ ...prev, [id]: response.data.value }))
    } catch {
      // Silently fail
    }
  }

  const closeDialog = () => {
    setDialogOpen(false)
    setEditingId(null)
    setForm(defaultForm)
  }

  const openCreate = () => {
    setForm({ ...defaultForm, project_id: selectedProject })
    setEditingId(null)
    setDialogOpen(true)
  }

  const openEdit = (envVar: EnvVar) => {
    setForm({
      project_id: envVar.project_id,
      key: envVar.key,
      value: "",
      description: envVar.description ?? "",
      is_secret: envVar.is_secret,
    })
    setEditingId(envVar.id)
    setDialogOpen(true)
  }

  const handleSubmit = () => {
    if (editingId) {
      const payload: Partial<EnvVarForm> = {
        key: form.key,
        description: form.description,
        is_secret: form.is_secret,
      }
      if (form.value) {
        payload.value = form.value
      }
      updateMutation.mutate({ id: editingId, data: payload })
    } else {
      createMutation.mutate(form)
    }
  }

  const projects = projectsData?.items ?? []

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">环境变量</h1>
        <Button onClick={openCreate} disabled={!selectedProject}>
          <Plus className="h-4 w-4 mr-2" />
          新建变量
        </Button>
      </div>

      {/* Project selector */}
      <div className="mb-6">
        <Label htmlFor="project-filter" className="mb-2 block text-sm">
          选择项目
        </Label>
        <Select
          id="project-filter"
          value={selectedProject}
          onChange={(e) => {
            setSelectedProject(e.target.value)
            setRevealedValues({})
          }}
        >
          <option value="">请选择项目</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
      </div>

      {!selectedProject ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground">请先选择一个项目查看其环境变量。</p>
          </CardContent>
        </Card>
      ) : isLoading ? (
        <p className="text-muted-foreground">加载中...</p>
      ) : envVarsData?.items.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground">该项目暂无环境变量，点击右上角创建。</p>
          </CardContent>
        </Card>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left p-3 font-medium">Key</th>
                <th className="text-left p-3 font-medium">Value</th>
                <th className="text-left p-3 font-medium">描述</th>
                <th className="text-left p-3 font-medium">类型</th>
                <th className="text-left p-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {envVarsData?.items.map((envVar) => (
                <tr key={envVar.id} className="border-t hover:bg-muted/30">
                  <td className="p-3 font-mono text-xs font-medium">{envVar.key}</td>
                  <td className="p-3 font-mono text-xs">
                    {envVar.is_secret ? (
                      <span className="text-muted-foreground">
                        {revealedValues[envVar.id] ?? "***"}
                      </span>
                    ) : (
                      <span>{envVar.value}</span>
                    )}
                  </td>
                  <td className="p-3 text-muted-foreground text-xs">
                    {envVar.description || "-"}
                  </td>
                  <td className="p-3">
                    {envVar.is_secret ? (
                      <Badge variant="secondary">
                        <Lock className="h-3 w-3 mr-1" />
                        密钥
                      </Badge>
                    ) : (
                      <Badge variant="outline">明文</Badge>
                    )}
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-1">
                      {envVar.is_secret && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => revealValue(envVar.id)}
                          title={revealedValues[envVar.id] ? "隐藏" : "查看"}
                        >
                          {revealedValues[envVar.id] ? (
                            <EyeOff className="h-4 w-4" />
                          ) : (
                            <Eye className="h-4 w-4" />
                          )}
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openEdit(envVar)}
                        title="编辑"
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                          if (confirm("确定要删除此环境变量吗？")) {
                            deleteMutation.mutate(envVar.id)
                          }
                        }}
                        title="删除"
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create / Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent open={dialogOpen} onClose={closeDialog}>
          <DialogHeader>
            <DialogTitle>{editingId ? "编辑环境变量" : "新建环境变量"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="key">Key</Label>
              <Input
                id="key"
                value={form.key}
                onChange={(e) => setForm({ ...form, key: e.target.value })}
                placeholder="例: DATABASE_URL"
                className="font-mono"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="value">
                Value {editingId && "(留空则不修改)"}
              </Label>
              <Input
                id="value"
                type="password"
                value={form.value}
                onChange={(e) => setForm({ ...form, value: e.target.value })}
                placeholder={editingId ? "留空则保持原值" : "输入变量值"}
                className="font-mono"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">描述</Label>
              <Input
                id="description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="变量用途说明（可选）"
              />
            </div>

            <div className="flex items-center gap-3">
              <Label htmlFor="is_secret">加密存储</Label>
              <Switch
                id="is_secret"
                checked={form.is_secret}
                onCheckedChange={(checked) => setForm({ ...form, is_secret: checked })}
              />
              <span className="text-xs text-muted-foreground">
                {form.is_secret ? "值将加密存储并在列表中隐藏" : "值以明文显示"}
              </span>
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={closeDialog}>
                取消
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {createMutation.isPending || updateMutation.isPending ? "提交中..." : "确定"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
