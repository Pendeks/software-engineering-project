import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";

describe("production build configuration", () => {
  it("requires an explicit authentication mode", () => {
    const temporaryDirectory = mkdtempSync(join(tmpdir(), "documind-web-build-"));
    const environment: NodeJS.ProcessEnv = { ...process.env };
    delete environment.VITE_DOCUMIND_AUTH_MODE;
    const viteEntrypoint = join(process.cwd(), "node_modules", "vite", "bin", "vite.js");

    try {
      const result = spawnSync(
        process.execPath,
        [
          viteEntrypoint,
          "build",
          "--config",
          "vite.config.ts",
          "--outDir",
          join(temporaryDirectory, "dist"),
        ],
        {
          cwd: process.cwd(),
          env: environment,
          encoding: "utf8",
        },
      );

      expect(result.status).not.toBe(0);
      expect(result.stderr + result.stdout).toContain("VITE_DOCUMIND_AUTH_MODE");
    } finally {
      rmSync(temporaryDirectory, { recursive: true, force: true });
    }
  });

  it("requires complete Entra settings for an Entra build", () => {
    const temporaryDirectory = mkdtempSync(join(tmpdir(), "documind-web-build-"));
    const environment: NodeJS.ProcessEnv = {
      ...process.env,
      VITE_DOCUMIND_AUTH_MODE: "entra",
    };
    delete environment.VITE_ENTRA_TENANT_ID;
    delete environment.VITE_ENTRA_CLIENT_ID;
    delete environment.VITE_ENTRA_API_SCOPE;
    delete environment.VITE_ENTRA_REDIRECT_URI;
    const viteEntrypoint = join(process.cwd(), "node_modules", "vite", "bin", "vite.js");

    try {
      const result = spawnSync(
        process.execPath,
        [
          viteEntrypoint,
          "build",
          "--config",
          "vite.config.ts",
          "--outDir",
          join(temporaryDirectory, "dist"),
        ],
        {
          cwd: process.cwd(),
          env: environment,
          encoding: "utf8",
        },
      );

      expect(result.status).not.toBe(0);
      expect(result.stderr + result.stdout).toContain("VITE_ENTRA_TENANT_ID");
    } finally {
      rmSync(temporaryDirectory, { recursive: true, force: true });
    }
  });
});
