import { afterEach, describe, expect, it, vi } from "vitest";

import { request } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("API authorization headers", () => {
  it("omits Authorization for public demo requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("[]", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await request("/api/v1/demo/documents", undefined);

    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(requestInit.headers).has("Authorization")).toBe(false);
  });

  it("adds the current access token for private requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("[]", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await request("/api/v1/workspaces", "current-access-token");

    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(requestInit.headers).get("Authorization")).toBe(
      "Bearer current-access-token",
    );
  });
});
