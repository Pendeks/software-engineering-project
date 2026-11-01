import { waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { appMock, initializeAuthMock, renderMock } = vi.hoisted(() => ({
  appMock: vi.fn(() => null),
  initializeAuthMock: vi.fn(),
  renderMock: vi.fn(),
}));

vi.mock("react-dom/client", () => ({
  createRoot: vi.fn(() => ({ render: renderMock })),
}));
vi.mock("./auth", () => ({ initializeAuth: initializeAuthMock }));
vi.mock("./App", () => ({ default: appMock }));

describe("application startup", () => {
  beforeEach(() => {
    vi.resetModules();
    initializeAuthMock.mockReset();
    renderMock.mockReset();
    document.body.innerHTML = '<div id="root"></div>';
  });

  it("surfaces authentication initialization errors in the app", async () => {
    initializeAuthMock.mockRejectedValue(new Error("Authentication initialization failed."));

    await import("./main");

    await waitFor(() => expect(renderMock).toHaveBeenCalledTimes(1));
    const renderedTree = renderMock.mock.calls[0][0] as ReactElement<{
      children: ReactNode;
    }>;
    const appElement = renderedTree.props.children as ReactElement<{
      startupError: string;
    }>;
    expect(appElement.props.startupError).toBe("Authentication initialization failed.");
  });
});
