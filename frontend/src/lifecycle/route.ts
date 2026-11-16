/**
 * 应用路由解析（ADR IDENTITY-002 §4）。
 *
 * URL 是页面选择的唯一来源；`App.tsx` 不再持有页面状态。
 * 保持单层路径 `/key` 与既有菜单 key 一一对应，同时支持 `/key/:param`
 * 供后续详情路由（`/products/:id`、`/candidates/:id`）使用。
 *
 * 生产 nginx console 配置已含 `try_files $uri $uri/ /index.html;`，BrowserRouter 可用。
 */

import { useLocation, useNavigate } from 'react-router-dom'

export interface AppRoute {
  /** 菜单 key（对齐 App.tsx 的 MenuKey） */
  key: string
  /** 第二段路径参数，例如 `/products/abc-123` → 'abc-123' */
  param: string | null
  navigate: (key: string) => void
}

const ROUTE_RE = /^\/([a-z0-9-]+)(?:\/([^/]+))?\/?$/

export function useAppRoute(): AppRoute {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const m = ROUTE_RE.exec(pathname)
  return {
    key: m?.[1] ?? 'dashboard',
    param: m?.[2] ?? null,
    navigate: (key) => navigate('/' + key),
  }
}
