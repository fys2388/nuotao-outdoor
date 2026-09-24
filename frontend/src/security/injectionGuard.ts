/**
 * BUG #10: 前端运行时防御
 *
 * 目标：彻底拦截第三方浏览器扩展（1688/选品通）在页面上注入的 iframe / 未知 script /
 *      隐藏元素。CSP 是主防线，这里是双保险。
 *
 * 核心策略：admin 页面不需要任何 iframe，全部移除。
 * 检测策略：
 * 1. MutationObserver 监听 <head> 和 <body> 的子元素插入
 * 2. 检测所有 iframe → 立即移除 + 上报（不区分来源）
 * 3. 检测外部 src 的 script 且 src 不是同源 → 立即移除 + 上报
 * 4. 检测 chrome-extension: 源的 link 元素 → 立即移除 + 上报
 * 5. 每 2 秒定时扫描（兜底 MutationObserver 漏过的场景）
 *
 * 上报：console.error + window.onerror 通道
 */

const ALLOWED_ORIGIN = location.origin

type InjectionReport = {
  kind: 'iframe-foreign' | 'script-foreign' | 'element-unknown'
  tag: string
  src?: string
  hostname?: string
  parentTag: string
}

const reports: InjectionReport[] = []

function report(evt: InjectionReport) {
  reports.push(evt)
  console.error('[injection-defense] removed foreign element:', evt)
  if (reports.length > 100) reports.shift()
}

function isForeignUrl(href: string | null | undefined): boolean {
  if (!href) return false
  if (href.startsWith('chrome-extension:') || href.startsWith('moz-extension:')) return true
  if (href.startsWith('javascript:') || href.startsWith('data:')) return true
  try {
    const u = new URL(href, location.href)
    return u.origin !== ALLOWED_ORIGIN
  } catch {
    return true
  }
}

/**
 * 递归清理 DOM 子树中的所有非法元素。
 * iframe：全部移除（admin 页面不需要 iframe）。
 * script：只移除外部 src 的。
 * link：只移除 chrome-extension 源的。
 */
function scrubNode(root: ParentNode) {
  // 1. iframe — 全部移除
  root.querySelectorAll('iframe').forEach((iframe) => {
    const src = iframe.getAttribute('src') || iframe.src || ''
    const srcdoc = iframe.getAttribute('srcdoc') || ''
    const name = iframe.getAttribute('name') || ''
    const desc = src || (srcdoc ? '[srcdoc]' : name ? `[name=${name}]` : '[no-src]')
    report({ kind: 'iframe-foreign', tag: 'iframe', src: desc, parentTag: iframe.parentElement?.tagName || 'BODY' })
    iframe.remove()
  })

  // 2. script — 移除外部 src
  root.querySelectorAll('script').forEach((script) => {
    const src = script.getAttribute('src')
    if (src && isForeignUrl(src)) {
      report({ kind: 'script-foreign', tag: 'script', src, parentTag: script.parentElement?.tagName || 'HEAD' })
      script.remove()
    }
  })

  // 3. link — 移除 chrome-extension 源
  root.querySelectorAll('link[href]').forEach((link) => {
    const href = link.getAttribute('href')
    if (href && href.startsWith('chrome-extension:')) {
      report({ kind: 'element-unknown', tag: 'link', src: href, parentTag: link.parentElement?.tagName || 'HEAD' })
      link.remove()
    }
  })
}

export function installInjectionDefense() {
  if (typeof window === 'undefined') return
  if ((window as any).__INJECTION_DEFENSE__) return
  ;(window as any).__INJECTION_DEFENSE__ = true

  // 初始扫描一次
  scrubNode(document.head)
  scrubNode(document.body)

  // MutationObserver: 捕获新插入的子节点
  const obs = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue
        const el = node as Element
        const tag = el.tagName.toLowerCase()

        if (tag === 'iframe') {
          // Admin 页面不需要任何 iframe，全部移除
          const src = el.getAttribute('src') || ''
          const srcdoc = el.getAttribute('srcdoc') || ''
          const name = el.getAttribute('name') || ''
          const desc = src || (srcdoc ? '[srcdoc]' : name ? `[name=${name}]` : '[no-src]')
          report({ kind: 'iframe-foreign', tag, src: desc, parentTag: el.parentElement?.tagName || 'UNKNOWN' })
          el.remove()
        } else if (tag === 'script') {
          const src = el.getAttribute('src')
          if (src && isForeignUrl(src)) {
            report({ kind: 'script-foreign', tag, src, parentTag: el.parentElement?.tagName || 'UNKNOWN' })
            el.remove()
          }
        } else if (
          el.getAttribute?.('src')?.startsWith('chrome-extension:') ||
          el.getAttribute?.('href')?.startsWith('chrome-extension:')
        ) {
          report({ kind: 'element-unknown', tag, src: el.getAttribute('src') || el.getAttribute('href') || '', parentTag: el.parentElement?.tagName || 'UNKNOWN' })
          el.remove()
        }

        // 也扫描新插入元素的子节点
        if (el.nodeType === Node.ELEMENT_NODE) {
          scrubNode(el)
        }
      }
    }
  })

  obs.observe(document.head, { childList: true, subtree: true })
  obs.observe(document.body, { childList: true, subtree: true })

  // 定时兜底（每 2 秒扫一次）
  window.setInterval(() => {
    scrubNode(document.head)
    scrubNode(document.body)
  }, 2000)

  // 通过 window 暴露最近报告，供审计工具读取
  Object.defineProperty(window, '__injectionDefenseReports', {
    get: () => reports.slice(-50),
    configurable: true,
  })
}
