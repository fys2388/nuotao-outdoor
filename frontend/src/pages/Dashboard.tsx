import { useEffect, useState } from "react";
import { healthApi, productApi, agentApi, eventApi, Product, Agent, Event } from "../api/client";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: string;
  color: string;
}

function StatCard({ title, value, subtitle, icon, color }: StatCardProps) {
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: "0.75rem",
        padding: "1.5rem",
        boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
        display: "flex",
        alignItems: "center",
        gap: "1rem",
      }}
    >
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: "0.5rem",
          background: color,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "1.5rem",
        }}
      >
        {icon}
      </div>
      <div>
        <div style={{ fontSize: "0.8rem", color: "#666", marginBottom: "0.25rem" }}>{title}</div>
        <div style={{ fontSize: "1.5rem", fontWeight: "bold", color: "#333" }}>{value}</div>
        {subtitle && <div style={{ fontSize: "0.7rem", color: "#999", marginTop: "0.25rem" }}>{subtitle}</div>}
      </div>
    </div>
  );
}

export function Dashboard() {
  const [products, setProducts] = useState<Product[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [health, setHealth] = useState<{ database: string; redis: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      const [healthRes, productsRes, agentsRes, eventsRes] = await Promise.all([
        healthApi.readyz(),
        productApi.list(),
        agentApi.list(),
        eventApi.list(10),
      ]);

      if (healthRes.data) setHealth(healthRes.data.checks);
      if (productsRes.data) setProducts(Array.isArray(productsRes.data) ? productsRes.data : (productsRes.data.items || []));
      if (agentsRes.data) setAgents(Array.isArray(agentsRes.data) ? agentsRes.data : (agentsRes.data.items || []));
      if (eventsRes.data) setEvents(Array.isArray(eventsRes.data) ? eventsRes.data : (eventsRes.data.items || eventsRes.data.events || []));
      setLoading(false);
    }
    loadData();
  }, []);

  if (loading) {
    return <div style={{ padding: "2rem", color: "#666" }}>加载中...</div>;
  }

  const activeAgents = agents.filter((a) => a.status === "active").length;

  return (
    <div>
      {/* Stats */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "1rem",
          marginBottom: "2rem",
        }}
      >
        <StatCard title="产品总数" value={products.length} subtitle="已注册产品" icon="📦" color="#e3f2fd" />
        <StatCard title="AI Agent" value={activeAgents} subtitle={`共 ${agents.length} 个已注册`} icon="🤖" color="#f3e5f5" />
        <StatCard title="数据库" value={health?.database === "ok" ? "正常" : "异常"} subtitle="PostgreSQL 16" icon="🗄️" color="#e8f5e9" />
        <StatCard title="Redis" value={health?.redis === "ok" ? "正常" : "异常"} subtitle="缓存 + 任务队列" icon="⚡" color="#fff3e0" />
      </div>

      {/* Recent Events & Agents */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        {/* Recent Events */}
        <div style={{ background: "#fff", borderRadius: "0.75rem", padding: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          <h3 style={{ margin: "0 0 1rem 0", fontSize: "1rem", color: "#333" }}>最近事件</h3>
          <div style={{ maxHeight: 300, overflowY: "auto" }}>
            {events.length === 0 ? (
              <div style={{ color: "#999", fontSize: "0.85rem" }}>暂无事件</div>
            ) : (
              events.slice(0, 10).map((event) => (
                <div
                  key={event.id}
                  style={{
                    padding: "0.75rem 0",
                    borderBottom: "1px solid #f0f0f0",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ fontSize: "0.85rem", fontWeight: 500, color: "#333" }}>{event.event_type}</div>
                    <div style={{ fontSize: "0.75rem", color: "#999" }}>
                      {event.entity_type}: {event.entity_id?.slice(0, 8)}...
                    </div>
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "#bbb" }}>
                    {event.created_at ? new Date(event.created_at).toLocaleTimeString() : ""}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Agent Status */}
        <div style={{ background: "#fff", borderRadius: "0.75rem", padding: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          <h3 style={{ margin: "0 0 1rem 0", fontSize: "1rem", color: "#333" }}>AI Agent 状态</h3>
          <div>
            {agents.length === 0 ? (
              <div style={{ color: "#999", fontSize: "0.85rem" }}>暂无 Agent</div>
            ) : (
              agents.map((agent) => (
                <div
                  key={agent.id}
                  style={{
                    padding: "0.75rem 0",
                    borderBottom: "1px solid #f0f0f0",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ fontSize: "0.85rem", fontWeight: 500, color: "#333" }}>{agent.name}</div>
                    <div style={{ fontSize: "0.75rem", color: "#999" }}>
                      {agent.model_provider}/{agent.model_name}
                    </div>
                  </div>
                  <span
                    style={{
                      background: agent.status === "active" ? "#e8f5e9" : "#ffebee",
                      color: agent.status === "active" ? "#2e7d32" : "#c62828",
                      padding: "0.25rem 0.75rem",
                      borderRadius: "1rem",
                      fontSize: "0.7rem",
                      fontWeight: 500,
                    }}
                  >
                    {agent.status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
