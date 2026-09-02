import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { visualizer } from 'rollup-plugin-visualizer'

// https://vitejs.dev/config/
export default defineConfig({
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
        target: 'http://localhost:8000',
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
        // 手动代码分割（按依赖库拆分）
        manualChunks: {
          // React 核心库
          'react-vendor': ['react', 'react-dom'],
          // Ant Design UI 库
          'antd-vendor': ['antd', '@ant-design/icons'],
        },

        // chunk 文件命名（含内容哈希，便于缓存）
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: (assetInfo) => {
          const ext = assetInfo.name?.split('.').pop() || ''
          if (ext === 'css') return 'assets/css/[name]-[hash].[ext]'
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
})
