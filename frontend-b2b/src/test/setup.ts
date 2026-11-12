// M2.5.6: Vitest + React Testing Library setup.
import '@testing-library/jest-dom/vitest'

// jsdom lacks matchMedia, which some Ant Design components use on mount.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

// jsdom lacks ResizeObserver, required by Ant Design layout/Select components.
if (typeof globalThis !== 'undefined' && !(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}
// jsdom lacks scrollIntoView (used by antd Select dropdowns).
if (typeof window !== 'undefined' && !(Element.prototype as any).scrollIntoView) {
  ;(Element.prototype as any).scrollIntoView = () => {}
}

// jsdom's localStorage can be unavailable/flaky under the test runner; back it
// with a minimal in-memory stub so cart/auth persistence works in tests.
if (typeof window !== 'undefined') {
  const store = new Map<string, string>()
  const localStorageStub = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => {
      store.set(k, String(v))
    },
    removeItem: (k: string) => {
      store.delete(k)
    },
    clear: () => store.clear(),
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    get length() {
      return store.size
    },
  }
  try {
    window.localStorage.setItem('__probe__', '1')
    window.localStorage.removeItem('__probe__')
  } catch {
    Object.defineProperty(window, 'localStorage', { value: localStorageStub, configurable: true })
  }
}