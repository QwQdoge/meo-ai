import React from "react";
import { createRoot } from "react-dom/client";
import CoreApp from "./core/CoreApp";
import "./theme.css";

// The page renders the shared Rust core (compiled to WASM); see ./core.
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <CoreApp />
  </React.StrictMode>,
);
