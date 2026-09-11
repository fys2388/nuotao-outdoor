import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import en from './en.json'
import de from './de.json'
import zh from './zh.json'

const translations: Record<string, any> = { en, de, zh }

interface I18nContextType {
  language: string
  setLanguage: (lang: string) => void
  t: (key: string) => string
  currency: string
  setCurrency: (curr: string) => void
}

const I18nContext = createContext<I18nContextType | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState('en')
  const [currency, setCurrencyState] = useState('USD')

  useEffect(() => {
    const savedLang = localStorage.getItem('nuotao_lang') || 'en'
    const savedCurrency = localStorage.getItem('nuotao_currency') || 'USD'
    setLanguageState(savedLang)
    setCurrencyState(savedCurrency)
  }, [])

  const setLanguage = (lang: string) => {
    setLanguageState(lang)
    localStorage.setItem('nuotao_lang', lang)
  }

  const setCurrency = (curr: string) => {
    setCurrencyState(curr)
    localStorage.setItem('nuotao_currency', curr)
  }

  const t = (key: string): string => {
    const keys = key.split('.')
    let value: any = translations[language] || translations.en
    for (const k of keys) {
      value = value?.[k]
    }
    return value || key
  }

  return (
    <I18nContext.Provider value={{ language, setLanguage, t, currency, setCurrency }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n() {
  const context = useContext(I18nContext)
  if (!context) throw new Error('useI18n must be used within I18nProvider')
  return context
}
