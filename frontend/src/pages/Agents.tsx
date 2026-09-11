import { useEffect, useState } from "react";
import { agentApi, Agent } from "../api/client";

export function Agents() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadAgents() {
      setLoading(true);
      const res = await agentApi.list();
      if (res.data) setAgents(res.data);
      setLoading(false);
    }
    loadAgents();
  }, []);

  if (loading) {
    return <div style={{ padding: "2rem", color: "#666" }}>加载中...</div>;
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1rem" }}>
      {agents.map((agent) => (
        <div
          key={agent.id}
          style={{
            background: "#fff",
            borderRadius: "0.75rem",
            padding: "1.5rem",
            boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: "1rem" }}>
            <div>
              <h3 style={{ margin: 0, fontSize: "1rem", color: "#333" }}>{agent.name}</h3>
              <div style={{ fontSize: "0.75rem", color: "#999", marginTop: "0.25rem" }}>{agent.agent_id}</div>
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

          {agent.description && (
            <p style={{ fontSize: "0.8rem", color: "#666", margin: "0 0 1rem 0", lineHeight: 1.5 }}>
              {agent.description}
            </p>
          )}

          <div style={{ fontSize: "0.75rem", color: "#555", lineHeight: 1.8 }}>
            <div><strong>领域:</strong> {agent.domain}</div>
            <div><strong>版本:</strong> {agent.version}</div>
            <div><strong>模型:</strong> {agent.model_provider}/{agent.model_name}</div>
            <div><strong>提示词版本:</strong> {agent.prompt_version}</div>
            <div><strong>权限级别:</strong> {agent.permission_level}</div>
          </div>

          <div style={{ marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid #f0f0f0", fontSize: "0.7rem", color: "#bbb" }}>
            ID: {agent.id.slice(0, 8)}...
          </div>
        </div>
      ))}
    </div>
  );
}
