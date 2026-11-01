export interface Workspace {
  id: string;
  name: string;
}

export interface DocumentRecord {
  id: string;
  workspace_id: string;
  filename: string;
  mime_type: string;
  file_size: number;
  sha256: string;
  status: "queued" | "processing" | "ready" | "failed" | "deleting" | "delete_failed";
  processing_error: string | null;
  created_at: string;
}

export interface Citation {
  citation_number: number;
  document_id: string;
  document_version_id: string;
  filename: string;
  page_number: number | null;
  start_offset: number;
  end_offset: number;
  excerpt: string;
}

export interface Answer {
  answer: string;
  abstained: boolean;
  citations: Citation[];
}

interface ApiError {
  detail?: string;
}

export async function request<T>(
  path: string,
  token?: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.delete("Authorization");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new Error("Could not reach DocuMind. Check that the API is running.");
  }

  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = (await response.json()) as ApiError;
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based error when the server does not return JSON.
    }
    throw new Error(message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function statusLabel(status: DocumentRecord["status"]): string {
  const labels: Record<DocumentRecord["status"], string> = {
    queued: "Queued",
    processing: "Processing",
    ready: "Indexed",
    failed: "Needs attention",
    deleting: "Removing",
    delete_failed: "Remove failed",
  };
  return labels[status];
}
