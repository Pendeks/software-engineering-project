import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export function validateBuildConfiguration(
  command: string,
  environment: Record<string, string>,
): void {
  if (command !== "build") return;

  const authMode = environment.VITE_DOCUMIND_AUTH_MODE;
  if (authMode !== "local" && authMode !== "entra") {
    throw new Error(
      "VITE_DOCUMIND_AUTH_MODE must be explicitly set to 'local' or 'entra' for production builds.",
    );
  }

  if (authMode === "entra") {
    const requiredSettings = [
      "VITE_ENTRA_TENANT_ID",
      "VITE_ENTRA_CLIENT_ID",
      "VITE_ENTRA_API_SCOPE",
      "VITE_ENTRA_REDIRECT_URI",
    ];
    const missing = requiredSettings.filter(
      (setting) => !environment[setting]?.trim(),
    );
    if (missing.length > 0) {
      throw new Error(
        `Entra production builds require ${missing.join(", ")}.`,
      );
    }
  }
}

export default defineConfig(({ command, mode }) => {
  const environment = loadEnv(mode, ".", "VITE_");
  validateBuildConfiguration(command, environment);

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": "http://127.0.0.1:8000",
        "/health": "http://127.0.0.1:8000",
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/testSetup.ts"],
      restoreMocks: true,
    },
  };
});
