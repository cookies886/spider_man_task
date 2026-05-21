import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  listUsers,
  listRoles,
  createUser,
  updateUser,
  deleteUser,
  resetUserPassword,
  type UserSummary,
} from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card"

const ALL_PAGES = [
  "dashboard",
  "projects",
  "tasks",
  "workers",
  "schedules",
  "environments",
  "env-vars",
  "logs",
  "files",
  "notifications",
  "users",
  "settings",
]

export function UsersPage() {
  const qc = useQueryClient()
  const usersQ = useQuery({ queryKey: ["users"], queryFn: () => listUsers({ page_size: 100 }) })
  const rolesQ = useQuery({ queryKey: ["roles"], queryFn: listRoles })

  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<UserSummary | null>(null)
  const [resetResult, setResetResult] = useState<{ username: string; password: string } | null>(null)

  const createMut = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] })
      setCreateOpen(false)
    },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updateUser>[1] }) =>
      updateUser(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] })
      setEditing(null)
    },
  })
  const deleteMut = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  })
  const resetMut = useMutation({
    mutationFn: resetUserPassword,
    onSuccess: (data, id) => {
      const u = usersQ.data?.items.find((x) => x.id === id)
      setResetResult({ username: u?.username ?? "", password: data.new_password })
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">用户管理</h1>
        <Button onClick={() => setCreateOpen(true)}>新建用户</Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>用户列表</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-2">用户名</th>
                <th>姓名</th>
                <th>角色</th>
                <th>页面</th>
                <th>状态</th>
                <th>最后登录</th>
                <th className="text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {usersQ.data?.items.map((u) => (
                <tr key={u.id} className="border-t">
                  <td className="py-2 font-medium">
                    {u.username}
                    {u.is_superuser && (
                      <span className="ml-2 px-1.5 py-0.5 rounded text-xs bg-primary/10 text-primary">
                        超管
                      </span>
                    )}
                  </td>
                  <td>{u.full_name || "-"}</td>
                  <td>{u.role_codes.join(", ") || "-"}</td>
                  <td className="max-w-[16rem] truncate">{u.page_acls.join(", ") || "-"}</td>
                  <td>
                    {u.is_active ? (
                      <span className="text-green-600">启用</span>
                    ) : (
                      <span className="text-muted-foreground">禁用</span>
                    )}
                  </td>
                  <td className="text-muted-foreground">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "-"}
                  </td>
                  <td className="text-right space-x-1">
                    <Button size="sm" variant="ghost" onClick={() => setEditing(u)}>
                      编辑
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => resetMut.mutate(u.id)}
                      disabled={resetMut.isPending}
                    >
                      重置密码
                    </Button>
                    {!u.is_superuser && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive"
                        onClick={() => {
                          if (confirm(`删除用户 ${u.username}?`)) deleteMut.mutate(u.id)
                        }}
                      >
                        删除
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <UserFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="新建用户"
        roles={rolesQ.data ?? []}
        onSubmit={(form) =>
          createMut.mutate({
            username: form.username,
            password: form.password,
            email: form.email || null,
            full_name: form.full_name || null,
            is_active: form.is_active,
            role_codes: form.role_codes,
            page_acls: form.page_acls,
          })
        }
        submitting={createMut.isPending}
      />

      {editing && (
        <UserFormDialog
          open
          onOpenChange={(o) => !o && setEditing(null)}
          title={`编辑 ${editing.username}`}
          roles={rolesQ.data ?? []}
          initial={editing}
          onSubmit={(form) =>
            updateMut.mutate({
              id: editing.id,
              body: {
                email: form.email || null,
                full_name: form.full_name || null,
                is_active: form.is_active,
                role_codes: form.role_codes,
                page_acls: form.page_acls,
              },
            })
          }
          submitting={updateMut.isPending}
        />
      )}

      <Dialog open={!!resetResult} onOpenChange={() => setResetResult(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>密码已重置</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 text-sm">
            <p>用户 <span className="font-mono">{resetResult?.username}</span> 的新密码：</p>
            <pre className="p-3 bg-muted rounded font-mono break-all">
              {resetResult?.password}
            </pre>
            <p className="text-muted-foreground">此密码仅显示这一次，请立即妥善保存。</p>
          </div>
          <div className="flex justify-end pt-3">
            <Button onClick={() => setResetResult(null)}>关闭</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

interface FormState {
  username: string
  password: string
  email: string
  full_name: string
  is_active: boolean
  role_codes: string[]
  page_acls: string[]
}

function UserFormDialog(props: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  roles: { code: string; name: string }[]
  initial?: UserSummary
  onSubmit: (form: FormState) => void
  submitting?: boolean
}) {
  const [form, setForm] = useState<FormState>({
    username: props.initial?.username ?? "",
    password: "",
    email: props.initial?.email ?? "",
    full_name: props.initial?.full_name ?? "",
    is_active: props.initial?.is_active ?? true,
    role_codes: props.initial?.role_codes ?? [],
    page_acls: props.initial?.page_acls ?? [],
  })

  const isEdit = !!props.initial

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{props.title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="用户名"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            disabled={isEdit}
          />
          {!isEdit && (
            <Input
              type="password"
              placeholder="初始密码（至少 8 位）"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          )}
          <Input
            placeholder="邮箱（可选）"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <Input
            placeholder="姓名（可选）"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          />
          <div>
            <div className="text-sm mb-1">角色</div>
            <div className="flex flex-wrap gap-2">
              {props.roles.map((r) => {
                const checked = form.role_codes.includes(r.code)
                return (
                  <button
                    key={r.code}
                    type="button"
                    onClick={() =>
                      setForm({
                        ...form,
                        role_codes: checked
                          ? form.role_codes.filter((c) => c !== r.code)
                          : [...form.role_codes, r.code],
                      })
                    }
                    className={`px-2 py-1 text-xs rounded border ${
                      checked ? "bg-primary text-primary-foreground" : "bg-muted"
                    }`}
                  >
                    {r.name}
                  </button>
                )
              })}
            </div>
          </div>
          <div>
            <div className="text-sm mb-1">页面访问权限</div>
            <div className="flex flex-wrap gap-2">
              {ALL_PAGES.map((p) => {
                const checked = form.page_acls.includes(p)
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() =>
                      setForm({
                        ...form,
                        page_acls: checked
                          ? form.page_acls.filter((x) => x !== p)
                          : [...form.page_acls, p],
                      })
                    }
                    className={`px-2 py-1 text-xs rounded border ${
                      checked ? "bg-primary text-primary-foreground" : "bg-muted"
                    }`}
                  >
                    {p}
                  </button>
                )
              })}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            启用
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => props.onSubmit(form)}
            disabled={props.submitting}
          >
            {props.submitting ? "保存中..." : "保存"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
