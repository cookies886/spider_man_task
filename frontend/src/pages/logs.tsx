import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { toast } from "sonner"
import {
  listLogs,
  deleteLog,
  getLogRetention,
  setLogRetention,
  cleanupLogsNow,
} from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"

export function LogsPage() {
  const qc = useQueryClient()
  const logsQ = useQuery({ queryKey: ["logs"], queryFn: () => listLogs(200) })
  const retentionQ = useQuery({ queryKey: ["log-retention"], queryFn: getLogRetention })
  const [days, setDays] = useState("30")
  const [enabled, setEnabled] = useState(false)

  const updateRetention = useMutation({
    mutationFn: () => setLogRetention({ days_to_keep: parseInt(days, 10), is_enabled: enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["log-retention"] })
      toast.success("保留策略已保存")
    },
  })
  const cleanupNow = useMutation({
    mutationFn: cleanupLogsNow,
    onSuccess: (data) => {
      toast.success(`已清理 ${data.deleted} 个超过 ${data.older_than_days} 天的日志`)
      qc.invalidateQueries({ queryKey: ["logs"] })
    },
  })
  const del = useMutation({
    mutationFn: deleteLog,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["logs"] }),
  })

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">日志管理</h1>
      <Card>
        <CardHeader><CardTitle className="text-base">自动清理</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-end gap-3 text-sm">
            <div>
              <div className="mb-1 text-muted-foreground">保留天数</div>
              <Input className="w-24" value={days} onChange={(e) => setDays(e.target.value)} />
            </div>
            <label className="flex items-center gap-2 mb-2">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              启用
            </label>
            <Button size="sm" onClick={() => updateRetention.mutate()}>保存</Button>
            <Button size="sm" variant="outline" onClick={() => cleanupNow.mutate()}>立即清理</Button>
            <span className="text-xs text-muted-foreground">
              当前：{retentionQ.data?.days_to_keep}d / {retentionQ.data?.is_enabled ? "启用" : "禁用"} ·
              上次：{retentionQ.data?.last_run_at ? new Date(retentionQ.data.last_run_at).toLocaleString() : "未运行"}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">日志文件</CardTitle></CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-2">Run ID</th>
                <th>文件名</th>
                <th>大小</th>
                <th>创建时间</th>
                <th className="text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {logsQ.data?.map((l) => (
                <tr key={l.run_id} className="border-t">
                  <td className="py-2 font-mono text-xs">{l.run_id.slice(0, 8)}</td>
                  <td className="font-mono text-xs">{l.file_name}</td>
                  <td className="text-xs">{l.size}B</td>
                  <td className="text-xs text-muted-foreground">{new Date(l.created_at).toLocaleString()}</td>
                  <td className="text-right space-x-1">
                    <a href={`/api/v1/tasks/runs/${l.run_id}/log`}
                      className="text-xs underline text-muted-foreground">下载</a>
                    <Button size="sm" variant="ghost" className="text-destructive"
                      onClick={() => del.mutate(l.run_id)}>删除</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}
