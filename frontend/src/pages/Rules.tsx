import { useEffect, useState } from "react";
import { ruleApi, Rule } from "../api/client";

export function Rules() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadRules() {
      setLoading(true);
      const res = await ruleApi.list();
      if (res.data) setRules(res.data);
      setLoading(false);
    }
    loadRules();
  }, []);

  if (loading) {
    return <div style={{ padding: "2rem", color: "#666" }}>加载中...</div>;
  }

  const groups = Array.from(new Set(rules.map((r) => r.group)));

  return (
    <div>
      {groups.map((group) => (
        <div key={group} style={{ marginBottom: "2rem" }}>
          <h3 style={{ margin: "0 0 1rem 0", fontSize: "1rem", color: "#333" }}>
            {group} ({rules.filter((r) => r.group === group).length})
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "1rem" }}>
            {rules
              .filter((r) => r.group === group)
              .map((rule) => (
                <div
                  key={rule.id}
                  style={{
                    background: "#fff",
                    borderRadius: "0.75rem",
                    padding: "1.25rem",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: "0.5rem" }}>
                    <div style={{ fontSize: "0.9rem", fontWeight: 500, color: "#333" }}>{rule.name}</div>
                    <span
                      style={{
                        background: rule.rule_type === "hard" ? "#ffebee" : "#e3f2fd",
                        color: rule.rule_type === "hard" ? "#c62828" : "#1565c0",
                        padding: "0.2rem 0.6rem",
                        borderRadius: "1rem",
                        fontSize: "0.65rem",
                        fontWeight: 500,
                      }}
                    >
                      {rule.rule_type}
                    </span>
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "#999", marginBottom: "0.5rem" }}>
                    {rule.rule_id} v{rule.version}
                  </div>
                  {rule.description && (
                    <p style={{ fontSize: "0.8rem", color: "#666", margin: 0, lineHeight: 1.5 }}>{rule.description}</p>
                  )}
                  <div style={{ marginTop: "0.75rem", fontSize: "0.7rem", color: "#bbb" }}>
                    状态: {rule.status}
                  </div>
                </div>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}
