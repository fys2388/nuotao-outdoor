import { useEffect, useState } from "react";
import { eventApi, Event } from "../api/client";

export function Events() {
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadEvents() {
      setLoading(true);
      const res = await eventApi.list(50);
      if (res.data) setEvents(res.data);
      setLoading(false);
    }
    loadEvents();
  }, []);

  if (loading) {
    return <div style={{ padding: "2rem", color: "#666" }}>加载中...</div>;
  }

  return (
    <div style={{ background: "#fff", borderRadius: "0.75rem", padding: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
      <h3 style={{ margin: "0 0 1rem 0", fontSize: "1rem", color: "#333" }}>事件日志 ({events.length})</h3>
      <div style={{ maxHeight: 600, overflowY: "auto" }}>
        {events.length === 0 ? (
          <div style={{ color: "#999", fontSize: "0.85rem", textAlign: "center", padding: "2rem" }}>暂无事件</div>
        ) : (
          events.map((event) => (
            <div
              key={event.id}
              style={{
                padding: "0.75rem 1rem",
                marginBottom: "0.5rem",
                borderRadius: "0.5rem",
                background: "#f9f9f9",
                borderLeft: "3px solid #2196f3",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontSize: "0.85rem", fontWeight: 500, color: "#333" }}>{event.event_type}</div>
                <div style={{ fontSize: "0.7rem", color: "#999" }}>
                  {event.created_at ? new Date(event.created_at).toLocaleString() : ""}
                </div>
              </div>
              <div style={{ fontSize: "0.75rem", color: "#666", marginTop: "0.25rem" }}>
                {event.entity_type}: {event.entity_id?.slice(0, 12)}...
                {event.actor && <span style={{ marginLeft: "1rem" }}>操作者: {event.actor}</span>}
              </div>
              {event.payload && Object.keys(event.payload).length > 0 && (
                <details style={{ marginTop: "0.5rem" }}>
                  <summary style={{ fontSize: "0.7rem", color: "#999", cursor: "pointer" }}>查看详情</summary>
                  <pre style={{ fontSize: "0.7rem", color: "#666", background: "#fff", padding: "0.5rem", borderRadius: "0.25rem", marginTop: "0.5rem", overflowX: "auto" }}>
                    {JSON.stringify(event.payload, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
