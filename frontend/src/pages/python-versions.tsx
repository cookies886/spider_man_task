import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  listPyVers,
  createPyVer,
  deletePyVer,
  setDefaultPyVer,
  type PyVerStatus,
} from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

const STATUS_COLOR: Record<PyVerStatus, string> = {
  downloading: "text-blue-600",
  building: "text-blue-600",
  ready: "text-green-600",
  failed: "text-destructive",
}

const SUGGESTED_VERSIONS = [
  { version: "3.13.3", url: "https://www.python.org/ftp/python/3.13.3/Python-3.13.3.tar.xz" },
  { version: "3.12.10", url: "https://www.python.org/ftp/python/3.12.10/Python-3.12.10.tar.xz" },
  { version: "3.11.12", url: "https://www.python.org/ftp/python/3.11.12/Python-3.11.12.tar.xz" },
  { version: "3.10.17", url: "https://www.python.org/ftp/python/3.10.17/Python-3.10.17.tar.xz" },
  { version: "3.9.22", url: "https://www.python.org/ftp/python/3.9.22/Python-3.9.22.tar.xz" },
]

export function PythonVersionsPage() {
  const qc = useQueryClient()
  const versionsQ = useQuery({
    queryKey: ["python-versions"],
    queryFn: listPyVers,
    refetchInterval: 5000,
  })
  const [createOpen, setCreateOpen] = useState(false)

  const createMut = useMutation({
    mutationFn: ({ version, url }: { version: string; url: string }) =>
      createPyVer(version, url),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["python-versions"] })
      setCreateOpen(false)
    },
  })
  const deleteMut = useMutation({
    mutationFn: deletePyVer,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["python-versions"] }),
  })
  const setDefaultMut = useMutation({
    mutationFn: setDefaultPyVer,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["python-versions"] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Python 版本管理</h1>
        <Button onClick={() => setCreateOpen(true)}>添加版本</Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>已安装版本</CardTitle>
        </CardHeader>
        <CardContent>
          {versionsQ.data?.length ? (
            <table className="w-full text-sm">
              <thead className="text-left text-muted-foreground">
                <tr>
                  <th className="py-2">版本</th>
                  <th>状态</th>
                  <th>安装路径</th>
                  <th>默认</th>
                  <th className="text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {versionsQ.data.map((v) => (
                  <tr key={v.id} className="border-t">
                    <td className="py-2 font-mono">{v.version}</td>
                    <td className={`text-xs font-medium ${STATUS_COLOR[v.status]}`}>
                      {v.status}
                      {v.error_msg && (
                        <span className="ml-2 text-xs text-destructive">{v.error_msg}</span>
                      )}
                    </td>
                    <td className="font-mono text-xs text-muted-foreground">
                      {v.install_path ?? "-"}
                    </td>
                    <td>{v.is_default && <span className="text-primary">★</span>}</td>
                    <td className="text-right space-x-1">
                      {v.status === "ready" && !v.is_default && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setDefaultMut.mutate(v.id)}
                        >
                          设为默认
                        </Button>
                      )}
                      <a
                        href={`/api/v1/python-versions/${v.id}/log`}
                        className="text-xs underline text-muted-foreground"
                      >
                        构建日志
                      </a>
                      {!v.is_default && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive"
                          onClick={() => {
                            if (confirm(`删除 ${v.version}?`)) deleteMut.mutate(v.id)
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
          ) : (
            <p className="text-sm text-muted-foreground">还没有添加 Python 版本</p>
          )}
        </CardContent>
      </Card>

      <CreatePyVerDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSubmit={(v, u) => createMut.mutate({ version: v, url: u })}
        submitting={createMut.isPending}
      />
    </div>
  )
}

function CreatePyVerDialog(props: {
  open: boolean
  onOpenChange: (o: boolean) => void
  onSubmit: (version: string, url: string) => void
  submitting?: boolean
}) {
  const [version, setVersion] = useState("")
  const [url, setUrl] = useState("")

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>添加 Python 版本</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="版本号（如 3.12.10）"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
          />
          <Input
            placeholder="Tarball URL（.tar.xz）"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <div className="text-xs text-muted-foreground">
            常用版本：
            <ul className="space-y-0.5 mt-1">
              {SUGGESTED_VERSIONS.map((v) => (
                <li key={v.version}>
                  <button
                    type="button"
                    className="text-primary hover:underline"
                    onClick={() => {
                      setVersion(v.version)
                      setUrl(v.url)
                    }}
                  >
                    {v.version}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <p className="text-xs text-amber-600">
            注意：Python 源码编译耗时较长（通常 10-30 分钟），请耐心等待。
          </p>
        </div>
        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => props.onSubmit(version, url)}
            disabled={props.submitting || !version || !url}
          >
            {props.submitting ? "提交中..." : "添加"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
