import React from 'react'
import ReactDOM from 'react-dom/client'
import { App as AntApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { installInjectionDefense } from './security/injectionGuard'
import './index.css'

// BUG #10: CSP 已经挡了 iframe 加载，这里做双保险 —— 主动拦截任何
// chrome-extension / 第三方 iframe / 未知 inline script 的注入。
installInjectionDefense()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{
      token: {
        colorPrimary: '#c96f32',
        colorInfo: '#2f7367',
        colorSuccess: '#2f8b64',
        colorWarning: '#c8872b',
        colorError: '#c34d4d',
        colorText: '#22302c',
        colorTextSecondary: '#6b7773',
        colorBgLayout: '#eef1ed',
        colorBgContainer: '#ffffff',
        borderRadius: 8,
        borderRadiusLG: 8,
        fontFamily: '"Aptos", "Segoe UI Variable", "Microsoft YaHei UI", "Noto Sans SC", sans-serif',
      },
      components: {
        Layout: {
          headerBg: '#ffffff',
          siderBg: '#173c35',
          bodyBg: '#eef1ed',
        },
        Menu: {
          darkItemBg: '#173c35',
          darkSubMenuItemBg: '#12332d',
          darkItemSelectedBg: '#d9773b',
          darkItemHoverBg: '#245248',
          itemBorderRadius: 7,
        },
        Card: {
          headerFontSize: 15,
        },
        Tag: {
          borderRadiusSM: 999,
        },
      },
    }}>
      <AntApp>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
)
