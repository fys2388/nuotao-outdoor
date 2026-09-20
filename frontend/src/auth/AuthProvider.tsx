import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import {
  ADMIN_REFRESH_TOKEN_KEY,
  API_BASE,
  ApiError,
  clearAuthTokens,
  getAccessToken,
  request,
  setAuthTokens,
} from '../api/client'

export interface AdminUser {
  id: string
  username: string
  email: string
  role: string
  is_active: boolean
}

interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: AdminUser
}

interface AuthContextValue {
  user: AdminUser | null
  loading: boolean
  authenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshUser = async () => {
    if (!getAccessToken()) {
      setUser(null)
      setLoading(false)
      return
    }

    try {
      const currentUser = await request<AdminUser>('/auth/me', { timeoutMs: 10000 })
      setUser(currentUser)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearAuthTokens()
      }
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshUser()
  }, [])

  const login = async (username: string, password: string) => {
    const form = new URLSearchParams()
    form.set('username', username)
    form.set('password', password)

    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    })
    const payload = await response.json().catch(() => null)

    if (!response.ok) {
      const detail =
        payload && typeof payload === 'object' && 'detail' in payload
          ? String((payload as { detail: unknown }).detail)
          : '登录失败'
      throw new ApiError(detail, response.status, payload)
    }

    const result = payload as LoginResponse
    setAuthTokens(result.access_token, result.refresh_token)
    localStorage.setItem(ADMIN_REFRESH_TOKEN_KEY, result.refresh_token)
    setUser(result.user)
  }

  const logout = () => {
    clearAuthTokens()
    setUser(null)
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      authenticated: Boolean(user && getAccessToken()),
      login,
      logout,
      refreshUser,
    }),
    [user, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return context
}

export function RequireAuth({ children }: { children?: ReactNode }) {
  const { authenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="route-loading">
        <span className="route-loading__mark" />
        <span>正在验证登录状态</span>
      </div>
    )
  }

  if (!authenticated) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  return children ? <>{children}</> : <Outlet />
}
