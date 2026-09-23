/**
 * BUG #10: 前端运行时防御
 *
 * 目标：拦截第三方浏览器扩展（1688/选品通）在页面上注入的 iframe / 未知 script /
 *      隐藏元素。CSP 是主防线，这里是双保险。
 *
 * 检测策略：
 * 1. MutationObserver 监听 <head> 和 <body> 的直接子元素插入
 * 2. 检测 chrome-extension: 源 iframe → 立即移除 + 上报
 * 3. 检测外部 src 的 script 且 src 不是同源 → 立即移除 + 上报
 * 4. 每 3 秒定时扫描（兜底 MutationObserver 漏过的场景）
 *
 * 上报：console.error + window.onerror 通道（后端可通过审计表收集，如已接入）
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
  // 保留最近 100 条，防止内存膨胀
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

function scrubNode(root: ParentNode) {
  // iframe with foreign src
  root.querySelectorAll('iframe').forEach((iframe) => {
    const src = iframe.getAttribute('src') || iframe.src || ''
    const srcdoc = iframe.getAttribute('srcdoc') || ''
    if (isForeignUrl(src) || src.startsWith('javascript:') || (srcdoc && srcdoc.length > 0)) {
      report({ kind: 'iframe-foreign', tag: 'iframe', src: src || '[srcdoc]', parentTag: iframe.parentElement?.tagName || 'BODY' })
      iframe.remove()
    }
  })

  // script with foreign src (not inlined)
  root.querySelectorAll('script').forEach((script) => {
    const src = script.getAttribute('src')
    if (src && isForeignUrl(src)) {
      report({ kind: 'script-foreign', tag: 'script', src, parentTag: script.parentElement?.tagName || 'HEAD' })
      script.remove()
    }
  })

  // Link with foreign href that has rel=prefetch/stylesheet pointing to chrome-extension
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

        // 直接在 head 里插入的 iframe/script 是最可疑的
        if (tag === 'iframe') {
          const src = el.getAttribute('src') || ''
          const srcdoc = el.getAttribute('srcdoc') || ''
          if (isForeignUrl(src) || srcdoc) {
            report({ kind: 'iframe-foreign', tag, src: src || '[srcdoc]', parentTag: el.parentElement?.tagName || 'UNKNOWN' })
            el.remove()
          }
        } else if (tag === 'script') {
          const src = el.getAttribute('src')
          if (src && isForeignUrl(src)) {
            report({ kind: 'script-foreign', tag, src, parentTag: el.parentElement?.tagName || 'UNKNOWN' })
            el.remove()
          }
        } else if (el.getAttribute?.('src')?.startsWith('chrome-extension:') || el.getAttribute?.('href')?.startsWith('chrome-extension:')) {
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

  // 定时兜底（每 3 秒扫一次）
  window.setInterval(() => {
    scrubNode(document.head)
    scrubNode(document.body)
  }, 3000)

  // 通过 window 暴露最近报告，供审计工具读取
  Object.defineProperty(window, '__injectionDefenseReports', {
    get: () => reports.slice(-50),
    configurable: true,
  })
}
