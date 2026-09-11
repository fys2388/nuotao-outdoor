import { useEffect, useState } from "react";
import { healthApi } from "../api/client";

interface SystemInfo {
  health: { status: string } | null;
  ready: { status: string; checks: { database: string; redis: string } } | null;
}

export function System() {
  const [info, setInfo] = useState<SystemInfo>({ health: null, ready: null });
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadData = async () => {
    setLoading(true);
    const [healthRes, readyRes] = await Promise.all([healthApi.healthz(), healthApi.readyz()]);
    setInfo({
      health: healthRes.data || null,
      ready: readyRes.data || null,
    });
    setLastUpdated(new Date());
    setLoading(false);
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  const services = [
    {
      name: "API 服务",
      status: info.health?.status === "ok" ? "正常" : "异常",
      icon: "🌐",
      color: info.health?.status === "ok" ? "#e8f5e9" : "#ffebee",
      textColor: info.health?.status === "ok" ? "#2e7d32" : "#c62828",
      detail: "FastAPI + Uvicorn",
    },
    {
      name: "数据库",
      status: info.ready?.checks.database === "ok" ? "正常" : "异常",
      icon: "🗄️",
      color: info.ready?.checks.database === "ok" ? "#e8f5e9" : "#ffebee",
      textColor: info.ready?.checks.database === "ok" ? "#2e7d32" : "#c62828",
      detail: "PostgreSQL 16",
    },
    {
      name: "Redis",
      status: info.ready?.checks.redis === "ok" ? "正常" : "异常",
      icon: "⚡",
      color: info.ready?.checks.redis === "ok" ? "#e8f5e9" : "#ffebee",
      textColor: info.ready?.checks.redis === "ok" ? "#2e7d32" : "#c62828",
      detail: "缓存 + 任务队列",
    },
    {
      name: "Worker 进程",
      status: "运行中",
      icon: "🔧",
      color: "#e8f5e9",
      textColor: "#2e7d32",
      detail: "Agent Worker + Alert Scheduler",
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h2 style={{ margin: 0, fontSize: "1.25rem", color: "#333" }}>系统状态</h2>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          {lastUpdated && <span style={{ fontSize: "0.75rem", color: "#999" }}>最后更新: {lastUpdated.toLocaleTimeString()}</span>}
          <button
            onClick={loadData}
            disabled={loading}
            style={{
              padding: "0.5rem 1rem",
              background: loading ? "#ccc" : "#2196f3",
              color: "#fff",
              border: "none",
              borderRadius: "0.5rem",
              fontSize: "0.8rem",
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "刷新中..." : "刷新"}
          </button>
        </div>
      </div>

      {/* Service Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
        {services.map((service) => (
          <div
            key={service.name}
            style={{
              background: "#fff",
              borderRadius: "0.75rem",
              padding: "1.5rem",
              boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
              <span style={{ fontSize: "2rem" }}>{service.icon}</span>
              <div>
                <div style={{ fontSize: "1rem", fontWeight: 500, color: "#333" }}>{service.name}</div>
                <div style={{ fontSize: "0.75rem", color: "#999" }}>{service.detail}</div>
              </div>
            </div>
            <span
              style={{
                display: "inline-block",
                background: service.color,
                color: service.textColor,
                padding: "0.3rem 0.75rem",
                borderRadius: "1rem",
                fontSize: "0.8rem",
                fontWeight: 500,
              }}
            >
              ● {service.status}
            </span>
          </div>
        ))}
      </div>

      {/* API Info */}
      <div style={{ background: "#fff", borderRadius: "0.75rem", padding: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
        <h3 style={{ margin: "0 0 1rem 0", fontSize: "1rem", color: "#333" }}>API 信息</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", fontSize: "0.85rem" }}>
          <div>
            <div style={{ color: "#666", marginBottom: "0.25rem" }}>API 地址</div>
            <div style={{ color: "#333", fontFamily: "monospace" }}>http://localhost:8000/api/v1</div>
          </div>
          <div>
            <div style={{ color: "#666", marginBottom: "0.25rem" }}>API 文档</div>
            <div style={{ color: "#333", fontFamily: "monospace" }}>http://localhost:8000/docs</div>
          </div>
          <div>
            <div style={{ color: "#666", marginBottom: "0.25rem" }}>前端地址</div>
            <div style={{ color: "#333", fontFamily: "monospace" }}>http://localhost:5173</div>
          </div>
          <div>
            <div style={{ color: "#666", marginBottom: "0.25rem" }}>LLM 提供商</div>
            <div style={{ color: "#333" }}>DeepSeek (deepseek-chat)</div>
          </div>
        </div>
      </div>
    </div>
  );
}
