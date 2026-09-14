import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button, Result } from 'antd'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  message: string
}

/**
 * 全局渲染错误边界：单个页面/组件抛出渲染异常时，展示可恢复的兜底界面而不是整屏白屏，
 * 并保留回到总览与整页刷新两个出口。网络请求错误由各页面自行处理，不在此拦截。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error?.message || '页面渲染异常' }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 保留控制台轨迹，便于排查；不打印任何敏感业务数据。
    console.error('[ErrorBoundary] render error:', error, info.componentStack)
  }

  private handleReload = (): void => {
    window.location.reload()
  }

  private handleGoHome = (): void => {
    window.location.href = '/dashboard'
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children
    return (
      <div style={{ padding: '48px 24px', maxWidth: 720, margin: '0 auto' }}>
        <Result
          status="error"
          title="当前模块出现渲染异常"
          subTitle={this.state.message}
          extra={[
            <Button type="primary" key="home" onClick={this.handleGoHome}>
              返回经营总览
            </Button>,
            <Button key="reload" onClick={this.handleReload}>
              刷新页面
            </Button>,
          ]}
        />
      </div>
    )
  }
}
