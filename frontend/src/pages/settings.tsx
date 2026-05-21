import { useEffect, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { getSmtp, updateSmtp } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"

export function SettingsPage() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ["smtp"], queryFn: getSmtp })

  const [form, setForm] = useState({
    host: "",
    port: 587,
    username: "",
    password: "",
    from_addr: "",
    use_tls: true,
    is_enabled: false,
  })

  useEffect(() => {
    if (q.data) {
      setForm((f) => ({
        ...f,
        host: q.data.host ?? "",
        port: q.data.port,
        username: q.data.username ?? "",
        from_addr: q.data.from_addr ?? "",
        use_tls: q.data.use_tls,
        is_enabled: q.data.is_enabled,
        password: "",
      }))
    }
  }, [q.data])

  const save = useMutation({
    mutationFn: () =>
      updateSmtp({
        host: form.host,
        port: form.port,
        username: form.username || null,
        password: form.password || null,
        from_addr: form.from_addr,
        use_tls: form.use_tls,
        is_enabled: form.is_enabled,
      } as any),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["smtp"] })
      toast.success("SMTP 设置已保存")
    },
  })

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">系统设置</h1>
      <Card>
        <CardHeader><CardTitle className="text-base">邮件 (SMTP)</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-muted-foreground mb-1">SMTP 主机</div>
              <Input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} />
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">端口</div>
              <Input type="number" value={form.port}
                onChange={(e) => setForm({ ...form, port: parseInt(e.target.value || "0", 10) })} />
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">用户名</div>
              <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">密码（留空保留旧值）</div>
              <Input type="password" value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </div>
            <div className="col-span-2">
              <div className="text-xs text-muted-foreground mb-1">发件人地址</div>
              <Input value={form.from_addr}
                onChange={(e) => setForm({ ...form, from_addr: e.target.value })} />
            </div>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={form.use_tls}
                onChange={(e) => setForm({ ...form, use_tls: e.target.checked })} />
              使用 TLS
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={form.is_enabled}
                onChange={(e) => setForm({ ...form, is_enabled: e.target.checked })} />
              启用邮件通知
            </label>
          </div>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "保存中..." : "保存"}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
