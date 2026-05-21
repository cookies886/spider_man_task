import { useState, useEffect } from "react"
import { useParams, Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import Editor from "@monaco-editor/react"
import {
  getProject,
  listProjectFiles,
  readProjectFile,
  writeProjectFile,
  triggerGitSync,
  type ProjectFileEntry,
} from "@/api/client"
import { useAuthStore } from "@/store/auth"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { ChevronRight, ChevronDown, FileText, Folder } from "lucide-react"
import { CollaboratorsCard } from "@/components/collaborators-card"

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const qc = useQueryClient()
  const me = useAuthStore((s) => s.me)

  const projectQ = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId!),
    enabled: !!projectId,
  })

  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [content, setContent] = useState("")
  const [savedContent, setSavedContent] = useState("")
  const [loadingFile, setLoadingFile] = useState(false)
  const [err, setErr] = useState("")

  const syncMut = useMutation({
    mutationFn: () => triggerGitSync(projectId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", projectId] }),
  })

  const saveMut = useMutation({
    mutationFn: () => writeProjectFile(projectId!, selectedPath!, content),
    onSuccess: () => {
      setSavedContent(content)
      qc.invalidateQueries({ queryKey: ["project", projectId] })
    },
  })

  useEffect(() => {
    if (!selectedPath || !projectId) return
    setLoadingFile(true)
    setErr("")
    readProjectFile(projectId, selectedPath)
      .then((d) => {
        setContent(d.content)
        setSavedContent(d.content)
      })
      .catch((e) => setErr(e?.response?.data?.detail || String(e)))
      .finally(() => setLoadingFile(false))
  }, [selectedPath, projectId])

  if (!projectId) return null
  const dirty = content !== savedContent

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/projects" className="text-sm text-muted-foreground hover:underline">
            ← 项目列表
          </Link>
          <h1 className="text-2xl font-semibold mt-1">
            {projectQ.data?.name ?? "..."}
          </h1>
        </div>
        {projectQ.data?.source_type === "git" && (
          <Button onClick={() => syncMut.mutate()} disabled={syncMut.isPending}>
            {syncMut.isPending ? "拉取中..." : "立即拉取 Git"}
          </Button>
        )}
      </div>

      {projectQ.data && (
        <CollaboratorsCard
          resource="project"
          resourceId={projectId}
          canManage={
            !!me?.is_superuser ||
            (!!me?.id && me.id === projectQ.data.owner_id)
          }
        />
      )}

      {projectQ.data?.git && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Git 仓库</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-1">
            <div>
              URL: <span className="font-mono">{projectQ.data.git.url}</span>
            </div>
            <div>分支: {projectQ.data.git.branch}</div>
            <div>
              最后同步:{" "}
              {projectQ.data.git.last_sync_at
                ? new Date(projectQ.data.git.last_sync_at).toLocaleString()
                : "尚未同步"}
            </div>
            <div>
              最后提交:{" "}
              <span className="font-mono">
                {projectQ.data.git.last_commit?.slice(0, 12) || "-"}
              </span>
            </div>
            {projectQ.data.git.last_error && (
              <div className="text-destructive">
                错误：{projectQ.data.git.last_error}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">代码浏览</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-[18rem_1fr] gap-3 h-[60vh]">
            <div className="border rounded p-2 overflow-auto">
              <FileTree
                projectId={projectId}
                selected={selectedPath}
                onSelect={setSelectedPath}
              />
            </div>
            <div className="border rounded flex flex-col">
              <div className="border-b p-2 flex items-center justify-between text-sm">
                <span className="font-mono">{selectedPath ?? "请选择文件"}</span>
                {selectedPath && (
                  <Button
                    size="sm"
                    onClick={() => saveMut.mutate()}
                    disabled={!dirty || saveMut.isPending}
                  >
                    {saveMut.isPending ? "保存中..." : dirty ? "保存" : "已保存"}
                  </Button>
                )}
              </div>
              <div className="flex-1">
                {loadingFile ? (
                  <div className="p-4 text-muted-foreground">加载中...</div>
                ) : err ? (
                  <div className="p-4 text-destructive">{err}</div>
                ) : selectedPath ? (
                  <Editor
                    value={content}
                    onChange={(v) => setContent(v ?? "")}
                    language={detectLang(selectedPath)}
                    theme="vs-dark"
                    options={{
                      fontSize: 13,
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                    }}
                  />
                ) : (
                  <div className="p-4 text-muted-foreground">
                    点击左侧文件以查看 / 编辑
                  </div>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function detectLang(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase()
  const map: Record<string, string> = {
    py: "python",
    js: "javascript",
    ts: "typescript",
    tsx: "typescript",
    jsx: "javascript",
    json: "json",
    yml: "yaml",
    yaml: "yaml",
    md: "markdown",
    html: "html",
    css: "css",
    sh: "shell",
    sql: "sql",
    toml: "toml",
    txt: "plaintext",
  }
  return ext ? map[ext] ?? "plaintext" : "plaintext"
}

function FileTree(props: {
  projectId: string
  selected: string | null
  onSelect: (path: string) => void
}) {
  return <FileTreeNode {...props} path="" depth={0} initiallyOpen />
}

function FileTreeNode(props: {
  projectId: string
  path: string
  depth: number
  selected: string | null
  onSelect: (path: string) => void
  initiallyOpen?: boolean
}) {
  const open = props.initiallyOpen ?? true
  const q = useQuery({
    queryKey: ["files", props.projectId, props.path],
    queryFn: () => listProjectFiles(props.projectId, props.path),
    enabled: open,
  })

  return (
    <ul className="text-sm">
      {q.data?.map((entry) => (
        <FileTreeRow
          key={entry.path}
          entry={entry}
          projectId={props.projectId}
          depth={props.depth}
          selected={props.selected}
          onSelect={props.onSelect}
        />
      ))}
    </ul>
  )
}

function FileTreeRow(props: {
  entry: ProjectFileEntry
  projectId: string
  depth: number
  selected: string | null
  onSelect: (path: string) => void
}) {
  const [open, setOpen] = useState(false)
  const indent = { paddingLeft: `${props.depth * 0.75}rem` }
  if (props.entry.is_dir) {
    return (
      <li>
        <button
          type="button"
          className="w-full text-left flex items-center gap-1 px-1 py-0.5 hover:bg-muted rounded"
          style={indent}
          onClick={() => setOpen(!open)}
        >
          {open ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          <Folder className="h-3.5 w-3.5 text-amber-600" />
          <span>{props.entry.name}</span>
        </button>
        {open && (
          <FileTreeNode
            projectId={props.projectId}
            path={props.entry.path}
            depth={props.depth + 1}
            selected={props.selected}
            onSelect={props.onSelect}
          />
        )}
      </li>
    )
  }
  const isSelected = props.selected === props.entry.path
  return (
    <li>
      <button
        type="button"
        className={`w-full text-left flex items-center gap-1 px-1 py-0.5 rounded ${
          isSelected ? "bg-primary/10 text-primary" : "hover:bg-muted"
        }`}
        style={indent}
        onClick={() => props.onSelect(props.entry.path)}
      >
        <span className="w-3" />
        <FileText className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="truncate">{props.entry.name}</span>
      </button>
    </li>
  )
}
