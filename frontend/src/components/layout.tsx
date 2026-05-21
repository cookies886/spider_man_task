import { useEffect } from "react"
import { Outlet, NavLink, useNavigate } from "react-router-dom"
import { useAuthStore } from "@/store/auth"
import { fetchMe } from "@/api/client"
import { useTheme } from "@/components/theme-provider"
import {
  LayoutDashboard,
  FolderGit2,
  ListTodo,
  Server,
  Network,
  Box,
  KeyRound,
  LogOut,
  Bug,
  Users,
  Bell,
  HardDrive,
  ScrollText,
  Settings,
  Sun,
  Moon,
  Monitor,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface NavItem {
  to: string
  icon: typeof LayoutDashboard
  label: string
  pageKey: string
  superuserOnly?: boolean
}

const navItems: NavItem[] = [
  { to: "/dashboard", icon: LayoutDashboard, label: "仪表盘", pageKey: "dashboard" },
  { to: "/projects", icon: FolderGit2, label: "项目管理", pageKey: "projects" },
  { to: "/tasks", icon: ListTodo, label: "任务列表", pageKey: "tasks" },
  { to: "/environments", icon: Box, label: "环境管理", pageKey: "environments" },
  { to: "/python-versions", icon: Box, label: "Python 版本", pageKey: "python-versions" },
  { to: "/mirror-sources", icon: Box, label: "PyPI 镜像源", pageKey: "mirror-sources" },
  { to: "/env-vars", icon: KeyRound, label: "环境变量", pageKey: "env-vars" },
  { to: "/workers", icon: Server, label: "Worker 节点", pageKey: "workers" },
  { to: "/worker-groups", icon: Network, label: "节点组", pageKey: "worker-groups" },
  { to: "/notifications", icon: Bell, label: "消息通知", pageKey: "notifications" },
  { to: "/files", icon: HardDrive, label: "持久化文件", pageKey: "files" },
  { to: "/logs", icon: ScrollText, label: "日志管理", pageKey: "logs" },
  { to: "/users", icon: Users, label: "用户管理", pageKey: "users", superuserOnly: true },
  { to: "/settings", icon: Settings, label: "系统设置", pageKey: "settings", superuserOnly: true },
  { to: "/audit", icon: ScrollText, label: "审计日志", pageKey: "audit", superuserOnly: true },
]

function ThemeToggle() {
  const { theme, setTheme, resolved } = useTheme()
  const next = theme === "light" ? "dark" : theme === "dark" ? "system" : "light"
  const Icon = theme === "system" ? Monitor : resolved === "dark" ? Moon : Sun
  const label = theme === "system" ? "跟随系统" : resolved === "dark" ? "暗色" : "亮色"
  return (
    <button
      onClick={() => setTheme(next)}
      className="p-1.5 rounded hover:bg-sidebar-accent transition-colors"
      title={`主题：${label}（点击切换）`}
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}

export function Layout() {
  const { username, logout, me, setMe, hasPage } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (!me) {
      fetchMe().then(setMe).catch(() => {})
    }
  }, [me, setMe])

  const visibleItems = navItems.filter((item) => {
    if (item.superuserOnly && !me?.is_superuser) return false
    return hasPage(item.pageKey)
  })

  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  return (
    <div className="flex h-screen">
      <aside className="w-60 flex flex-col bg-sidebar text-sidebar-foreground">
        <div className="flex items-center gap-2 px-4 py-5 border-b border-sidebar-accent">
          <Bug className="h-6 w-6 text-primary" />
          <span className="text-lg font-bold">SpiderMan</span>
        </div>
        <nav className="flex-1 py-4 space-y-1 px-2">
          {visibleItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-sidebar-accent p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-sidebar-foreground/70 truncate">{username}</span>
            <div className="flex items-center gap-1">
              <ThemeToggle />
              <button
                onClick={handleLogout}
                className="p-1.5 rounded hover:bg-sidebar-accent transition-colors"
                title="退出登录"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-auto bg-background">
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
