import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { api, AgentProfile, setToken, clearToken } from './api/client'

interface AuthContextType {
  agent: AgentProfile | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refreshAgent: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [agent, setAgent] = useState<AgentProfile | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('b2b_token')
    if (token) {
      api.getMe()
        .then(setAgent)
        .catch(() => {
          clearToken()
        })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (email: string, password: string) => {
    const res = await api.login(email, password)
    setToken(res.access_token)
    setAgent(res.agent)
  }

  const logout = () => {
    clearToken()
    setAgent(null)
    window.location.href = '/login'
  }

  const refreshAgent = async () => {
    const me = await api.getMe()
    setAgent(me)
  }

  return (
    <AuthContext.Provider value={{ agent, loading, login, logout, refreshAgent }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
