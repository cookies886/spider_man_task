import { useRef, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  listPersistentFiles,
  makePersistentFolder,
  uploadPersistentFile,
  deletePersistentFile,
} from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import {
  Folder,
  FileText,
  ChevronLeft,
  Upload,
  FolderPlus,
  Copy,
  FolderUp,
  X,
} from "lucide-react"

interface QueueItem {
  id: string
  name: string
  size: number
  status: "pending" | "uploading" | "done" | "error"
  error?: string
  /** Resolved destination subpath (for tooltip in queue UI). */
  dest: string
}

export function FilesPage() {
  const qc = useQueryClient()
  const [path, setPath] = useState("")
  const [queue, setQueue] = useState<QueueItem[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)

  const filesQ = useQuery({
    queryKey: ["pfiles", path],
    queryFn: () => listPersistentFiles(path),
  })

  const mkdir = useMutation({
    mutationFn: makePersistentFolder,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pfiles", path] })
      toast.success("文件夹已创建")
    },
  })
  const del = useMutation({
    mutationFn: deletePersistentFile,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pfiles", path] }),
  })

  const goUp = () => {
    const parts = path.split("/").filter(Boolean)
    parts.pop()
    setPath("/" + parts.join("/"))
  }

  const enqueueAndUpload = async (files: FileList | File[], asFolder: boolean) => {
    const arr = Array.from(files)
    if (arr.length === 0) return

    // Build queue entries with resolved destination paths
    const items: QueueItem[] = arr.map((f) => {
      const rel = (f as any).webkitRelativePath as string | undefined
      const subPath = asFolder && rel ? rel : f.name
      const dest = `${path}/${subPath}`.replace(/\/+/g, "/")
      return {
        id: `${Date.now()}-${Math.random()}`,
        name: rel || f.name,
        size: f.size,
        status: "pending",
        dest,
      }
    })
    setQueue((q) => [...q, ...items])

    // Upload sequentially (parallel uploads of dozens of files can overwhelm
    // small servers; sequential is safer + progress is clearer).
    let okCount = 0
    let errCount = 0
    for (let i = 0; i < arr.length; i++) {
      const f = arr[i]
      const item = items[i]
      setQueue((q) =>
        q.map((x) => (x.id === item.id ? { ...x, status: "uploading" } : x))
      )
      try {
        // Parent directory of the file (everything before the leaf filename)
        const parentDir = item.dest.replace(/\/[^/]+$/, "") || "/"
        await uploadPersistentFile(parentDir, f)
        setQueue((q) =>
          q.map((x) => (x.id === item.id ? { ...x, status: "done" } : x))
        )
        okCount++
      } catch (e: any) {
        const msg = e?.response?.data?.detail || e?.message || "失败"
        setQueue((q) =>
          q.map((x) =>
            x.id === item.id ? { ...x, status: "error", error: msg } : x
          )
        )
        errCount++
      }
    }

    qc.invalidateQueries({ queryKey: ["pfiles", path] })
    if (errCount === 0) {
      toast.success(`已上传 ${okCount} 个文件`)
    } else {
      toast.error(`完成 ${okCount}，失败 ${errCount}`)
    }
  }

  const onFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    enqueueAndUpload(e.target.files, false)
    e.target.value = ""
  }
  const onFolderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    enqueueAndUpload(e.target.files, true)
    e.target.value = ""
  }

  // Drag-and-drop support
  const [dragOver, setDragOver] = useState(false)
  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const items = e.dataTransfer.items
    if (!items) return
    const collected: File[] = []
    const traverse = async (entry: any, prefix: string) => {
      if (entry.isFile) {
        const f: File = await new Promise((resolve) => entry.file(resolve))
        // Synthesize webkitRelativePath so downstream logic works the same
        Object.defineProperty(f, "webkitRelativePath", {
          value: prefix + f.name,
          configurable: true,
        })
        collected.push(f)
      } else if (entry.isDirectory) {
        const reader = entry.createReader()
        const entries: any[] = await new Promise((resolve) =>
          reader.readEntries(resolve)
        )
        for (const child of entries) {
          await traverse(child, `${prefix}${entry.name}/`)
        }
      }
    }
    const promises: Promise<void>[] = []
    for (let i = 0; i < items.length; i++) {
      const it = items[i]
      const entry = (it as any).webkitGetAsEntry?.()
      if (entry) promises.push(traverse(entry, ""))
    }
    await Promise.all(promises)
    if (collected.length > 0) {
      enqueueAndUpload(collected, true)
    }
  }

  const clearDoneQueue = () =>
    setQueue((q) => q.filter((x) => x.status !== "done"))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">持久化文件</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const name = prompt("文件夹名")
              if (name) mkdir.mutate(`${path}/${name}`.replace("//", "/"))
            }}
          >
            <FolderPlus className="h-4 w-4 mr-1" /> 新建文件夹
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="h-4 w-4 mr-1" /> 上传文件
          </Button>
          <Button size="sm" onClick={() => folderInputRef.current?.click()}>
            <FolderUp className="h-4 w-4 mr-1" /> 上传文件夹
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={onFilesChange}
          />
          <input
            ref={folderInputRef}
            type="file"
            multiple
            // @ts-expect-error — non-standard but widely supported attrs for dir-picking
            webkitdirectory=""
            directory=""
            className="hidden"
            onChange={onFolderChange}
          />
        </div>
      </div>

      <Card
        className={dragOver ? "ring-2 ring-primary" : ""}
        onDragEnter={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            {path && (
              <Button size="sm" variant="ghost" onClick={goUp}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
            )}
            <span className="font-mono">{path || "/"}</span>
            <span className="text-xs text-muted-foreground ml-auto">
              拖拽文件 / 文件夹到此区域上传
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!filesQ.data?.length ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              空目录（拖拽上传 / 点击右上"上传文件夹"）
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-muted-foreground">
                <tr>
                  <th className="py-2">名称</th>
                  <th>大小</th>
                  <th>修改时间</th>
                  <th className="text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filesQ.data.map((f) => (
                  <tr key={f.path} className="border-t">
                    <td className="py-2">
                      <button
                        className="flex items-center gap-2 hover:text-primary"
                        onClick={() => f.is_dir && setPath(f.path)}
                      >
                        {f.is_dir ? (
                          <Folder className="h-4 w-4 text-amber-600" />
                        ) : (
                          <FileText className="h-4 w-4 text-muted-foreground" />
                        )}
                        <span>{f.name}</span>
                      </button>
                    </td>
                    <td className="text-xs text-muted-foreground">
                      {f.is_dir ? "-" : `${f.size}B`}
                    </td>
                    <td className="text-xs text-muted-foreground">
                      {new Date(f.mtime).toLocaleString()}
                    </td>
                    <td className="text-right space-x-1">
                      {!f.is_dir && (
                        <>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              navigator.clipboard.writeText(
                                `/app/../static/persistentMappedAddress${f.path}`
                              )
                              toast.success("路径已复制")
                            }}
                          >
                            <Copy className="h-3 w-3" />
                          </Button>
                          <a
                            href={`/api/v1/files/download?path=${encodeURIComponent(f.path)}`}
                            className="text-xs underline text-muted-foreground"
                          >
                            下载
                          </a>
                        </>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive"
                        onClick={() => {
                          if (confirm(`删除 ${f.name}?`)) del.mutate(f.path)
                        }}
                      >
                        删除
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {queue.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center justify-between">
              <span>上传队列 ({queue.length})</span>
              <Button size="sm" variant="ghost" onClick={clearDoneQueue}>
                清除已完成
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 max-h-48 overflow-y-auto text-xs">
              {queue.map((q) => (
                <li
                  key={q.id}
                  className="flex items-center gap-2 border-b py-1"
                  title={q.dest}
                >
                  <span className="flex-1 truncate font-mono">{q.name}</span>
                  <span className="text-muted-foreground">{q.size}B</span>
                  <span
                    className={
                      q.status === "done"
                        ? "text-green-600"
                        : q.status === "error"
                        ? "text-destructive"
                        : q.status === "uploading"
                        ? "text-blue-600"
                        : "text-muted-foreground"
                    }
                  >
                    {q.status === "done"
                      ? "✓"
                      : q.status === "error"
                      ? `✗ ${q.error}`
                      : q.status === "uploading"
                      ? "上传中..."
                      : "等待"}
                  </span>
                  {q.status !== "uploading" && (
                    <button
                      onClick={() => setQueue((qs) => qs.filter((x) => x.id !== q.id))}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
