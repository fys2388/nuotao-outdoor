import { useEffect, useState } from "react";
import { productApi, Product, productAnalystApi, ProductAnalysisResult } from "../api/client";

export function Products() {
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [analysisResult, setAnalysisResult] = useState<ProductAnalysisResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadProducts() {
      setLoading(true);
      const res = await productApi.list();
      if (res.data) setProducts(res.data);
      setLoading(false);
    }
    loadProducts();
  }, []);

  const handleAnalyze = async (productId: string) => {
    setAnalyzing(true);
    setAnalysisResult(null);
    const res = await productAnalystApi.analyze(productId);
    if (res.data) setAnalysisResult(res.data);
    setAnalyzing(false);
  };

  if (loading) {
    return <div style={{ padding: "2rem", color: "#666" }}>加载中...</div>;
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
      {/* Product List */}
      <div style={{ background: "#fff", borderRadius: "0.75rem", padding: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
        <h3 style={{ margin: "0 0 1rem 0", fontSize: "1rem", color: "#333" }}>产品列表 ({products.length})</h3>
        <div style={{ maxHeight: 500, overflowY: "auto" }}>
          {products.length === 0 ? (
            <div style={{ color: "#999", fontSize: "0.85rem" }}>暂无产品</div>
          ) : (
            products.map((product) => (
              <div
                key={product.id}
                onClick={() => setSelectedProduct(product)}
                style={{
                  padding: "1rem",
                  marginBottom: "0.5rem",
                  borderRadius: "0.5rem",
                  cursor: "pointer",
                  background: selectedProduct?.id === product.id ? "#e3f2fd" : "#f9f9f9",
                  border: selectedProduct?.id === product.id ? "1px solid #2196f3" : "1px solid transparent",
                  transition: "all 0.15s",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: "0.9rem", fontWeight: 500, color: "#333" }}>{product.name}</div>
                    <div style={{ fontSize: "0.75rem", color: "#999", marginTop: "0.25rem" }}>SKU: {product.sku}</div>
                    {product.category && (
                      <div style={{ fontSize: "0.75rem", color: "#666", marginTop: "0.25rem" }}>分类: {product.category}</div>
                    )}
                  </div>
                  <span
                    style={{
                      background: product.status === "active" ? "#e8f5e9" : "#fff3e0",
                      color: product.status === "active" ? "#2e7d32" : "#e65100",
                      padding: "0.2rem 0.6rem",
                      borderRadius: "1rem",
                      fontSize: "0.65rem",
                      fontWeight: 500,
                    }}
                  >
                    {product.status}
                  </span>
                </div>
                {(product.cost_price || product.sale_price) && (
                  <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem", fontSize: "0.75rem" }}>
                    {product.cost_price && <span style={{ color: "#666" }}>成本: ${product.cost_price}</span>}
                    {product.sale_price && <span style={{ color: "#2e7d32", fontWeight: 500 }}>售价: ${product.sale_price}</span>}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Product Detail & Analysis */}
      <div style={{ background: "#fff", borderRadius: "0.75rem", padding: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
        <h3 style={{ margin: "0 0 1rem 0", fontSize: "1rem", color: "#333" }}>产品详情</h3>
        {!selectedProduct ? (
          <div style={{ color: "#999", fontSize: "0.85rem", textAlign: "center", padding: "2rem" }}>
            请从左侧选择一个产品
          </div>
        ) : (
          <div>
            <div style={{ marginBottom: "1rem" }}>
              <h4 style={{ margin: "0 0 0.5rem 0", color: "#333" }}>{selectedProduct.name}</h4>
              <div style={{ fontSize: "0.8rem", color: "#666", lineHeight: 1.6 }}>
                <div><strong>SKU:</strong> {selectedProduct.sku}</div>
                <div><strong>ID:</strong> {selectedProduct.id}</div>
                <div><strong>状态:</strong> {selectedProduct.status}</div>
                {selectedProduct.category && <div><strong>分类:</strong> {selectedProduct.category}</div>}
                {selectedProduct.description && <div><strong>描述:</strong> {selectedProduct.description}</div>}
                {selectedProduct.source && <div><strong>来源:</strong> {selectedProduct.source}</div>}
              </div>
            </div>

            <button
              onClick={() => handleAnalyze(selectedProduct.id)}
              disabled={analyzing}
              style={{
                width: "100%",
                padding: "0.75rem",
                background: analyzing ? "#ccc" : "#2196f3",
                color: "#fff",
                border: "none",
                borderRadius: "0.5rem",
                fontSize: "0.9rem",
                cursor: analyzing ? "not-allowed" : "pointer",
                marginBottom: "1rem",
              }}
            >
              {analyzing ? "AI 分析中..." : "🤖 运行产品分析师 AI"}
            </button>

            {analysisResult && (
              <div style={{ background: "#f9f9f9", borderRadius: "0.5rem", padding: "1rem", fontSize: "0.8rem" }}>
                <h4 style={{ margin: "0 0 0.75rem 0", color: "#333" }}>AI 分析结果</h4>
                <div style={{ lineHeight: 1.8, color: "#555" }}>
                  <div><strong>状态:</strong> {analysisResult.status}</div>
                  <div><strong>决策:</strong> {analysisResult.decision || "N/A"}</div>
                  <div><strong>置信度:</strong> {analysisResult.confidence ? (analysisResult.confidence * 100).toFixed(1) + "%" : "N/A"}</div>
                  {analysisResult.recommended_price && <div><strong>建议售价:</strong> ${analysisResult.recommended_price}</div>}
                  {analysisResult.max_cac && <div><strong>最大获客成本:</strong> ${analysisResult.max_cac}</div>}
                  <div><strong>模型:</strong> {analysisResult.provider}/{analysisResult.model}</div>
                  <div><strong>耗时:</strong> {analysisResult.latency_ms}ms</div>
                  <div><strong>成本:</strong> ${analysisResult.estimated_cost?.toFixed(6)}</div>
                  <div><strong>审批状态:</strong> {analysisResult.approval_status || "N/A"}</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
