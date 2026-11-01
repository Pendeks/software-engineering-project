import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  formatBytes,
  request,
  statusLabel,
  type Answer,
  type DocumentRecord,
  type Workspace,
} from "./api";
import {
  authConfigurationError,
  getAccessToken,
  getAuthMode,
  hasSignedInAccount,
  signInWithMicrosoft,
  signOutFromMicrosoft,
} from "./auth";

type IconName =
  | "spark"
  | "file"
  | "upload"
  | "arrow"
  | "plus"
  | "refresh"
  | "trash"
  | "lock"
  | "book"
  | "chevron";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}

function requestPrivate<T>(
  path: string,
  localToken: string | null,
  init: RequestInit = {},
): Promise<T> {
  const tokenPromise =
    getAuthMode() === "entra" ? getAccessToken() : Promise.resolve(localToken ?? undefined);
  return tokenPromise.then((token) => request<T>(path, token, init));
}

function DemoExperience({ onBack }: { onBack: () => void }) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    request<DocumentRecord[]>("/api/v1/demo/documents")
      .then((items) => {
        if (active) setDocuments(items);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      });
    return () => {
      active = false;
    };
  }, []);

  const hasActiveJobs = documents.some(
    (document) => document.status === "queued" || document.status === "processing",
  );
  useEffect(() => {
    if (!hasActiveJobs) return;
    let active = true;
    const timer = window.setInterval(() => {
    request<DocumentRecord[]>("/api/v1/demo/documents")
      .then((items) => {
        if (active) setDocuments(items);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      });
    }, 4000);
    return () => {
    active = false;
    window.clearInterval(timer);
    };
  }, [hasActiveJobs]);

  async function askQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError("");
    setAnswer(null);
    try {
      const result = await request<Answer>(
        "/api/v1/demo/questions",
        undefined,
        { method: "POST", body: JSON.stringify({ question: question.trim() }) },
      );
      setAnswer(result);
      setQuestion("");
    } catch (reason: unknown) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const readyDocuments = documents.filter((document) => document.status === "ready");

  return (
    <main className="demo-page">
      <header className="demo-topbar">
        <a className="brand" href="#" aria-label="DocuMind home">
          <span className="brand-mark"><Icon name="spark" size={19} /></span>
          <span>DocuMind</span>
        </a>
        <button className="text-button" onClick={onBack} type="button">Back</button>
      </header>
      <section className="demo-content">
        <p className="eyebrow">PUBLIC DEMO</p>
        <h1>Explore DocuMind with sample documents.</h1>
        <p className="page-subtitle">
          This read-only demo uses synthetic content. Your private workspaces are not shown here.
        </p>
        {error && <p className="inline-error" role="alert">{error}</p>}
        <div className="demo-card">
          <div className="section-heading">
            <div><h2>Sample documents</h2><span>{documents.length} files</span></div>
          </div>
          {documents.length === 0 ? (
            <p className="demo-empty">The sample library is not available yet.</p>
          ) : (
            <ul className="document-list">
              {documents.map((document) => (
                <li className="document-row" key={document.id}>
                  <div className="document-file-icon"><Icon name="file" size={19} /></div>
                  <div className="document-info">
                    <strong>{document.filename}</strong>
                    <span>{statusLabel(document.status)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="demo-card">
          <h2>Ask the sample documents</h2>
          {answer && (
            <div className="answer-card" aria-live="polite">
              <p className="answer-label">{answer.abstained ? "NOT ENOUGH EVIDENCE" : "ANSWER"}</p>
              <p className={answer.abstained ? "answer-text abstained" : "answer-text"}>
                {answer.answer}
              </p>
              {!answer.abstained && answer.citations.map((citation) => (
                <article className="citation-card" key={`${citation.document_version_id}-${citation.citation_number}`}>
                  <div className="citation-title">
                    <span>[{citation.citation_number}]</span><strong>{citation.filename}</strong>
                  </div>
                  <p>“{citation.excerpt}”</p>
                </article>
              ))}
            </div>
          )}
          <form className="question-form" onSubmit={askQuestion}>
            <label className="sr-only" htmlFor="demo-question-input">Ask a question</label>
            <textarea
              id="demo-question-input"
              rows={3}
              maxLength={2000}
              placeholder="Ask a question about the sample documents…"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              disabled={!readyDocuments.length || busy}
            />
            <div className="question-form-footer">
              <span>{readyDocuments.length ? "Only sample documents are searched" : "Sample documents are being prepared"}</span>
              <button
                className="send-button"
                disabled={!readyDocuments.length || !question.trim() || busy}
                type="submit"
                aria-label="Send question"
              >
                {busy ? <span className="status-spinner" /> : <Icon name="arrow" size={17} />}
              </button>
            </div>
          </form>
        </div>
      </section>
    </main>
  );
}

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, string> = {
    spark: "M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2L12 3zm7 11l1.1 2.9L23 18l-2.9 1.1L19 22l-1.1-2.9L15 18l2.9-1.1L19 14z",
    file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zm0 1v5h5M8 13h8M8 17h8",
    upload: "M12 16V4m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4",
    arrow: "M5 12h14m-6-6 6 6-6 6",
    plus: "M12 5v14m-7-7h14",
    refresh: "M20 7v5h-5M4 17v-5h5m10-3a7 7 0 0 0-12-2L4 12m16 0-3 5a7 7 0 0 1-12-2",
    trash: "M3 6h18m-2 0-1 14H6L5 6m3 0V4h8v2m-7 4v6m4-6v6",
    lock: "M5 11h14v10H5zm3 0V7a4 4 0 1 1 8 0v4m-4 4v2",
    book: "M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 0 4 22zm0 0V22m4-15h8m-8 4h8",
    chevron: "m9 18 6-6-6-6",
  };
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name]} />
    </svg>
  );
}

function App({ startupError = "" }: { startupError?: string }) {
  const [tokenDraft, setTokenDraft] = useState("");
  const [apiToken, setApiToken] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(
    getAuthMode() === "entra" && hasSignedInAccount(),
  );
  const [demoMode, setDemoMode] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [workspaceName, setWorkspaceName] = useState("");
  const [showWorkspaceForm, setShowWorkspaceForm] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState(startupError || authConfigurationError);
  const [notice, setNotice] = useState("");

  const isConnected = getAuthMode() === "entra" ? signedIn : apiToken !== null;
  const currentWorkspace = workspaces.find((workspace) => workspace.id === workspaceId);
  const readyCount = useMemo(
    () => documents.filter((document) => document.status === "ready").length,
    [documents],
  );

  useEffect(() => {
    if (!isConnected) return;
    let active = true;
    requestPrivate<Workspace[]>("/api/v1/workspaces", apiToken)
      .then((items) => {
        if (!active) return;
        setWorkspaces(items);
        setWorkspaceId((selected) =>
          items.some((workspace) => workspace.id === selected)
            ? selected
            : (items[0]?.id ?? ""),
        );
        setError("");
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      });
    return () => {
      active = false;
    };
  }, [apiToken, isConnected]);

  useEffect(() => {
    if (!isConnected || !workspaceId) {
      setDocuments([]);
      setAnswer(null);
      return;
    }
    let active = true;
    const load = () =>
      requestPrivate<DocumentRecord[]>(
        `/api/v1/workspaces/${workspaceId}/documents`,
        apiToken,
      )
        .then((items) => {
          if (active) setDocuments(items);
        })
        .catch((reason: unknown) => {
          if (active) setError(errorMessage(reason));
        });
    void load();
    return () => {
      active = false;
    };
  }, [apiToken, isConnected, workspaceId]);

  const hasActiveJobs = documents.some(
    (document) => document.status === "queued" || document.status === "processing",
  );
  useEffect(() => {
    if (!isConnected || !workspaceId || !hasActiveJobs) return;
    let active = true;
    const timer = window.setInterval(() => {
      requestPrivate<DocumentRecord[]>(
        `/api/v1/workspaces/${workspaceId}/documents`,
        apiToken,
      )
        .then((items) => {
          if (active) setDocuments(items);
        })
        .catch((reason: unknown) => {
          if (active) setError(errorMessage(reason));
        });
    }, 4000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [apiToken, hasActiveJobs, isConnected, workspaceId]);

  function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tokenDraft.trim()) return;
    setError("");
    setApiToken(tokenDraft.trim());
  }

  async function connectWithMicrosoft() {
    setError("");
    try {
      await signInWithMicrosoft();
      setSignedIn(true);
    } catch (reason: unknown) {
      setError(errorMessage(reason));
    }
  }

  async function disconnect() {
    if (getAuthMode() === "entra") {
      try {
        await signOutFromMicrosoft();
      } catch (reason: unknown) {
        setError(errorMessage(reason));
        return;
      }
      setSignedIn(false);
    }
    setApiToken(null);
    setTokenDraft("");
    setWorkspaces([]);
    setWorkspaceId("");
    setDocuments([]);
    setAnswer(null);
    setError("");
    setNotice("");
  }

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isConnected || !workspaceName.trim()) return;
    setBusyAction("workspace");
    setError("");
    try {
      const workspace = await requestPrivate<Workspace>("/api/v1/workspaces", apiToken, {
        method: "POST",
        body: JSON.stringify({ name: workspaceName.trim() }),
      });
      setWorkspaces((items) => [...items, workspace]);
      setWorkspaceId(workspace.id);
      setWorkspaceName("");
      setShowWorkspaceForm(false);
      setNotice("Your workspace is ready.");
    } catch (reason: unknown) {
      setError(errorMessage(reason));
    } finally {
      setBusyAction("");
    }
  }

  async function refreshDocuments() {
    if (!isConnected || !workspaceId) return;
    setBusyAction("refresh");
    setError("");
    try {
      setDocuments(
        await requestPrivate<DocumentRecord[]>(
          `/api/v1/workspaces/${workspaceId}/documents`,
          apiToken,
        ),
      );
    } catch (reason: unknown) {
      setError(errorMessage(reason));
    } finally {
      setBusyAction("");
    }
  }

  async function uploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isConnected || !workspaceId || !selectedFile) return;
    setBusyAction("upload");
    setError("");
    setNotice("");
    const form = new FormData();
    form.append("file", selectedFile);
    try {
      const uploadedDocument = await requestPrivate<DocumentRecord>(
        `/api/v1/workspaces/${workspaceId}/documents`,
        apiToken,
        { method: "POST", body: form },
      );
      setDocuments((items) => [uploadedDocument, ...items]);
      setSelectedFile(null);
      const input = window.document.getElementById("document-file") as HTMLInputElement | null;
      if (input) input.value = "";
      setNotice("Upload complete. Indexing will begin in the background.");
    } catch (reason: unknown) {
      setError(errorMessage(reason));
    } finally {
      setBusyAction("");
    }
  }

  async function deleteDocument(document: DocumentRecord) {
    if (!isConnected || !workspaceId) return;
    if (!window.confirm(`Remove “${document.filename}” and its indexed content?`)) return;
    setBusyAction(`delete-${document.id}`);
    setError("");
    try {
      await requestPrivate<void>(
        `/api/v1/workspaces/${workspaceId}/documents/${document.id}`,
        apiToken,
        { method: "DELETE" },
      );
      setDocuments((items) => items.filter((item) => item.id !== document.id));
      setNotice("Document removed.");
    } catch (reason: unknown) {
      setError(errorMessage(reason));
    } finally {
      setBusyAction("");
    }
  }

  async function retryDocument(document: DocumentRecord) {
    if (!isConnected || !workspaceId) return;
    setBusyAction(`retry-${document.id}`);
    setError("");
    try {
      await requestPrivate(
        `/api/v1/workspaces/${workspaceId}/documents/${document.id}/process`,
        apiToken,
        { method: "POST" },
      );
      await refreshDocuments();
      setNotice("Processing has been queued for retry.");
    } catch (reason: unknown) {
      setError(errorMessage(reason));
    } finally {
      setBusyAction("");
    }
  }

  async function askQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isConnected || !workspaceId || !question.trim()) return;
    setBusyAction("question");
    setError("");
    setAnswer(null);
    try {
      const result = await requestPrivate<Answer>(
        `/api/v1/workspaces/${workspaceId}/questions`,
        apiToken,
        { method: "POST", body: JSON.stringify({ question: question.trim() }) },
      );
      setAnswer(result);
      setQuestion("");
    } catch (reason: unknown) {
      setError(errorMessage(reason));
    } finally {
      setBusyAction("");
    }
  }

  if (demoMode) {
    return <DemoExperience onBack={() => setDemoMode(false)} />;
  }

  if (!isConnected) {
    return (
      <main className="connect-page">
        <div className="connect-brand">
          <span className="brand-mark"><Icon name="spark" size={21} /></span>
          DocuMind
        </div>
        <section className="connect-card">
          <p className="eyebrow">YOUR KNOWLEDGE, IN CONTEXT</p>
          <h1>Good answers start with trusted sources.</h1>
          <p className="connect-copy">
            Bring your team’s documents together and ask questions with answers you can trace
            back to the page.
          </p>
          {getAuthMode() === "local" ? (
            <form className="connect-form" onSubmit={connect}>
              <label htmlFor="api-token">Local API bearer token</label>
              <input
                id="api-token"
                type="password"
                autoComplete="off"
                value={tokenDraft}
                onChange={(event) => setTokenDraft(event.target.value)}
                placeholder="Paste your development token"
                required
              />
              <button className="button button-primary button-wide" type="submit">
                Connect securely <Icon name="arrow" size={17} />
              </button>
              {error && <p className="inline-error" role="alert">{error}</p>}
            </form>
          ) : (
            <div className="connect-form">
              <button
                className="button button-primary button-wide"
                onClick={() => void connectWithMicrosoft()}
                type="button"
                disabled={Boolean(authConfigurationError)}
              >
                Sign in with Microsoft <Icon name="arrow" size={17} />
              </button>
              {error && <p className="inline-error" role="alert">{error}</p>}
            </div>
          )}
          {getAuthMode() === "local" && (
            <p className="privacy-note"><Icon name="lock" size={15} /> Token stays in memory and clears when you disconnect.</p>
          )}
          <button
            className="button button-secondary button-wide demo-entry"
            onClick={() => setDemoMode(true)}
            type="button"
          >
            Try the demo
          </button>
        </section>
        <p className="connect-foot">A private space for the knowledge your team already owns.</p>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="DocuMind home">
          <span className="brand-mark"><Icon name="spark" size={19} /></span>
          <span>DocuMind</span>
        </a>
        <div className="sidebar-label">YOUR WORKSPACES</div>
        <label className="sr-only" htmlFor="workspace-select">Select workspace</label>
        <div className="select-wrap">
          <select
            id="workspace-select"
            value={workspaceId}
            onChange={(event) => setWorkspaceId(event.target.value)}
          >
            <option value="">Choose a workspace</option>
            {workspaces.map((workspace) => (
              <option value={workspace.id} key={workspace.id}>{workspace.name}</option>
            ))}
          </select>
          <Icon name="chevron" size={15} />
        </div>
        <button className="sidebar-create" onClick={() => setShowWorkspaceForm(true)} type="button">
          <Icon name="plus" size={16} /> New workspace
        </button>
        {showWorkspaceForm && (
          <form className="workspace-form" onSubmit={createWorkspace}>
            <label htmlFor="workspace-name">Workspace name</label>
            <input
              id="workspace-name"
              autoFocus
              maxLength={120}
              value={workspaceName}
              onChange={(event) => setWorkspaceName(event.target.value)}
              placeholder="e.g. Product handbook"
              required
            />
            <div className="workspace-form-actions">
              <button className="text-button" type="button" onClick={() => setShowWorkspaceForm(false)}>Cancel</button>
              <button className="button button-primary button-small" disabled={busyAction === "workspace"} type="submit">
                {busyAction === "workspace" ? "Creating…" : "Create"}
              </button>
            </div>
          </form>
        )}
        <div className="sidebar-bottom">
          <div className="private-badge"><Icon name="lock" size={15} /><span>Private to your workspace</span></div>
          <button className="disconnect-button" onClick={() => void disconnect()} type="button">
            {getAuthMode() === "entra" ? "Sign out" : "Disconnect token"}
          </button>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumb">Workspace <Icon name="chevron" size={14} /> <strong>{currentWorkspace?.name ?? "Select a workspace"}</strong></div>
          <div className="topbar-right"><span className="secure-indicator"><span /> Private workspace</span><button className="mobile-disconnect" onClick={() => void disconnect()} type="button">Disconnect</button></div>
        </header>
        {error && <div className="toast toast-error" role="alert">{error}<button onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}
        {notice && <div className="toast toast-success" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Dismiss notice">×</button></div>}

        {!workspaces.length ? (
          <section className="welcome-empty">
            <span className="empty-icon"><Icon name="book" size={25} /></span>
            <p className="eyebrow">A FRESH START</p>
            <h1>Create your first knowledge space.</h1>
            <p>Keep documents organized by team, project, or topic. Only workspace members can search its content.</p>
            <button className="button button-primary" onClick={() => setShowWorkspaceForm(true)} type="button">
              <Icon name="plus" size={17} /> Create a workspace
            </button>
          </section>
        ) : !workspaceId ? (
          <section className="welcome-empty"><h1>Choose a workspace to get started.</h1></section>
        ) : (
          <div className="content-grid">
            <section className="library-column">
              <div className="page-heading">
                <div>
                  <p className="eyebrow">YOUR TEAM’S KNOWLEDGE</p>
                  <h1>{currentWorkspace?.name}</h1>
                  <p className="page-subtitle">Bring your documents together. Find answers with their sources attached.</p>
                </div>
                <div className="heading-art"><Icon name="spark" size={26} /></div>
              </div>

              <div className="stats-row" aria-label="Workspace document summary">
                <div className="stat-card"><span className="stat-value">{documents.length}</span><span className="stat-label">Documents</span></div>
                <div className="stat-card"><span className="stat-value">{readyCount}</span><span className="stat-label">Ready to search</span></div>
                <div className="stat-card"><span className="stat-value">{documents.filter((doc) => doc.status === "queued" || doc.status === "processing").length}</span><span className="stat-label">Indexing</span></div>
              </div>

              <form className="upload-card" onSubmit={uploadDocument}>
                <div className="upload-icon"><Icon name="upload" size={20} /></div>
                <div className="upload-copy">
                  <strong>Add to your knowledge base</strong>
                  <span>PDF, DOCX, TXT or Markdown · up to 10 MB</span>
                </div>
                <label className="button button-secondary choose-file" htmlFor="document-file">
                  {selectedFile ? "Choose another" : "Choose file"}
                </label>
                <input
                  className="sr-only"
                  id="document-file"
                  type="file"
                  accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
                  onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                />
                {selectedFile && (
                  <div className="selected-file">
                    <span><Icon name="file" size={16} /> {selectedFile.name} <small>{formatBytes(selectedFile.size)}</small></span>
                    <button className="button button-primary button-small" disabled={busyAction === "upload"} type="submit">
                      {busyAction === "upload" ? "Uploading…" : "Upload"}
                    </button>
                  </div>
                )}
              </form>

              <div className="section-heading">
                <div><h2>Your documents</h2><span>{documents.length} {documents.length === 1 ? "file" : "files"}</span></div>
                <button className="icon-button" onClick={refreshDocuments} disabled={busyAction === "refresh"} type="button" aria-label="Refresh documents" title="Refresh">
                  <Icon name="refresh" size={17} />
                </button>
              </div>

              {documents.length === 0 ? (
                <div className="documents-empty">
                  <span className="empty-icon small"><Icon name="file" size={20} /></span>
                  <strong>Your library is ready for its first document.</strong>
                  <span>Upload a file to start building a searchable knowledge base.</span>
                </div>
              ) : (
                <ul className="document-list">
                  {documents.map((document) => (
                    <li className="document-row" key={document.id}>
                      <div className="document-file-icon"><Icon name="file" size={19} /></div>
                      <div className="document-info">
                        <strong title={document.filename}>{document.filename}</strong>
                        <span>{formatBytes(document.file_size)} <span className="dot-separator">·</span> Added {new Date(document.created_at).toLocaleDateString()}</span>
                        {document.processing_error && <span className="document-error">{document.processing_error}</span>}
                      </div>
                      <span className={`status-pill status-${document.status}`}>
                        {document.status === "queued" || document.status === "processing" ? <span className="status-spinner" /> : null}
                        {statusLabel(document.status)}
                      </span>
                      {document.status === "failed" && (
                        <button className="text-button retry-button" disabled={busyAction === `retry-${document.id}`} onClick={() => void retryDocument(document)} type="button">
                          Retry
                        </button>
                      )}
                      <button className="icon-button delete-button" disabled={busyAction === `delete-${document.id}`} onClick={() => void deleteDocument(document)} type="button" aria-label={`Remove ${document.filename}`} title="Remove document">
                        <Icon name="trash" size={16} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="library-footnote"><Icon name="lock" size={14} /> Your files stay private. Only indexed passages are used to answer questions.</p>
            </section>

            <aside className="ask-panel" aria-labelledby="ask-title">
              <div className="ask-header">
                <span className="ask-symbol"><Icon name="spark" size={18} /></span>
                <div><h2 id="ask-title">Ask your documents</h2><p>Answers grounded in your sources</p></div>
              </div>
              {!answer ? (
                <>
                  <div className="ask-intro">
                    <span className="ask-orb"><Icon name="spark" size={23} /></span>
                    <h3>What would you like to know?</h3>
                    <p>Ask a question about the indexed documents in this workspace.</p>
                  </div>
                  <div className="suggestion-label">TRY ASKING</div>
                  <div className="suggestion-list">
                    {[
                      "What are the key points?",
                      "Summarize the latest guidance",
                      "What should I know before getting started?",
                    ].map((suggestion) => (
                      <button className="suggestion" key={suggestion} onClick={() => setQuestion(suggestion)} type="button">
                        {suggestion}<Icon name="arrow" size={15} />
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <div className="answer-card" aria-live="polite">
                  <p className="answer-label">{answer.abstained ? "NOT ENOUGH EVIDENCE" : "ANSWER"}</p>
                  <p className={answer.abstained ? "answer-text abstained" : "answer-text"}>{answer.answer}</p>
                  {!answer.abstained && answer.citations.length > 0 && (
                    <div className="citation-section">
                      <p className="citation-heading"><Icon name="book" size={15} /> SOURCES USED</p>
                      {answer.citations.map((citation) => (
                        <article className="citation-card" key={`${citation.document_version_id}-${citation.citation_number}`}>
                          <div className="citation-title"><span>[{citation.citation_number}]</span><strong>{citation.filename}</strong></div>
                          <p>“{citation.excerpt}”</p>
                          <small>{citation.page_number ? `Page ${citation.page_number} · ` : ""}Lines {citation.start_offset}–{citation.end_offset}</small>
                        </article>
                      ))}
                    </div>
                  )}
                  <button className="ask-again" onClick={() => setAnswer(null)} type="button">Ask another question</button>
                </div>
              )}
              <form className="question-form" onSubmit={askQuestion}>
                <label className="sr-only" htmlFor="question-input">Ask a question about your documents</label>
                <textarea
                  id="question-input"
                  rows={3}
                  maxLength={2000}
                  placeholder="Ask anything about your documents…"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  disabled={!readyCount || busyAction === "question"}
                />
                <div className="question-form-footer">
                  <span>{readyCount ? "Only indexed documents are searched" : "Upload and index a document to ask"}</span>
                  <button className="send-button" disabled={!readyCount || !question.trim() || busyAction === "question"} type="submit" aria-label="Send question">
                    {busyAction === "question" ? <span className="status-spinner" /> : <Icon name="arrow" size={17} />}
                  </button>
                </div>
              </form>
              <p className="answer-disclaimer"><Icon name="lock" size={13} /> Answers can be wrong. Check the cited source.</p>
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
