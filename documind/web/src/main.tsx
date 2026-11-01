import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { initializeAuth } from "./auth";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);

function renderApp(startupError = "") {
  root.render(
    <React.StrictMode>
      <App startupError={startupError} />
    </React.StrictMode>,
  );
}

void initializeAuth()
  .then(() => renderApp())
  .catch((error: unknown) => {
    renderApp(
      error instanceof Error
        ? error.message
        : "Authentication could not be initialized.",
    );
  });
