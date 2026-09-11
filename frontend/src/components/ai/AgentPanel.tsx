import { useState } from "react";

export interface AnalysisResult {
  summary: string;
  confidence_score: number;
  [key: string]: any;
}

interface AgentPanelProps {
  agentName: string;
  agentColor: string;
  defaultContext: string;
  onAnalyze: (context: string) => Promise<AnalysisResult | null>;
  resultKeys: { key: string; label: string; type: "text" | "list" | "object" | "number" }[];
}

export function AgentPanel({
  agentName,
  agentColor,
  defaultContext,
  onAnalyze,
  resultKeys,
}: AgentPanelProps) {
  const [context, setContext] = useState(defaultContext);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    const startTime = Date.now();

    try {
      const res = await onAnalyze(context);
      if (res) {
        setResult(res);
        setElapsed((Date.now() - startTime) / 1000);
      } else {
        setError("分析失败，请重试");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "分析过程中发生错误");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setContext(defaultContext);
    setResult(null);
    setError(null);
    setElapsed(null);
  };

  const renderValue = (value: any, type: string) => {
    if (value === null || value === undefined) {
      return <span style={{ color: "#999" }}>N/A</span>;
    }

    if (type === "text") {
      return <span style={{ color: "#333" }}>{String(value)}</span>;
    }

    if (type === "number") {
      return (
        <span style={{ color: agentColor, fontWeight: 600, fontSize: "1.1rem" }}>
          {typeof value === "number" ? value.toFixed(2) : value}
        </span>
      );
    }

    if (type === "list" && Array.isArray(value)) {
      return (
        <ul style={{ margin: 0, paddingLeft: "1.25rem", color: "#555" }}>
          {value.map((item, idx) => (
            <li key={idx} style={{ marginBottom: "0.35rem", lineHeight: 1.5 }}>
              {typeof item === "object" ? JSON.stringify(item, null, 2) : String(item)}
            </li>
          ))}
        </ul>
      );
    }

    if (type === "object" && typeof value === "object") {
      return (
        <pre
          style={{
            background: "#f5f5f5",
            padding: "0.75rem",
            borderRadius: "0.375rem",
            fontSize: "0.75rem",
            overflow: "auto",
            maxHeight: "300px",
            margin: 0,
          }}
        >
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }

    return <span style={{ color: "#333" }}>{String(value)}</span>;
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
      {/* 左侧：输入区域 */}
      <div
        style={{
          background: "#fff",
          borderRadius: "0.75rem",
          padding: "1.25rem",
          boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
        }}
      >
        <h3 style={{ margin: "0 0 1rem 0", fontSize: "1rem", color: "#333" }}>
          分析上下文
        </h3>

        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          style={{
            width: "100%",
            minHeight: "400px",
            padding: "0.75rem",
            border: "1px solid #ddd",
            borderRadius: "0.5rem",
            fontSize: "0.8rem",
            fontFamily: "monospace",
            resize: "vertical",
            boxSizing: "border-box",
          }}
          placeholder="输入 JSON 格式的分析上下文数据..."
        />

        <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
          <button
            onClick={handleAnalyze}
            disabled={loading}
            style={{
              flex: 1,
              padding: "0.75rem 1.5rem",
              background: loading ? "#ccc" : agentColor,
              color: "#fff",
              border: "none",
              borderRadius: "0.5rem",
              fontSize: "0.9rem",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              transition: "background 0.2s",
            }}
          >
            {loading ? "分析中..." : `运行 ${agentName} 分析`}
          </button>

          <button
            onClick={handleReset}
            disabled={loading}
            style={{
              padding: "0.75rem 1.25rem",
              background: "#f5f5f5",
              color: "#666",
              border: "1px solid #ddd",
              borderRadius: "0.5rem",
              fontSize: "0.9rem",
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            重置
          </button>
        </div>

        {error && (
          <div
            style={{
              marginTop: "1rem",
              padding: "0.75rem",
              background: "#ffebee",
              color: "#c62828",
              borderRadius: "0.5rem",
              fontSize: "0.85rem",
            }}
          >
            ❌ {error}
          </div>
        )}
      </div>

      {/* 右侧：结果展示 */}
      <div
        style={{
          background: "#fff",
          borderRadius: "0.75rem",
          padding: "1.25rem",
          boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
          minHeight: "500px",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1rem",
          }}
        >
          <h3 style={{ margin: 0, fontSize: "1rem", color: "#333" }}>
            分析结果
          </h3>
          {elapsed && (
            <span style={{ fontSize: "0.75rem", color: "#999" }}>
              耗时: {elapsed.toFixed(2)}s
            </span>
          )}
        </div>

        {loading && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              minHeight: "400px",
              color: "#999",
            }}
          >
            <div
              style={{
                width: "40px",
                height: "40px",
                border: `3px solid #f0f0f0`,
                borderTop: `3px solid ${agentColor}`,
                borderRadius: "50%",
                animation: "spin 1s linear infinite",
                marginBottom: "1rem",
              }}
            />
            <p>AI 正在分析数据，请稍候...</p>
            <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {!loading && !result && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              minHeight: "400px",
              color: "#bbb",
            }}
          >
            <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📊</div>
            <p>点击左侧"运行分析"按钮开始</p>
            <p style={{ fontSize: "0.8rem" }}>AI 将基于上下文数据提供结构化分析</p>
          </div>
        )}

        {!loading && result && (
          <div style={{ overflow: "auto" }}>
            {/* 摘要 */}
            <div
              style={{
                padding: "1rem",
                background: `${agentColor}11`,
                borderRadius: "0.5rem",
                marginBottom: "1rem",
                borderLeft: `3px solid ${agentColor}`,
              }}
            >
              <div style={{ fontSize: "0.75rem", color: agentColor, fontWeight: 600, marginBottom: "0.35rem" }}>
                📋 分析摘要
              </div>
              <div style={{ fontSize: "0.85rem", color: "#333", lineHeight: 1.6 }}>
                {result.summary}
              </div>
            </div>

            {/* 置信度 */}
            {result.confidence_score !== undefined && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.75rem",
                  marginBottom: "1rem",
                  padding: "0.75rem",
                  background: "#f9f9f9",
                  borderRadius: "0.5rem",
                }}
              >
                <span style={{ fontSize: "0.8rem", color: "#666" }}>置信度:</span>
                <div style={{ flex: 1, height: "8px", background: "#e0e0e0", borderRadius: "4px", overflow: "hidden" }}>
                  <div
                    style={{
                      width: `${(result.confidence_score * 100).toFixed(0)}%`,
                      height: "100%",
                      background: agentColor,
                      borderRadius: "4px",
                    }}
                  />
                </div>
                <span style={{ fontSize: "0.85rem", fontWeight: 600, color: agentColor }}>
                  {(result.confidence_score * 100).toFixed(0)}%
                </span>
              </div>
            )}

            {/* 各字段结果 */}
            {resultKeys.map(({ key, label, type }) => (
              <div key={key} style={{ marginBottom: "1rem" }}>
                <div
                  style={{
                    fontSize: "0.8rem",
                    fontWeight: 600,
                    color: "#555",
                    marginBottom: "0.5rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                  }}
                >
                  {label}
                </div>
                {renderValue(result[key], type)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
