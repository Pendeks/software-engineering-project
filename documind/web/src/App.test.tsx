import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getAccessToken,
  getAuthMode,
  hasSignedInAccount,
} from "./auth";
import App from "./App";

vi.mock("./auth", () => ({
  authConfigurationError: "",
  getAccessToken: vi.fn(),
  getAuthMode: vi.fn(),
  hasSignedInAccount: vi.fn(),
  signInWithMicrosoft: vi.fn(),
  signOutFromMicrosoft: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("DocuMind entry experiences", () => {
  it("renders Microsoft sign-in and public demo choices in Entra mode", () => {
    vi.mocked(getAuthMode).mockReturnValue("entra");
    vi.mocked(hasSignedInAccount).mockReturnValue(false);

    render(<App />);

    expect(
      screen.getByRole("button", { name: /sign in with microsoft/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try the demo/i })).toBeInTheDocument();
  });

  it("keeps the development token form in local mode", () => {
    vi.mocked(getAuthMode).mockReturnValue("local");

    render(<App />);

    expect(screen.getByLabelText(/local api bearer token/i)).toBeInTheDocument();
  });

  it("uses an acquired access token for private workspace requests", async () => {
    vi.mocked(getAuthMode).mockReturnValue("entra");
    vi.mocked(hasSignedInAccount).mockReturnValue(true);
    vi.mocked(getAccessToken).mockResolvedValue("acquired-token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ id: "private-workspace", name: "Private" }]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await screen.findByRole("option", { name: "Private" });
    const workspaceRequest = fetchMock.mock.calls.find(
      ([path]) => path === "/api/v1/workspaces",
    )?.[1] as RequestInit | undefined;
    expect(new Headers(workspaceRequest?.headers).get("Authorization")).toBe(
      "Bearer acquired-token",
    );
  });

  it("lists and asks demo questions without sending authorization", async () => {
    vi.mocked(getAuthMode).mockReturnValue("entra");
    vi.mocked(hasSignedInAccount).mockReturnValue(false);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify([
            {
              id: "demo-document",
              workspace_id: "recruiter-demo",
              filename: "recruiter-demo-handbook.txt",
              mime_type: "text/plain",
              file_size: 20,
              sha256: "0".repeat(64),
              status: "ready",
              processing_error: null,
              created_at: "2026-01-01T00:00:00Z",
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            answer: "The emergency lantern is amber [1].",
            abstained: false,
            citations: [
              {
                citation_number: 1,
                document_id: "demo-document",
                document_version_id: "demo-version",
                filename: "recruiter-demo-handbook.txt",
                page_number: null,
                start_offset: 0,
                end_offset: 20,
                excerpt: "The Aurora archive keeps its emergency lantern amber.",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /try the demo/i }));

    expect(await screen.findByText("PUBLIC DEMO")).toBeInTheDocument();
    expect(
      await screen.findByText("recruiter-demo-handbook.txt"),
    ).toBeInTheDocument();
    const questionField = screen.getByRole("textbox", { name: /ask a question/i });
    fireEvent.change(questionField, {
      target: { value: "What color is the emergency lantern?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send question/i }));

    expect(
      await screen.findByText("The emergency lantern is amber [1]."),
    ).toBeInTheDocument();
    for (const [path, init] of fetchMock.mock.calls as [string, RequestInit][]) {
      if (path === "/api/v1/demo/documents" || path === "/api/v1/demo/questions") {
        expect(new Headers(init.headers).get("Authorization")).toBeNull();
      }
    }
    expect(screen.queryByRole("button", { name: /upload/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /new workspace/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
    expect(screen.getAllByText("recruiter-demo-handbook.txt")).toHaveLength(2);
  });

  it("refreshes demo documents while the sample is being indexed", async () => {
    vi.mocked(getAuthMode).mockReturnValue("local");
    const queuedDocument = {
      id: "demo-document",
      workspace_id: "recruiter-demo",
      filename: "recruiter-demo-handbook.txt",
      mime_type: "text/plain",
      file_size: 20,
      sha256: "0".repeat(64),
      status: "queued",
      processing_error: null,
      created_at: "2026-01-01T00:00:00Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify([queuedDocument]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([{ ...queuedDocument, status: "ready" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    const intervalSpy = vi.spyOn(window, "setInterval");
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /try the demo/i }));
    await screen.findByText("Queued");
    const intervalCall = await waitFor(() =>
      intervalSpy.mock.calls.find(([, intervalMs]) => intervalMs === 4000),
    );
    expect(intervalCall).toBeDefined();
    const poll = intervalCall?.[0];
    if (typeof poll !== "function") throw new Error("Demo polling callback was not registered.");

    await act(async () => {
      poll();
      await Promise.resolve();
    });

    expect(await screen.findByText("Indexed")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /ask a question/i })).toBeEnabled();
  });
});
