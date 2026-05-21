import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import api from "@/api/client"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

interface AuditEntry {
  id: string
  actor_id: string | null
  actor_name: string | null
  action: string
  target_type: string | null
  target_id: string | null
  before: any
  after: any
  ip: string | null
  user_agent: string | null
  request_id: string | null
  created_at: string
}

export function AuditPage() {
  const [page, setPage] = useState(1)
  const [actionFilter, setActionFilter] = useState("")

  const q = useQuery({
    queryKey: ["audit", page, actionFilter],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, page_size: 50 }
      if (actionFilter) params.action = actionFilter
      const r = await api.get<{ total: number; page: number; items: AuditEntry[] }>(
        "/audit",
        { params },
      )
      return r.data
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">审计日志</h1>
        <span className="text-sm text-muted-foreground">
          {q.data?.total ?? 0} 条
        </span>
      </div>

      <div className="flex gap-2">
        <Input
          className="max-w-xs"
          placeholder="按操作筛选（如 project / task.delete）"
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.target.value)
            setPage(1)
          }}
        />
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground border-b">
              <tr>
                <th className="py-3 pl-4">时间</th>
                <th>操作者</th>
                <th>动作</th>
                <th>目标</th>
                <th>IP</th>
                <th className="pr-4">详情</th>
              </tr>
            </thead>
            <tbody>
              {q.isLoading && (
                <tr>
                  <td colSpan={6} className="p-4 text-center text-muted-foreground">
                    加载中…
                  </td>
                </tr>
              )}
              {q.data?.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-6 text-center text-muted-foreground text-sm">
                    暂无记录
                  </td>
                </tr>
              )}
              {q.data?.items.map((e) => (
                <tr key={e.id} className="border-t hover:bg-muted/30">
                  <td className="py-2 pl-4 text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(e.created_at).toLocaleString()}
                  </td>
                  <td className="text-xs">{e.actor_name ?? "system"}</td>
                  <td>
                    <Badge variant="outline" className="font-mono text-xs">
                      {e.action}
                    </Badge>
                  </td>
                  <td className="text-xs">
                    {e.target_type && (
                      <>
                        <span className="text-muted-foreground">{e.target_type}:</span>{" "}
                        <span className="font-mono">{e.target_id?.slice(0, 12)}</span>
                      </>
                    )}
                  </td>
                  <td className="text-xs text-muted-foreground font-mono">
                    {e.ip ?? "-"}
                  </td>
                  <td className="text-xs pr-4 max-w-[20rem] truncate">
                    {e.before && (
                      <span title={JSON.stringify(e.before, null, 2)} className="text-muted-foreground">
                        before: {JSON.stringify(e.before).slice(0, 80)}
                      </span>
                    )}
                    {e.after && (
                      <span title={JSON.stringify(e.after, null, 2)} className="text-emerald-700">
                        {" "}after: {JSON.stringify(e.after).slice(0, 80)}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          上一页
        </Button>
        <span className="text-sm text-muted-foreground">第 {page} 页</span>
        <Button
          size="sm"
          variant="outline"
          disabled={!q.data || q.data.items.length < 50}
          onClick={() => setPage((p) => p + 1)}
        >
          下一页
        </Button>
      </div>
    </div>
  )
}
