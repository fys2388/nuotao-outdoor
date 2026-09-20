import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { visualizer } from 'rollup-plugin-visualizer'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const apiProxyTarget =
    process.env.VITE_API_PROXY_TARGET || env.VITE_API_PROXY_TARGET || 'http://localhost:8000'
  const buildId = (
    process.env.VITE_BUILD_ID ||
    env.VITE_BUILD_ID ||
    new Date().toISOString().replace(/\D/g, '').slice(0, 14)
  ).replace(/[^a-zA-Z0-9_-]/g, '')

  return {
  plugins: [
    react(),
    // Bundle 分析器（构建时生成 stats.html）
    visualizer({
      filename: 'dist/stats.html',
      open: false,
      gzipSize: true,
      brotliSize: true,
    }),
  ],

  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
    // 预构建优化（减少冷启动时间）
    warmup: {
      clientFiles: ['./src/App.tsx', './src/main.tsx'],
    },
  },

  build: {
    // 构建目标（支持现代浏览器）
    target: 'es2020',
    // 压缩方式（esbuild 更快，terser 更小但更慢）
    minify: 'esbuild',
    // 生产环境不生成 sourcemap（减小体积，可根据需要开启）
    sourcemap: false,
    // chunk 大小警告阈值（KB）
    chunkSizeWarningLimit: 1000,
    // CSS 代码分割
    cssCodeSplit: true,
    // 资源内联阈值（小于 4KB 的资源内联为 base64）
    assetsInlineLimit: 4096,

    rollupOptions: {
      output: {
        // 手动代码分割（按依赖库拆分，函数形式更灵活）
        manualChunks(id) {
          // React 核心库
          if (id.includes('node_modules/react/') || id.includes('node_modules/react-dom/') || id.includes('node_modules/scheduler/')) {
            return 'react-vendor'
          }
          // Ant Design UI 库
          if (id.includes('node_modules/antd/') || id.includes('node_modules/@ant-design/')) {
            return 'antd-vendor'
          }
          // Ant Design Icons 单独拆分（图标库较大）
          if (id.includes('node_modules/@ant-design/icons/')) {
            return 'icons-vendor'
          }
          // 路由库
          if (id.includes('node_modules/react-router/') || id.includes('node_modules/@remix-run/')) {
            return 'router-vendor'
          }
          // 工具库
          if (id.includes('node_modules/lodash/') || id.includes('node_modules/axios/') || id.includes('node_modules/dayjs/')) {
            return 'utils-vendor'
          }
          // 图表库
          if (id.includes('node_modules/echarts/') || id.includes('node_modules/zrender/')) {
            return 'charts-vendor'
          }
        },

        // 内容哈希之外再附加构建标识，避免 CDN 长期缓存旧地址或错误响应。
        chunkFileNames: `assets/js/[name]-[hash]-${buildId}.js`,
        entryFileNames: `assets/js/[name]-[hash]-${buildId}.js`,
        assetFileNames: (assetInfo) => {
          const ext = assetInfo.name?.split('.').pop() || ''
          if (ext === 'css') return `assets/css/[name]-[hash]-${buildId}.[ext]`
          if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext))
            return 'assets/images/[name]-[hash].[ext]'
          if (['woff', 'woff2', 'ttf', 'eot'].includes(ext))
            return 'assets/fonts/[name]-[hash].[ext]'
          return 'assets/[name]-[hash].[ext]'
        },
      },
    },
  },

  // 依赖预构建优化
  optimizeDeps: {
    include: ['react', 'react-dom', 'antd', '@ant-design/icons'],
    // 预构建时排除（避免重复打包）
    exclude: [],
  },

  // 环境变量前缀
  envPrefix: 'VITE_',
  }
})
