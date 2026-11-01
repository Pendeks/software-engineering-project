import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text

from documind.api import create_app
from documind.config import Settings
from documind.database import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from documind.demo_content import (
    DEMO_DOCUMENT_FILENAME,
)
from documind.models import (
    Chunk,
    Document,
    DocumentVersion,
    User,
    Workspace,
)
from documind.processing import process_next_job
from documind.retrieval import RetrievedSource
from documind.seed_demo import seed_demo_workspace
from documind.storage import LocalFileStorage

DEMO_WORKSPACE_ID = "recruiter-demo"


class FakeEmbeddingProvider:
    def embed(
        self,
        texts: Sequence[str],
        *,
        input_type: Literal["document", "query"] = "document",
    ) -> list[list[float]]:
        del input_type
        return [[1.0, *([0.0] * 767)] for _ in texts]


class FakeChatProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def generate_answer(
        self, question: str, sources: Sequence[RetrievedSource]
    ) -> str:
        self.calls.append((question, [source.filename for source in sources]))
        return "The emergency lantern is amber [1]."


@dataclass
class DemoTestClient:
    client: TestClient
    settings: Settings
    chat_provider: FakeChatProvider


def demo_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "database_url": f"sqlite:///{tmp_path / 'demo.db'}",
        "storage_path": tmp_path / "uploads",
        "demo_workspace_id": DEMO_WORKSPACE_ID,
        "api_token": SecretStr("private-local-token"),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def demo_client(tmp_path: Path):
    settings = demo_settings(tmp_path)
    storage = LocalFileStorage(settings.storage_path)
    engine = create_database_engine(settings.database_url)
    initialize_schema(engine, settings.embedding_model_id)
    factory = create_session_factory(engine)
    embedding_provider = FakeEmbeddingProvider()
    chat_provider = FakeChatProvider()
    with factory() as session:
        seed_demo_workspace(session, storage, DEMO_WORKSPACE_ID)
    assert process_next_job(factory, storage, embedding_provider, settings)

    with factory() as session:
        session.add(User(id="private-user"))
        private_workspace = Workspace(
            id="private-workspace",
            name="Unrelated private workspace",
        )
        session.add(private_workspace)
        session.flush()
        private_document = Document(
            id="private-document",
            workspace_id=private_workspace.id,
            uploaded_by="private-user",
            filename="private.txt",
            mime_type="text/plain",
            file_size=40,
            sha256="a" * 64,
            storage_key="b" * 32,
            status="ready",
        )
        session.add(private_document)
        session.flush()
        private_version = DocumentVersion(
            id="private-version",
            document_id=private_document.id,
            version_number=1,
            status="ready",
        )
        session.add(private_version)
        session.flush()
        session.add(
            Chunk(
                document_version_id=private_version.id,
                sequence_number=0,
                text="Private-only secret content.",
                start_offset=0,
                end_offset=28,
                embedding=[1.0, *([0.0] * 767)],
            )
        )
        session.commit()
    engine.dispose()

    app = create_app(
        settings=settings,
        storage=storage,
        embedding_provider=embedding_provider,
        chat_provider=chat_provider,
    )
    with TestClient(app) as client:
        yield DemoTestClient(client, settings, chat_provider)


def test_demo_is_unavailable_without_workspace_configuration(tmp_path: Path):
    app = create_app(settings=demo_settings(tmp_path, demo_workspace_id=None))

    with TestClient(app) as client:
        response = client.get("/api/v1/demo/documents")

    assert response.status_code == 503


def run_demo_seed(database_path: Path, storage_path: Path, demo_workspace_id: str):
    package_root = Path(__file__).parents[1]
    environment = os.environ.copy()
    existing_python_path = environment.get("PYTHONPATH", "")
    environment.update(
        {
            "DOCUMIND_DATABASE_URL": f"sqlite:///{database_path}",
            "DOCUMIND_STORAGE_PATH": str(storage_path),
            "DOCUMIND_DEMO_WORKSPACE_ID": demo_workspace_id,
            "PYTHONPATH": os.pathsep.join(
                filter(None, [str(package_root / "src"), existing_python_path])
            ),
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "documind.seed_demo"],
        cwd=package_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_demo_seed_is_idempotent(tmp_path: Path):
    database_path = tmp_path / "seed.db"
    storage_path = tmp_path / "seed-uploads"

    first = run_demo_seed(database_path, storage_path, "recruiter-demo")
    second = run_demo_seed(database_path, storage_path, "recruiter-demo")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    engine = create_database_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM workspaces")) == 1
            assert connection.scalar(text("SELECT COUNT(*) FROM documents")) == 1
            assert connection.scalar(text("SELECT COUNT(*) FROM document_versions")) == 1
            assert connection.scalar(text("SELECT COUNT(*) FROM processing_jobs")) == 1
    finally:
        engine.dispose()


def test_demo_lists_only_configured_workspace_documents(demo_client: DemoTestClient):
    response = demo_client.client.get("/api/v1/demo/documents")

    assert response.status_code == 200
    documents = response.json()
    assert [document["filename"] for document in documents] == [
        DEMO_DOCUMENT_FILENAME
    ]


def test_demo_question_citations_are_limited_to_demo_workspace(
    demo_client: DemoTestClient,
):
    response = demo_client.client.post(
        "/api/v1/demo/questions",
        json={
            "question": "What color is the emergency lantern?",
            "workspace_id": "private-workspace",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["answer"] == "The emergency lantern is amber [1]."
    assert [citation["filename"] for citation in result["citations"]] == [
        DEMO_DOCUMENT_FILENAME
    ]
    assert demo_client.chat_provider.calls == [
        ("What color is the emergency lantern?", [DEMO_DOCUMENT_FILENAME])
    ]
    assert "private.txt" not in response.text
    assert "Private-only secret content." not in response.text


def test_demo_ignores_arbitrary_workspace_ids_and_has_no_mutation_routes(
    demo_client: DemoTestClient,
):
    listing = demo_client.client.get(
        "/api/v1/demo/documents?workspace_id=private-workspace"
    )
    unauthorized_private_read = demo_client.client.get(
        "/api/v1/workspaces/private-workspace/documents"
    )
    mutation = demo_client.client.post(
        "/api/v1/demo/documents",
        files={"file": ("intrusion.txt", b"private", "text/plain")},
    )

    assert listing.status_code == 200
    assert [document["filename"] for document in listing.json()] == [
        DEMO_DOCUMENT_FILENAME
    ]
    assert unauthorized_private_read.status_code == 401
    assert mutation.status_code in {404, 405}


def test_demo_requires_a_marked_workspace(tmp_path: Path):
    settings = demo_settings(tmp_path)
    engine = create_database_engine(settings.database_url)
    initialize_schema(engine)
    with create_session_factory(engine)() as session:
        session.add(Workspace(id=DEMO_WORKSPACE_ID, name="Ordinary private workspace"))
        session.commit()
    engine.dispose()
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get("/api/v1/demo/documents")

    assert response.status_code == 503


def test_demo_rate_limit_returns_429_and_retry_after(tmp_path: Path):
    settings = demo_settings(
        tmp_path,
        demo_rate_limit_requests=1,
        demo_rate_limit_window_seconds=60,
    )
    storage = LocalFileStorage(settings.storage_path)
    engine = create_database_engine(settings.database_url)
    initialize_schema(engine)
    with create_session_factory(engine)() as session:
        seed_demo_workspace(session, storage, DEMO_WORKSPACE_ID)
    engine.dispose()
    app = create_app(settings=settings, storage=storage)

    with TestClient(app) as client:
        first = client.get("/api/v1/demo/documents")
        second = client.get("/api/v1/demo/documents")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "60"


def test_demo_rate_limit_ignores_untrusted_forwarded_for(tmp_path: Path):
    settings = demo_settings(tmp_path, demo_rate_limit_requests=1)
    storage = LocalFileStorage(settings.storage_path)
    engine = create_database_engine(settings.database_url)
    initialize_schema(engine)
    with create_session_factory(engine)() as session:
        seed_demo_workspace(session, storage, DEMO_WORKSPACE_ID)
    engine.dispose()
    app = create_app(settings=settings, storage=storage)

    with TestClient(app) as client:
        first = client.get(
            "/api/v1/demo/documents",
            headers={"X-Forwarded-For": "198.51.100.11"},
        )
        second = client.get(
            "/api/v1/demo/documents",
            headers={"X-Forwarded-For": "203.0.113.42"},
        )

    assert first.status_code == 200
    assert second.status_code == 429


def test_demo_seed_refuses_an_existing_private_workspace(tmp_path: Path):
    settings = demo_settings(tmp_path)
    engine = create_database_engine(settings.database_url)
    initialize_schema(engine)
    factory = create_session_factory(engine)
    storage = LocalFileStorage(settings.storage_path)
    with factory() as session:
        session.add(Workspace(id=DEMO_WORKSPACE_ID, name="My private workspace"))
        session.commit()
    with factory() as session:
        with pytest.raises(RuntimeError, match="private or conflicting"):
            seed_demo_workspace(session, storage, DEMO_WORKSPACE_ID)
    with factory() as session:
        workspace = session.get(Workspace, DEMO_WORKSPACE_ID)
        assert workspace is not None
        assert workspace.is_public_demo is False
        assert list(
            session.scalars(
                select(Document).where(Document.workspace_id == DEMO_WORKSPACE_ID)
            )
        ) == []
    assert list(storage.root.iterdir()) == []
    engine.dispose()


def test_existing_workspaces_remain_unmarked_after_schema_upgrade(tmp_path: Path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE workspaces "
                "(id VARCHAR(36) PRIMARY KEY, name VARCHAR(120) NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO workspaces (id, name, created_at) "
                "VALUES ('old-private', 'Existing private workspace', CURRENT_TIMESTAMP)"
            )
        )

    initialize_schema(engine)

    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT is_public_demo FROM workspaces WHERE id='old-private'")
        ) in (False, 0)
    engine.dispose()
