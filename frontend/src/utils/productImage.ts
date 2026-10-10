/**
 * 产品图片工具函数
 * 从产品数据中提取图片 URL
 */

export interface ProductWithMeta {
  meta?: Record<string, unknown> | null
  attributes?: Record<string, unknown> | null
  images?: string[]
  [key: string]: unknown
}

/**
 * 从产品数据中提取图片 URL
 * 优先级: images[0] > meta.main_images[0].src > meta.image_url > meta.image > meta.main_image > meta.images[0] > attributes.image > null
 */
export function getProductImageUrl(product: ProductWithMeta): string | null {
  if (!product) return null
  
  // 1. images[0] (ProductListing 使用的格式)
  if (Array.isArray(product.images) && product.images.length > 0 && product.images[0]) {
    return product.images[0]
  }
  
  const meta = product.meta || {}
  const attributes = product.attributes || {}
  
  // 2. meta.main_images[0].src (数组格式)
  const mainImages = meta.main_images as Array<{ src?: string }> | undefined
  if (Array.isArray(mainImages) && mainImages.length > 0 && mainImages[0]?.src) {
    return mainImages[0].src
  }
  
  // 3. meta.image_url (单 URL 字符串)
  if (typeof meta.image_url === 'string' && meta.image_url) {
    return meta.image_url
  }
  
  // 4. meta.image (单 URL 字符串)
  if (typeof meta.image === 'string' && meta.image) {
    return meta.image
  }
  
  // 5. meta.main_image (单 URL 字符串)
  if (typeof meta.main_image === 'string' && meta.main_image) {
    return meta.main_image
  }
  
  // 6. meta.images[0] (数组格式)
  const images = meta.images as string[] | undefined
  if (Array.isArray(images) && images.length > 0 && images[0]) {
    return images[0]
  }
  
  // 7. attributes.image
  if (typeof attributes.image === 'string' && attributes.image) {
    return attributes.image
  }
  
  return null
}

/**
 * 获取产品图片占位符 URL (当没有图片时)
 */
export function getImagePlaceholder(): string {
  return 'https://via.placeholder.com/60x60?text=无图片'
}