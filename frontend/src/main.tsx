import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

// M0 placeholder entrypoint; real console routes arrive in M1.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);