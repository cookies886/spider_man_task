import { create } from "zustand"

export interface Me {
  id: string
  username: string
  full_name: string | null
  email: string | null
  is_superuser: boolean
  must_change_password: boolean
  permissions: string[]
  page_acls: string[]
  last_login_at: string | null
}

interface AuthState {
  isAuthenticated: boolean
  username: string | null
  me: Me | null
  login: (accessToken: string, refreshToken: string, username: string) => void
  setMe: (me: Me) => void
  logout: () => void
  hasPage: (key: string) => boolean
  hasPerm: (code: string) => boolean
}

const cachedMe = (() => {
  const raw = localStorage.getItem("me")
  return raw ? (JSON.parse(raw) as Me) : null
})()

export const useAuthStore = create<AuthState>((set, get) => ({
  isAuthenticated: !!localStorage.getItem("access_token"),
  username: localStorage.getItem("username"),
  me: cachedMe,
  login: (accessToken, refreshToken, username) => {
    localStorage.setItem("access_token", accessToken)
    localStorage.setItem("refresh_token", refreshToken)
    localStorage.setItem("username", username)
    set({ isAuthenticated: true, username })
  },
  setMe: (me) => {
    localStorage.setItem("me", JSON.stringify(me))
    set({ me })
  },
  logout: () => {
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
    localStorage.removeItem("username")
    localStorage.removeItem("me")
    set({ isAuthenticated: false, username: null, me: null })
  },
  hasPage: (key) => {
    const me = get().me
    if (!me) return false
    if (me.is_superuser) return true
    return me.page_acls.includes(key)
  },
  hasPerm: (code) => {
    const me = get().me
    if (!me) return false
    if (me.is_superuser) return true
    return me.permissions.includes(code)
  },
}))
