import { BrowserRouter } from 'react-router-dom'
import AppRoutes from './app/AppRoutes'
import { AuthProvider } from './auth/AuthProvider'

export default function App() {
  return (
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
