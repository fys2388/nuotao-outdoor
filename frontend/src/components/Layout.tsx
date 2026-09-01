import { ReactNode, useState } from "react";

interface NavItem {
  id: string;
  label: string;
  icon: string;
}

const navItems: NavItem[] = [
  { id: "dashboard", label: "仪表盘", icon: "📊" },
  { id: "products", label: "产品管理", icon: "📦" },
  { id: "orders", label: "订单管理", icon: "🛒" },
  { id: "users", label: "用户权限", icon: "👥" },
  { id: "ai-analysis", label: "AI 分析", icon: "🤖" },
  { id: "agents", label: "Agent 管理", icon: "⚙️" },
  { id: "events", label: "事件日志", icon: "📋" },
  { id: "rules", label: "规则引擎", icon: "📐" },
  { id: "system", label: "系统状态", icon: "🖥️" },
];

interface LayoutProps {
  children: ReactNode;
  currentPage: string;
  onNavigate: (page: string) => void;
}

export function Layout({ children, currentPage, onNavigate }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      {/* Sidebar */}
      <aside
        style={{
          width: sidebarOpen ? 240 : 60,
          background: "#1a1a2e",
          color: "#eee",
          transition: "width 0.2s",
          display: "flex",
          flexDirection: "column",
          position: "fixed",
          height: "100vh",
          zIndex: 100,
        }}
      >
        {/* Logo */}
        <div
          style={{
            padding: "1rem",
            borderBottom: "1px solid #333",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            cursor: "pointer",
          }}
          onClick={() => setSidebarOpen(!sidebarOpen)}
        >
          <span style={{ fontSize: "1.5rem" }}>🏕️</span>
          {sidebarOpen && (
            <div>
              <div style={{ fontWeight: "bold", fontSize: "0.9rem" }}>Nuotao AI OS</div>
              <div style={{ fontSize: "0.7rem", color: "#888" }}>户外电商智能运营</div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "0.5rem 0", overflowY: "auto" }}>
          {navItems.map((item) => (
            <div
              key={item.id}
              onClick={() => onNavigate(item.id)}
              style={{
                padding: "0.75rem 1rem",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                background: currentPage === item.id ? "#16213e" : "transparent",
                borderLeft: currentPage === item.id ? "3px solid #0f3460" : "3px solid transparent",
                transition: "background 0.15s",
              }}
              onMouseEnter={(e) => {
                if (currentPage !== item.id) {
                  e.currentTarget.style.background = "#16213e";
                }
              }}
              onMouseLeave={(e) => {
                if (currentPage !== item.id) {
                  e.currentTarget.style.background = "transparent";
                }
              }}
            >
              <span style={{ fontSize: "1.1rem" }}>{item.icon}</span>
              {sidebarOpen && <span style={{ fontSize: "0.85rem" }}>{item.label}</span>}
            </div>
          ))}
        </nav>

        {/* Footer */}
        {sidebarOpen && (
          <div style={{ padding: "1rem", borderTop: "1px solid #333", fontSize: "0.7rem", color: "#666" }}>
            <div>v0.1.0</div>
            <div style={{ marginTop: "0.25rem" }}>© 2026 Nuotao Outdoor</div>
          </div>
        )}
      </aside>

      {/* Main content */}
      <main
        style={{
          flex: 1,
          marginLeft: sidebarOpen ? 240 : 60,
          background: "#f5f5f7",
          minHeight: "100vh",
          transition: "margin-left 0.2s",
        }}
      >
        {/* Header */}
        <header
          style={{
            background: "#fff",
            padding: "1rem 2rem",
            borderBottom: "1px solid #e0e0e0",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            position: "sticky",
            top: 0,
            zIndex: 50,
          }}
        >
          <h1 style={{ margin: 0, fontSize: "1.25rem", color: "#333" }}>
            {navItems.find((n) => n.id === currentPage)?.label || "仪表盘"}
          </h1>
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <span
              style={{
                background: "#e8f5e9",
                color: "#2e7d32",
                padding: "0.25rem 0.75rem",
                borderRadius: "1rem",
                fontSize: "0.75rem",
                fontWeight: 500,
              }}
            >
              ● 系统运行中
            </span>
          </div>
        </header>

        {/* Page content */}
        <div style={{ padding: "2rem" }}>{children}</div>
      </main>
    </div>
  );
}
