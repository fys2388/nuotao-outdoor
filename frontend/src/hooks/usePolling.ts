import { useEffect, useRef, useCallback, useState } from 'react'

interface UsePollingOptions {
  intervalMs: number
  immediate?: boolean
  enabled?: boolean
}

/**
 * Poll a callback at a fixed interval.
 * 
 * @param callback - async function to call at each interval
 * @param options - polling configuration
 * @returns { stop, start, isPolling } controls and state
 */
export function usePolling(
  callback: () => Promise<void> | void,
  options: UsePollingOptions,
) {
  const { intervalMs, immediate = false, enabled = true } = options
  const timerRef = useRef<number | null>(null)
  const callbackRef = useRef(callback)
  const [isPolling, setIsPolling] = useState(enabled)

  // Keep callback ref up to date
  callbackRef.current = callback

  const stop = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    setIsPolling(false)
  }, [])

  const start = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
    }
    setIsPolling(true)
    
    if (immediate) {
      void callbackRef.current()
    }
    
    timerRef.current = window.setInterval(() => {
      void callbackRef.current()
    }, intervalMs)
  }, [intervalMs, immediate])

  useEffect(() => {
    if (enabled) {
      start()
    } else {
      stop()
    }
    
    return () => {
      stop()
    }
  }, [enabled, start, stop])

  return { stop, start, isPolling }
}