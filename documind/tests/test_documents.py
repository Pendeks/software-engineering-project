import io
import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from docx import Document as WordDocument
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

import documind.api as api_module
from documind.api import create_app
from documind.answering import (
    AnsweringError,
    INSUFFICIENT_EVIDENCE,
    AzureOpenAIChatProvider,
)
from documind.config import Settings
from documind.database import create_database_engine, create_session_factory
from documind.document_validation import has_safe_docx_archive
from documind.embeddings import AzureOpenAIEmbeddingProvider
from documind.models import Chunk, Document, DocumentVersion, ProcessingJob
from documind.processing import (
    ProcessingError,
    chunk_sections,
    extract_sections,
    process_next_job,
)
from documind.retrieval import RetrievedSource
from documind.storage import LocalFileStorage


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        batch = list(texts)
        self.calls.append(batch)
        return [[float(len(text)), *([0.0] * 1535)] for text in batch]


class FakeChatProvider:
    def __init__(self, answer: str = "The source supports this answer [1].") -> None:
        self.answer = answer
        self.calls: list[tuple[str, list[str]]] = []

    def generate_answer(self, question: str, sources: Sequence[RetrievedSource]) -> str:
        self.calls.append((question, [source.filename for source in sources]))
        return self.answer


class FailingChatProvider:
    def generate_answer(self, question: str, sources: Sequence[RetrievedSource]) -> str:
        del question, sources
        raise RuntimeError("private upstream details")


@dataclass
class DocuMindTestApp:
    client: TestClient
    settings: Settings
    storage: LocalFileStorage
    storage_path: Path
    session_factory: sessionmaker[Session]
    embedding_provider: FakeEmbeddingProvider
    chat_provider: FakeChatProvider


@pytest.fixture
def client(tmp_path: Path) -> Iterator[DocuMindTestApp]:
    settings = Settings(
        api_token=SecretStr("test-token"),
        api_token_subject="test-user",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        storage_path=tmp_path / "uploads",
        max_upload_bytes=4096,
    )
    storage = LocalFileStorage(settings.storage_path)
    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    embedding_provider = FakeEmbeddingProvider()
    chat_provider = FakeChatProvider()
    app = create_app(
        settings=settings,
        storage=storage,
        embedding_provider=embedding_provider,
        chat_provider=chat_provider,
    )
    try:
        with TestClient(app) as test_client:
            yield DocuMindTestApp(
                client=test_client,
                settings=settings,
                storage=storage,
                storage_path=settings.storage_path,
                session_factory=session_factory,
                embedding_provider=embedding_provider,
                chat_provider=chat_provider,
            )
    finally:
        engine.dispose()


def make_workspace(client: TestClient) -> str:
    response = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": "Bearer test-token"},
        json={"name": "Product Docs"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def auth_headers(settings: Settings) -> dict[str, str]:
    if settings.api_token is None:
        raise AssertionError("Test settings must have an API token")
    token = settings.api_token.get_secret_value()
    return {"Authorization": f"Bearer {token}"}


def test_document_upload_is_private_and_listed_without_storage_key(client):
    test_client = client.client
    storage_path = client.storage_path
    workspace_id = make_workspace(test_client)

    response = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": "Bearer test-token"},
        files={"file": ("guide.txt", b"Hello, document.", "text/plain")},
    )

    assert response.status_code == 201
    document = response.json()
    assert document["filename"] == "guide.txt"
    assert document["mime_type"] == "text/plain"
    assert document["file_size"] == len(b"Hello, document.")
    assert document["status"] == "queued"
    assert "storage_key" not in document
    stored_files = list(storage_path.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].name != "guide.txt"
    assert stored_files[0].read_bytes() == b"Hello, document."

    listed = test_client.get(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": "Bearer test-token"},
    )
    inspected = test_client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [document["id"]]
    assert inspected.status_code == 200
    assert inspected.json()["id"] == document["id"]


def test_upload_rejects_unsupported_type_and_mismatched_content(client):
    test_client = client.client
    storage_path = client.storage_path
    workspace_id = make_workspace(test_client)
    headers = {"Authorization": "Bearer test-token"}

    unsupported = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
        files={"file": ("script.exe", b"anything", "application/octet-stream")},
    )
    mismatch = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
        files={"file": ("fake.pdf", b"not a PDF", "application/pdf")},
    )

    assert unsupported.status_code == 415
    assert mismatch.status_code == 415
    assert list(storage_path.iterdir()) == []


def test_upload_rejects_oversize_file_and_invalid_workspace(client):
    test_client = client.client
    storage_path = client.storage_path
    workspace_id = make_workspace(test_client)
    headers = {"Authorization": "Bearer test-token"}
    too_large = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
        files={"file": ("large.txt", b"x" * 4097, "text/plain")},
    )
    inaccessible = test_client.get(
        f"/api/v1/workspaces/{uuid4()}/documents",
        headers=headers,
    )

    assert too_large.status_code == 413
    assert inaccessible.status_code == 404
    assert list(storage_path.iterdir()) == []


def test_upload_rejects_docx_archive_over_expansion_limit(client, monkeypatch):
    workspace_id = make_workspace(client.client)
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "x" * 2048)
    monkeypatch.setattr(
        api_module,
        "has_safe_docx_archive",
        lambda value: has_safe_docx_archive(value, max_uncompressed_bytes=1024),
    )

    response = client.client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={
            "file": (
                "oversized-expansion.docx",
                content.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 415
    assert list(client.storage_path.iterdir()) == []


def test_document_delete_removes_storage_and_metadata(client):
    test_client = client.client
    storage_path = client.storage_path
    workspace_id = make_workspace(test_client)
    headers = {"Authorization": "Bearer test-token"}
    uploaded = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
        files={"file": ("remove.md", b"# Temporary", "text/markdown")},
    )
    document_id = uploaded.json()["id"]
    assert len(list(storage_path.iterdir())) == 1

    deleted = test_client.delete(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        headers=headers,
    )
    listed = test_client.get(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
    )

    assert deleted.status_code == 204
    assert listed.json() == []
    assert list(storage_path.iterdir()) == []
    assert not process_next_job(
        client.session_factory,
        client.storage,
        FakeEmbeddingProvider(),
        client.settings,
    )


def test_document_endpoints_require_bearer_token(client):
    response = client.client.post("/api/v1/workspaces", json={"name": "Private"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_live_and_readiness_checks_report_status_and_request_id(
    client, monkeypatch, tmp_path, caplog
):
    caplog.set_level("INFO", logger="documind.api")
    live = client.client.get("/health/live?token=private-query-value")
    ready = client.client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert len(live.headers["x-request-id"]) == 32
    assert "http_request_completed" in caplog.text
    assert "status_code=200" in caplog.text
    assert "private-query-value" not in caplog.text
    assert "test-token" not in caplog.text
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}

    engine = client.client.app.state.engine

    def database_unavailable():
        raise SQLAlchemyError("private database detail")

    with monkeypatch.context() as patcher:
        patcher.setattr(engine, "connect", database_unavailable)
        database_failed = client.client.get("/health/ready")
    assert database_failed.status_code == 503
    assert "private database detail" not in database_failed.text

    with monkeypatch.context() as patcher:
        patcher.setattr(client.storage, "root", tmp_path / "missing-storage")
        storage_failed = client.client.get("/health/ready")
    assert storage_failed.status_code == 503
    assert "missing-storage" not in storage_failed.text


def test_workspace_list_only_returns_workspaces_for_authenticated_user(client):
    test_client = client.client
    owned_workspace = make_workspace(test_client)
    other_settings = client.settings.model_copy(update={"api_token_subject": "other-user"})
    other_app = create_app(settings=other_settings, storage=client.storage)

    with TestClient(other_app) as other_client:
        created = other_client.post(
            "/api/v1/workspaces",
            headers=auth_headers(other_settings),
            json={"name": "Other workspace"},
        )
        assert created.status_code == 201
        other_workspace = created.json()["id"]

    listed = test_client.get(
        "/api/v1/workspaces",
        headers=auth_headers(client.settings),
    )

    assert listed.status_code == 200
    assert [workspace["id"] for workspace in listed.json()] == [owned_workspace]
    assert other_workspace not in {workspace["id"] for workspace in listed.json()}


def test_app_serves_built_frontend_when_configured(client, tmp_path):
    web_root = tmp_path / "web"
    web_root.mkdir()
    (web_root / "index.html").write_text(
        "<!doctype html><title>DocuMind UI</title>",
        encoding="utf-8",
    )
    settings = client.settings.model_copy(update={"web_static_path": web_root})
    app = create_app(
        settings=settings,
        storage=client.storage,
    )

    with TestClient(app) as web_client:
        page = web_client.get("/")
        health = web_client.get("/health/live")

    assert page.status_code == 200
    assert "DocuMind UI" in page.text
    assert health.status_code == 200


def test_document_access_is_scoped_to_workspace_members(client):
    test_client = client.client
    storage_path = client.storage_path
    workspace_id = make_workspace(test_client)
    upload = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={"file": ("private.txt", b"Workspace-specific.", "text/plain")},
    )
    assert upload.status_code == 201

    other_settings = client.settings.model_copy(
        update={
            "api_token_subject": "other-user",
        }
    )
    other_app = create_app(
        settings=other_settings,
        storage=client.storage,
    )
    with TestClient(other_app) as other_client:
        headers = auth_headers(other_settings)
        assert other_client.get(
            f"/api/v1/workspaces/{workspace_id}/documents",
            headers=headers,
        ).status_code == 404
        assert other_client.get(
            f"/api/v1/workspaces/{workspace_id}/documents/{upload.json()['id']}",
            headers=headers,
        ).status_code == 404
        assert other_client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            headers=headers,
            files={"file": ("intrusion.txt", b"Should not be stored.", "text/plain")},
        ).status_code == 404
        assert other_client.delete(
            f"/api/v1/workspaces/{workspace_id}/documents/{upload.json()['id']}",
            headers=headers,
        ).status_code == 404

    listed = test_client.get(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
    )
    assert [document["id"] for document in listed.json()] == [upload.json()["id"]]
    assert len(list(storage_path.iterdir())) == 1


def test_delete_storage_failure_keeps_document_retryable(client, monkeypatch):
    test_client = client.client
    storage_path = client.storage_path
    workspace_id = make_workspace(test_client)
    headers = auth_headers(client.settings)
    uploaded = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
        files={"file": ("retry.txt", b"Retry deletion.", "text/plain")},
    )
    document_id = uploaded.json()["id"]
    original_delete = client.storage.delete

    def fail_delete(_key: str) -> None:
        del _key
        raise OSError("simulated storage outage")

    monkeypatch.setattr(client.storage, "delete", fail_delete)
    failed = test_client.delete(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        headers=headers,
    )
    listed = test_client.get(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
    )
    assert failed.status_code == 503
    assert listed.json()[0]["status"] == "delete_failed"
    assert len(list(storage_path.iterdir())) == 1

    monkeypatch.setattr(client.storage, "delete", original_delete)
    retried = test_client.delete(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        headers=headers,
    )
    assert retried.status_code == 204
    assert list(storage_path.iterdir()) == []


def test_text_extraction_and_chunk_offsets_preserve_source_text():
    source = "DocuMind extracts text and keeps stable source offsets for citations."
    sections = extract_sections("notes.txt", source.encode())
    chunks = chunk_sections(sections, chunk_size=32, chunk_overlap=8)

    assert len(chunks) > 1
    assert all(
        source[chunk.start_offset : chunk.end_offset] == chunk.text
        for chunk in chunks
    )
    assert chunks[0].start_offset == 0
    assert chunks[-1].end_offset == len(source)


def test_pdf_and_docx_text_extraction():
    pdf_writer = PdfWriter()
    page = pdf_writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): pdf_writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (PDF text extraction works.) Tj ET")
    page[NameObject("/Contents")] = pdf_writer._add_object(stream)
    pdf_content = io.BytesIO()
    pdf_writer.write(pdf_content)

    docx_document = WordDocument()
    docx_document.add_paragraph("DOCX text extraction works.")
    docx_content = io.BytesIO()
    docx_document.save(docx_content)

    pdf_sections = extract_sections("manual.pdf", pdf_content.getvalue())
    docx_sections = extract_sections("manual.docx", docx_content.getvalue())

    assert "PDF text extraction works." in pdf_sections[0].text
    assert pdf_sections[0].page_number == 1
    assert "DOCX text extraction works." in docx_sections[0].text


def test_docx_archive_expansion_and_entry_count_are_bounded():
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "x" * 2048)

    assert not has_safe_docx_archive(content.getvalue(), max_uncompressed_bytes=1024)
    assert has_safe_docx_archive(content.getvalue(), max_uncompressed_bytes=4096)

    many_entries = io.BytesIO()
    with zipfile.ZipFile(many_entries, "w") as archive:
        archive.writestr("word/document.xml", "<document/>")
        for index in range(1000):
            archive.writestr(f"word/media/image-{index}.bin", b"x")
    assert not has_safe_docx_archive(many_entries.getvalue())


def test_upload_queues_job_and_worker_persists_chunks_and_embeddings(client):
    test_client = client.client
    workspace_id = make_workspace(test_client)
    source = (
        "Documents need reliable processing. "
        "Each passage keeps offsets for citation. "
        "Embeddings support later semantic retrieval."
    )
    uploaded = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={"file": ("pipeline.txt", source.encode(), "text/plain")},
    )
    document_id = uploaded.json()["id"]

    provider = FakeEmbeddingProvider()
    assert process_next_job(
        client.session_factory,
        client.storage,
        provider,
        client.settings.model_copy(update={"chunk_size": 48, "chunk_overlap": 8}),
    )

    listed = test_client.get(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
    )
    assert listed.json()[0]["status"] == "ready"
    assert listed.json()[0]["processing_error"] is None
    with client.session_factory() as session:
        document = session.get(Document, document_id)
        version = session.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        )
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.document_version_id == version.id)
        )
        chunks = list(
            session.scalars(
                select(Chunk)
                .where(Chunk.document_version_id == version.id)
                .order_by(Chunk.sequence_number)
            )
        )

    assert document.status == "ready"
    assert version.status == "ready"
    assert job.status == "completed"
    assert job.attempts == 1
    assert len(chunks) > 1
    assert [chunk.sequence_number for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.embedding) == 1536 for chunk in chunks)
    assert all(
        source[chunk.start_offset : chunk.end_offset] == chunk.text
        for chunk in chunks
    )
    assert provider.calls == [[chunk.text for chunk in chunks]]


def test_failed_embedding_can_be_retried_and_does_not_leak_provider_error(client):
    test_client = client.client
    workspace_id = make_workspace(test_client)
    uploaded = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={"file": ("retry.txt", b"Retry this document.", "text/plain")},
    )
    document_id = uploaded.json()["id"]

    class FailingEmbeddingProvider:
        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            del texts
            raise RuntimeError("private endpoint credential detail")

    assert process_next_job(
        client.session_factory,
        client.storage,
        FailingEmbeddingProvider(),
        client.settings,
    )
    failed = test_client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        headers=auth_headers(client.settings),
    ).json()
    assert failed["status"] == "failed"
    assert "credential" not in failed["processing_error"]

    retry = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/process",
        headers=auth_headers(client.settings),
    )
    assert retry.status_code == 202
    assert retry.json() == {"status": "queued", "attempts": 1}
    assert process_next_job(
        client.session_factory,
        client.storage,
        FakeEmbeddingProvider(),
        client.settings,
    )

    ready = test_client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        headers=auth_headers(client.settings),
    ).json()
    assert ready["status"] == "ready"
    with client.session_factory() as session:
        job = session.scalar(
            select(ProcessingJob)
            .join(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
        )
        assert job.status == "completed"
        assert job.attempts == 2


def test_stale_processing_job_can_be_reclaimed(client):
    test_client = client.client
    workspace_id = make_workspace(test_client)
    uploaded = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={"file": ("stale.txt", b"Recover interrupted processing.", "text/plain")},
    )
    document_id = uploaded.json()["id"]
    with client.session_factory() as session:
        document = session.get(Document, document_id)
        version = session.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        )
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.document_version_id == version.id)
        )
        document.status = "processing"
        version.status = "processing"
        job.status = "processing"
        job.attempts = 1
        job.updated_at = datetime.now(timezone.utc) - timedelta(
            seconds=client.settings.processing_job_timeout_seconds + 1
        )
        session.commit()

    retry = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/process",
        headers=auth_headers(client.settings),
    )
    assert retry.status_code == 202
    assert retry.json() == {"status": "queued", "attempts": 1}
    assert process_next_job(
        client.session_factory,
        client.storage,
        FakeEmbeddingProvider(),
        client.settings,
    )
    with client.session_factory() as session:
        job = session.scalar(
            select(ProcessingJob)
            .join(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
        )
        assert job.status == "completed"
        assert job.attempts == 2


def test_deleting_document_while_processing_is_rejected(client):
    test_client = client.client
    workspace_id = make_workspace(test_client)
    uploaded = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={"file": ("active.txt", b"Still being processed.", "text/plain")},
    )
    document_id = uploaded.json()["id"]
    with client.session_factory() as session:
        document = session.get(Document, document_id)
        document.status = "processing"
        session.commit()
        job = session.scalar(
            select(ProcessingJob)
            .join(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
        )
        job.status = "processing"
        session.commit()

    deleted = test_client.delete(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        headers=auth_headers(client.settings),
    )
    assert deleted.status_code == 409
    assert len(list(client.storage_path.iterdir())) == 1


def test_worker_marks_unextractable_document_failed(client):
    test_client = client.client
    workspace_id = make_workspace(test_client)
    uploaded = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={"file": ("empty.txt", b" \n\t ", "text/plain")},
    )

    assert process_next_job(
        client.session_factory,
        client.storage,
        FakeEmbeddingProvider(),
        client.settings,
    )

    failed = test_client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{uploaded.json()['id']}",
        headers=auth_headers(client.settings),
    ).json()
    assert failed["status"] == "failed"
    assert failed["processing_error"] == "No extractable text was found in the document."


def test_azure_embedding_adapter_requires_real_configuration():
    with pytest.raises(ProcessingError, match="configuration is incomplete"):
        AzureOpenAIEmbeddingProvider(Settings()).embed(["sample"])


def test_azure_chat_adapter_requires_real_configuration():
    with pytest.raises(AnsweringError, match="configuration is incomplete"):
        AzureOpenAIChatProvider(Settings()).generate_answer("question", [])


def test_question_returns_workspace_scoped_citations(client):
    test_client = client.client
    first_workspace = make_workspace(test_client)
    second_workspace = make_workspace(test_client)
    first_document_id = ""

    for workspace_id, filename, text in [
        (first_workspace, "first.txt", b"Workspace one contains a project fact."),
        (second_workspace, "second.txt", b"Workspace two contains another project fact."),
    ]:
        uploaded = test_client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            headers=auth_headers(client.settings),
            files={"file": (filename, text, "text/plain")},
        )
        assert uploaded.status_code == 201
        if workspace_id == first_workspace:
            first_document_id = uploaded.json()["id"]
        assert process_next_job(
            client.session_factory,
            client.storage,
            FakeEmbeddingProvider(),
            client.settings,
        )

    response = test_client.post(
        f"/api/v1/workspaces/{first_workspace}/questions",
        headers=auth_headers(client.settings),
        json={"question": "What is in the project document?"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["answer"] == "The source supports this answer [1]."
    assert result["abstained"] is False
    assert len(result["citations"]) == 1
    citation = result["citations"][0]
    assert citation["citation_number"] == 1
    assert citation["document_id"] == first_document_id
    assert citation["filename"] == "first.txt"
    assert citation["page_number"] is None
    assert citation["start_offset"] == 0
    assert citation["end_offset"] == len("Workspace one contains a project fact.")
    assert citation["excerpt"] == "Workspace one contains a project fact."
    assert client.chat_provider.calls == [
        ("What is in the project document?", ["first.txt"])
    ]


def test_question_abstains_without_relevant_ready_sources(client):
    workspace_id = make_workspace(client.client)

    response = client.client.post(
        f"/api/v1/workspaces/{workspace_id}/questions",
        headers=auth_headers(client.settings),
        json={"question": "What does the document say?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": INSUFFICIENT_EVIDENCE,
        "abstained": True,
        "citations": [],
    }
    assert client.chat_provider.calls == []


def test_question_rejects_blank_input_without_calling_providers(client):
    workspace_id = make_workspace(client.client)

    response = client.client.post(
        f"/api/v1/workspaces/{workspace_id}/questions",
        headers=auth_headers(client.settings),
        json={"question": " \t "},
    )

    assert response.status_code == 422
    assert client.embedding_provider.calls == []
    assert client.chat_provider.calls == []


def test_question_abstains_below_similarity_threshold(client):
    workspace_id = make_workspace(client.client)
    uploaded = client.client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={"file": ("unrelated.txt", b"Unrelated reference material.", "text/plain")},
    )
    assert uploaded.status_code == 201
    assert process_next_job(
        client.session_factory,
        client.storage,
        FakeEmbeddingProvider(),
        client.settings,
    )
    with client.session_factory() as session:
        chunk = session.scalar(select(Chunk))
        chunk.embedding = [0.0, 1.0, *([0.0] * 1534)]
        session.commit()

    response = client.client.post(
        f"/api/v1/workspaces/{workspace_id}/questions",
        headers=auth_headers(client.settings),
        json={"question": "A query with a different embedding direction."},
    )

    assert response.status_code == 200
    assert response.json()["abstained"] is True
    assert response.json()["citations"] == []
    assert client.chat_provider.calls == []


def test_question_rejects_uncited_model_output(client):
    workspace_id = make_workspace(client.client)
    client.chat_provider.answer = "This answer contains an unsupported assertion."
    uploaded = client.client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={"file": ("facts.txt", b"A source fact.", "text/plain")},
    )
    assert uploaded.status_code == 201
    assert process_next_job(
        client.session_factory,
        client.storage,
        FakeEmbeddingProvider(),
        client.settings,
    )

    response = client.client.post(
        f"/api/v1/workspaces/{workspace_id}/questions",
        headers=auth_headers(client.settings),
        json={"question": "What is the source fact?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == INSUFFICIENT_EVIDENCE
    assert response.json()["abstained"] is True
    assert response.json()["citations"] == []


def test_question_rejects_unknown_citation_and_hides_provider_errors(client):
    workspace_id = make_workspace(client.client)
    uploaded = client.client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={"file": ("facts.txt", b"A source fact.", "text/plain")},
    )
    assert uploaded.status_code == 201
    assert process_next_job(
        client.session_factory,
        client.storage,
        FakeEmbeddingProvider(),
        client.settings,
    )
    client.chat_provider.answer = "An unsupported result [99]."

    invalid_citation = client.client.post(
        f"/api/v1/workspaces/{workspace_id}/questions",
        headers=auth_headers(client.settings),
        json={"question": "What is the source fact?"},
    )

    assert invalid_citation.status_code == 200
    assert invalid_citation.json()["abstained"] is True
    assert invalid_citation.json()["citations"] == []

    app = create_app(
        settings=client.settings,
        storage=client.storage,
        embedding_provider=client.embedding_provider,
        chat_provider=FailingChatProvider(),
    )
    with TestClient(app) as failing_client:
        failed = failing_client.post(
            f"/api/v1/workspaces/{workspace_id}/questions",
            headers=auth_headers(client.settings),
            json={"question": "What is the source fact?"},
        )
    assert failed.status_code == 503
    assert "private upstream details" not in failed.text


def test_question_requires_workspace_membership_before_embedding(client):
    workspace_id = make_workspace(client.client)
    other_settings = client.settings.model_copy(
        update={"api_token_subject": "question-outsider"}
    )
    other_app = create_app(
        settings=other_settings,
        storage=client.storage,
        embedding_provider=client.embedding_provider,
        chat_provider=client.chat_provider,
    )
    calls_before = len(client.embedding_provider.calls)

    with TestClient(other_app) as other_client:
        response = other_client.post(
            f"/api/v1/workspaces/{workspace_id}/questions",
            headers=auth_headers(other_settings),
            json={"question": "Can I see this workspace?"},
        )

    assert response.status_code == 404
    assert len(client.embedding_provider.calls) == calls_before


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        ("guide.pdf", "application/pdf", b"%PDF-1.7\nDocuMind PDF fixture"),
        ("guide.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", None),
    ],
)
def test_upload_accepts_supported_pdf_and_docx_content(
    client: DocuMindTestApp,
    filename: str,
    content_type: str,
    content: bytes | None,
):
    test_client = client.client
    workspace_id = make_workspace(test_client)
    if content is None:
        document_xml = b"<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'/>"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", document_xml)
        content = buffer.getvalue()

    response = test_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=auth_headers(client.settings),
        files={"file": (filename, content, content_type)},
    )

    assert response.status_code == 201
    assert response.json()["filename"] == filename
    assert response.json()["file_size"] == len(content)
    assert len(list(client.storage_path.iterdir())) == 1
