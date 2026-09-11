/** 全局导航工具（history 模式） */
export function navigateTo(path: string) {
  const url = path.startsWith('/') ? path : '/' + path
  window.history.pushState({}, '', url)
  window.dispatchEvent(new PopStateEvent('popstate'))
}
