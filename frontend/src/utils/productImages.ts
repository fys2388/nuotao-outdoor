/**
 * Single source of truth for resolving a product's images on the client.
 *
 * The 商品主数据 list used to carry its own inline resolver that read only
 * `meta.media.images`, `meta.media.gallery_images` and `meta.images` — but the
 * WooCommerce sync also writes `media.main_image` (singular) and the sourcing
 * pipeline writes `meta.main_images`, which `build_wc_payload` prefers. Six
 * products therefore had images the UI could not see and rendered a placeholder.
 *
 * Any component that renders a product image should use this so the list, the
 * detail drawer and the publish preview never disagree.
 */

type AnyRecord = Record<string, any>

const HTTP = /^https?:\/\//i

/** Normalise one value into a list of http(s) URLs. */
function pickUrls(value: unknown): string[] {
  if (!value) return []
  if (typeof value === 'string') return HTTP.test(value) ? [value] : []
  if (Array.isArray(value)) {
    const out: string[] = []
    for (const item of value) out.push(...pickUrls(item))
    return out
  }
  if (typeof value === 'object') {
    const record = value as AnyRecord
    return pickUrls(record.url ?? record.src ?? record.image ?? record.image_url)
  }
  return []
}

/**
 * Every usable image URL for a product, cover first, de-duplicated.
 *
 * `media.main_image` is intentionally promoted to the front: the sync writes it
 * as the explicit cover and it may not be the first entry of `media.images`.
 */
export function getProductImages(product: unknown): string[] {
  if (!product || typeof product !== 'object') return []
  const p = product as AnyRecord
  const meta = (p.meta ?? {}) as AnyRecord
  const media = (meta.media ?? {}) as AnyRecord
  const attributes = (p.attributes ?? {}) as AnyRecord

  const cover = [
    ...pickUrls(media.main_image),
    ...pickUrls(media.mainImage),
    ...pickUrls(meta.main_image),
    ...pickUrls(meta.mainImage),
  ]

  const rest = [
    ...pickUrls(media.images),
    ...pickUrls(media.gallery_images),
    ...pickUrls(media.galleryImages),
    ...pickUrls(meta.main_images),
    ...pickUrls(meta.images),
    ...pickUrls(attributes.images),
    ...pickUrls(p.images),
    ...pickUrls(p.image_url),
  ]

  const seen = new Set<string>()
  const result: string[] = []
  for (const url of [...cover, ...rest]) {
    if (!seen.has(url)) {
      seen.add(url)
      result.push(url)
    }
  }
  return result
}

/** The single image to show in a list row, or null. */
export function getProductThumbnail(product: unknown): string | null {
  return getProductImages(product)[0] ?? null
}

/** Count of usable images, for "how complete is this listing" hints. */
export function countProductImages(product: unknown): number {
  return getProductImages(product).length
}
