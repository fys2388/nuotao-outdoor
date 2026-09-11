import { useState, useEffect } from 'react'
import { Select, Dropdown, Button, Space } from 'antd'
import { GlobalOutlined } from '@ant-design/icons'

const languages = [
  { value: 'en', label: 'English', flag: '🇺🇸' },
  { value: 'de', label: 'Deutsch', flag: '🇩🇪' },
  { value: 'es', label: 'Español', flag: '🇪🇸' },
  { value: 'fr', label: 'Français', flag: '🇫🇷' },
  { value: 'zh', label: '中文', flag: '🇨🇳' },
]

const currencies = [
  { value: 'USD', label: 'USD $', symbol: '$' },
  { value: 'EUR', label: 'EUR €', symbol: '€' },
  { value: 'GBP', label: 'GBP £', symbol: '£' },
  { value: 'CAD', label: 'CAD C$', symbol: 'C$' },
  { value: 'AUD', label: 'AUD A$', symbol: 'A$' },
]

export default function LanguageSwitcher() {
  const [language, setLanguage] = useState('en')
  const [currency, setCurrency] = useState('USD')

  useEffect(() => {
    const savedLang = localStorage.getItem('nuotao_lang')
    const savedCurrency = localStorage.getItem('nuotao_currency')
    if (savedLang) setLanguage(savedLang)
    if (savedCurrency) setCurrency(savedCurrency)
  }, [])

  const handleLanguageChange = (lang: string) => {
    setLanguage(lang)
    localStorage.setItem('nuotao_lang', lang)
    document.documentElement.lang = lang
    // 触发页面刷新以应用语言
    window.location.reload()
  }

  const handleCurrencyChange = (curr: string) => {
    setCurrency(curr)
    localStorage.setItem('nuotao_currency', curr)
  }

  return (
    <Space size="small">
      <Select
        value={language}
        onChange={handleLanguageChange}
        style={{ width: 110 }}
        size="small"
        prefix={<GlobalOutlined />}
        options={languages.map(l => ({ value: l.value, label: `${l.flag} ${l.label}` }))}
      />
      <Select
        value={currency}
        onChange={handleCurrencyChange}
        style={{ width: 90 }}
        size="small"
        options={currencies.map(c => ({ value: c.value, label: c.label }))}
      />
    </Space>
  )
}
