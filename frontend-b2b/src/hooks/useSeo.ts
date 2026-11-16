import { useEffect } from 'react'

/**
 * Lightweight SPA SEO hook for the public B2B portal.
 *
 * The portal is a static SPA on Cloudflare Pages (no server-side rendering),
 * so we update the document title + meta description + Open Graph tags on the
 * client for every route. Everything is written in the B2B wholesale context:
 * no retail pricing, only catalogue + request-a-quote language.
 */
export function useSeo(title: string, description?: string, image?: string) {
  useEffect(() => {
    document.title = title

    const setMeta = (key: string, value: string, property = false) => {
      const attr = property ? 'property' : 'name'
      let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`)
      if (!el) {
        el = document.createElement('meta')
        el.setAttribute(attr, key)
        document.head.appendChild(el)
      }
      el.setAttribute('content', value)
    }

    if (description) setMeta('description', description)
    setMeta('og:title', title, true)
    if (description) setMeta('og:description', description, true)
    if (image) setMeta('og:image', image, true)
  }, [title, description, image])
}
