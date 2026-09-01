import { useState } from "react";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Products } from "./pages/Products";
import { AIAnalysis } from "./pages/AIAnalysis";
import { Agents } from "./pages/Agents";
import { Events } from "./pages/Events";
import { Rules } from "./pages/Rules";
import { System } from "./pages/System";

export function App() {
  const [currentPage, setCurrentPage] = useState("dashboard");

  const renderPage = () => {
    switch (currentPage) {
      case "dashboard":
        return <Dashboard />;
      case "products":
        return <Products />;
      case "ai-analysis":
        return <AIAnalysis />;
      case "agents":
        return <Agents />;
      case "events":
        return <Events />;
      case "rules":
        return <Rules />;
      case "system":
        return <System />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <Layout currentPage={currentPage} onNavigate={setCurrentPage}>
      {renderPage()}
    </Layout>
  );
}
