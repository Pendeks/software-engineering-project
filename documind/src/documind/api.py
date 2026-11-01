import hashlib
import hmac
import logging
import math
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from documind.answering import (
    AnsweringError,
    ChatProvider,
    QuestionAnswer,
    answer_question,
    create_chat_provider,
)
from documind.auth import (
    InvalidAccessToken,
    get_or_create_external_user,
    verify_entra_access_token,
)
from documind.config import Settings
from documind.database import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
    session_dependency,
)
from documind.document_validation import has_safe_docx_archive
from documind.embeddings import create_embedding_provider
from documind.models import (
    Document,
    DocumentVersion,
    ProcessingJob,
    User,
    Workspace,
    WorkspaceMember,
)
from documind.processing import EmbeddingProvider
from documind.retrieval import RetrievalError
from documind.storage import LocalFileStorage

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}
UPLOAD_REQUEST_OVERHEAD_BYTES = 64 * 1024


class UploadBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].startswith("/api/v1/workspaces/")
            or not scope["path"].endswith("/documents")
        ):
            await self.app(scope, receive, send)
            return

        content_length = next(
            (
                value
                for name, value in scope["headers"]
                if name.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        received_bytes = 0

        async def receive_with_limit() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise _UploadBodyTooLarge
            return message

        try:
            await self.app(scope, receive_with_limit, send)
        except _UploadBodyTooLarge:
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "The uploaded file exceeds the size limit."},
        )
        await response(scope, receive, send)


class _UploadBodyTooLarge(Exception):
    pass


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workspace name cannot be blank")
        return normalized


class WorkspaceResponse(BaseModel):
    id: str
    name: str


class DocumentResponse(BaseModel):
    id: str
    workspace_id: str
    filename: str
    mime_type: str
    file_size: int
    sha256: str
    status: str
    processing_error: str | None
    created_at: str


class ProcessingResponse(BaseModel):
    status: str
    attempts: int


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Question cannot be blank")
        return normalized


class CitationResponse(BaseModel):
    citation_number: int
    document_id: str
    document_version_id: str
    filename: str
    page_number: int | None
    start_offset: int
    end_offset: int
    excerpt: str


class QuestionResponse(BaseModel):
    answer: str
    abstained: bool
    citations: list[CitationResponse]


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    storage: LocalFileStorage | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    chat_provider: ChatProvider | None = None,
) -> FastAPI:
    app_settings = settings or Settings()
    db_engine = engine or create_database_engine(app_settings.database_url)
    session_factory = create_session_factory(db_engine)
    file_storage = storage or LocalFileStorage(app_settings.storage_path)
    question_embedding_provider = embedding_provider or create_embedding_provider(app_settings)
    question_chat_provider = chat_provider or create_chat_provider(app_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        del _app
        initialize_schema(db_engine, app_settings.embedding_model_id)
        yield
        db_engine.dispose()

    app = FastAPI(title="DocuMind API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        UploadBodyLimitMiddleware,
        max_body_bytes=app_settings.max_upload_bytes + UPLOAD_REQUEST_OVERHEAD_BYTES,
    )
    app.state.settings = app_settings
    app.state.engine = db_engine
    app.state.session_factory = session_factory
    app.state.storage = file_storage
    app.state.embedding_provider = question_embedding_provider
    app.state.chat_provider = question_chat_provider
    demo_request_windows: dict[str, tuple[float, int]] = {}

    def get_session():
        yield from session_dependency(session_factory)

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = uuid4().hex
        started_at = time.perf_counter()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception(
                "http_request_failed request_id=%s method=%s",
                request_id,
                request.method,
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "http_request_completed request_id=%s method=%s status_code=%s duration_ms=%.2f",
                request_id,
                request.method,
                status_code,
                duration_ms,
            )

    def current_user(
        authorization: str | None = Header(default=None),
        session: Session = Depends(get_session),
    ) -> str:
        scheme, separator, supplied_token = (authorization or "").partition(" ")
        if (
            not separator
            or scheme.casefold() != "bearer"
            or not supplied_token
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if app_settings.auth_mode == "entra":
            try:
                issuer, subject = verify_entra_access_token(
                    supplied_token, app_settings
                )
                return get_or_create_external_user(session, issuer, subject)
            except InvalidAccessToken as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required.",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from error
            except SQLAlchemyError as error:
                logger.exception("external_identity_resolution_failed")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service is temporarily unavailable.",
                ) from error

        configured_token = app_settings.api_token
        if configured_token is None or not configured_token.get_secret_value():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API authentication is not configured.",
            )
        if not hmac.compare_digest(supplied_token, configured_token.get_secret_value()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return app_settings.api_token_subject

    def require_workspace_member(
        session: Session, workspace_id: str, user_id: str
    ) -> Workspace:
        workspace = session.scalar(
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(
                Workspace.id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        return workspace

    def require_demo_workspace(session: Session) -> Workspace:
        workspace_id = app_settings.demo_workspace_id
        if not workspace_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The public demo is not configured.",
            )
        workspace = session.scalar(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.is_public_demo.is_(True),
            )
        )
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The public demo is unavailable.",
            )
        return workspace

    def require_demo_request_limit(request: Request) -> None:
        client = request.client
        if client is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The public demo is temporarily unavailable.",
            )

        now = time.monotonic()
        window_seconds = app_settings.demo_rate_limit_window_seconds
        client_host = client.host
        expired_hosts = [
            host
            for host, (window_start, _count) in demo_request_windows.items()
            if now - window_start >= window_seconds
        ]
        for host in expired_hosts:
            del demo_request_windows[host]

        window_start, request_count = demo_request_windows.get(
            client_host, (now, 0)
        )
        if now - window_start >= window_seconds:
            window_start, request_count = now, 0
        if request_count >= app_settings.demo_rate_limit_requests:
            retry_after = max(1, math.ceil(window_seconds - (now - window_start)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="The public demo request limit has been reached.",
                headers={"Retry-After": str(retry_after)},
            )
        demo_request_windows[client_host] = (window_start, request_count + 1)

    @app.get("/health")
    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def health_ready() -> dict[str, str]:
        try:
            with db_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            storage_ready = (
                file_storage.root.is_dir()
                and os.access(file_storage.root, os.R_OK | os.W_OK)
            )
        except (OSError, SQLAlchemyError) as error:
            logger.error(
                "readiness_check_failed error_type=%s",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Required service is unavailable.",
            ) from error

        if not storage_ready:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Required service is unavailable.",
            )
        return {"status": "ready"}

    @app.get(
        "/api/v1/demo/documents",
        response_model=list[DocumentResponse],
    )
    def list_demo_documents(
        request: Request,
        session: Session = Depends(get_session),
    ) -> list[DocumentResponse]:
        require_demo_request_limit(request)
        workspace = require_demo_workspace(session)
        documents = session.scalars(
            select(Document)
            .where(Document.workspace_id == workspace.id)
            .order_by(Document.created_at.desc(), Document.id)
        )
        return [_document_response(document) for document in documents]

    @app.post(
        "/api/v1/demo/questions",
        response_model=QuestionResponse,
    )
    def ask_demo_question(
        payload: QuestionRequest,
        request: Request,
        session: Session = Depends(get_session),
    ) -> QuestionResponse:
        require_demo_request_limit(request)
        workspace = require_demo_workspace(session)
        try:
            result = answer_question(
                session,
                workspace.id,
                payload.question,
                question_embedding_provider,
                question_chat_provider,
                app_settings,
            )
        except (AnsweringError, RetrievalError, SQLAlchemyError) as error:
            logger.error(
                "demo_question_answering_failed error_type=%s",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Question answering is temporarily unavailable.",
            ) from error
        return _question_response(result)

    @app.post(
        "/api/v1/workspaces",
        response_model=WorkspaceResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_workspace(
        payload: WorkspaceCreate,
        session: Session = Depends(get_session),
        user_id: str = Depends(current_user),
    ) -> WorkspaceResponse:
        try:
            session.merge(User(id=user_id))
            workspace = Workspace(name=payload.name)
            session.add(workspace)
            session.flush()
            session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user_id, role="owner"))
            session.commit()
            return WorkspaceResponse(id=workspace.id, name=workspace.name)
        except SQLAlchemyError:
            session.rollback()
            logger.exception("workspace_create_failed")
            raise HTTPException(status_code=503, detail="Workspace could not be created.")

    @app.get(
        "/api/v1/workspaces",
        response_model=list[WorkspaceResponse],
    )
    def list_workspaces(
        session: Session = Depends(get_session),
        user_id: str = Depends(current_user),
    ) -> list[WorkspaceResponse]:
        workspaces = session.scalars(
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.name, Workspace.id)
        )
        return [
            WorkspaceResponse(id=workspace.id, name=workspace.name)
            for workspace in workspaces
        ]

    @app.post(
        "/api/v1/workspaces/{workspace_id}/documents",
        response_model=DocumentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def upload_document(
        workspace_id: str,
        file: UploadFile = File(...),
        session: Session = Depends(get_session),
        user_id: str = Depends(current_user),
    ) -> DocumentResponse:
        require_workspace_member(session, workspace_id, user_id)
        filename = _safe_filename(file.filename)
        extension = Path(filename).suffix.casefold()
        expected_mime_type = SUPPORTED_TYPES.get(extension)
        if expected_mime_type is None:
            raise HTTPException(status_code=415, detail="Supported file types are PDF, DOCX, TXT, and MD.")

        content = file.file.read(app_settings.max_upload_bytes + 1)
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        if len(content) > app_settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="The uploaded file exceeds the size limit.")
        _validate_content(extension, content)

        key = uuid4().hex
        document = Document(
            workspace_id=workspace_id,
            uploaded_by=user_id,
            filename=filename,
            mime_type=expected_mime_type,
            file_size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            storage_key=key,
            status="queued",
        )

        try:
            file_storage.put(key, content)
        except OSError:
            logger.exception("document_storage_write_failed")
            raise HTTPException(status_code=503, detail="Document storage is unavailable.")

        try:
            session.add(document)
            session.flush()
            version = DocumentVersion(document_id=document.id, version_number=1, status="queued")
            session.add(version)
            session.flush()
            session.add(ProcessingJob(document_version_id=version.id, status="queued"))
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            try:
                file_storage.delete(key)
            except OSError:
                logger.exception("document_storage_cleanup_failed")
            logger.exception("document_metadata_write_failed")
            raise HTTPException(status_code=503, detail="Document metadata could not be saved.")

        return _document_response(document)

    @app.get(
        "/api/v1/workspaces/{workspace_id}/documents",
        response_model=list[DocumentResponse],
    )
    def list_documents(
        workspace_id: str,
        session: Session = Depends(get_session),
        user_id: str = Depends(current_user),
    ) -> list[DocumentResponse]:
        require_workspace_member(session, workspace_id, user_id)
        documents = session.scalars(
            select(Document)
            .where(Document.workspace_id == workspace_id)
            .order_by(Document.created_at.desc(), Document.id)
        )
        return [_document_response(document) for document in documents]

    @app.get(
        "/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        response_model=DocumentResponse,
    )
    def get_document(
        workspace_id: str,
        document_id: str,
        session: Session = Depends(get_session),
        user_id: str = Depends(current_user),
    ) -> DocumentResponse:
        require_workspace_member(session, workspace_id, user_id)
        document = session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
            )
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        return _document_response(document)

    @app.post(
        "/api/v1/workspaces/{workspace_id}/documents/{document_id}/process",
        response_model=ProcessingResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def retry_document_processing(
        workspace_id: str,
        document_id: str,
        session: Session = Depends(get_session),
        user_id: str = Depends(current_user),
    ) -> ProcessingResponse:
        require_workspace_member(session, workspace_id, user_id)
        document = session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
            )
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        job = session.scalar(
            select(ProcessingJob)
            .join(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        )
        if job is None:
            raise HTTPException(status_code=409, detail="Document has no processing job.")
        if job.status == "processing":
            updated_at = job.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            lease_expires_at = datetime.now(timezone.utc) - timedelta(
                seconds=app_settings.processing_job_timeout_seconds
            )
            if updated_at > lease_expires_at:
                raise HTTPException(status_code=409, detail="Document processing is already in progress.")
        if job.status == "completed":
            raise HTTPException(status_code=409, detail="Document processing is already complete.")

        if job.status in {"failed", "processing"}:
            job.status = "queued"
            job.last_error = None
            document.status = "queued"
            document.processing_error = None
            version = session.get(DocumentVersion, job.document_version_id)
            if version is not None:
                version.status = "queued"
        try:
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.exception("document_processing_retry_failed")
            raise HTTPException(status_code=503, detail="Document processing could not be queued.")
        return ProcessingResponse(status=job.status, attempts=job.attempts)

    @app.post(
        "/api/v1/workspaces/{workspace_id}/questions",
        response_model=QuestionResponse,
    )
    def ask_question(
        workspace_id: str,
        payload: QuestionRequest,
        session: Session = Depends(get_session),
        user_id: str = Depends(current_user),
    ) -> QuestionResponse:
        require_workspace_member(session, workspace_id, user_id)
        try:
            result = answer_question(
                session,
                workspace_id,
                payload.question,
                question_embedding_provider,
                question_chat_provider,
                app_settings,
            )
        except (AnsweringError, RetrievalError, SQLAlchemyError) as error:
            logger.error(
                "question_answering_failed workspace_id=%s error_type=%s",
                workspace_id,
                type(error).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="Question answering is temporarily unavailable.",
            ) from error
        return _question_response(result)

    @app.delete(
        "/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_document(
        workspace_id: str,
        document_id: str,
        session: Session = Depends(get_session),
        user_id: str = Depends(current_user),
    ) -> None:
        require_workspace_member(session, workspace_id, user_id)
        document = session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
            )
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        jobs = list(
            session.scalars(
                select(ProcessingJob)
                .join(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .with_for_update()
            )
        )
        if any(job.status == "processing" for job in jobs):
            raise HTTPException(status_code=409, detail="Wait for document processing to finish before deleting it.")
        for job in jobs:
            if job.status == "queued":
                job.status = "cancelled"
                version = session.get(DocumentVersion, job.document_version_id)
                if version is not None:
                    version.status = "cancelled"

        document.status = "deleting"
        document.processing_error = None
        try:
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.exception("document_delete_state_write_failed")
            raise HTTPException(status_code=503, detail="Document deletion could not be started.")

        try:
            file_storage.delete(document.storage_key)
        except OSError:
            logger.exception("document_storage_delete_failed")
            document.status = "delete_failed"
            document.processing_error = "Document storage deletion failed. Retry the delete request."
            try:
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                logger.exception("document_delete_failure_state_write_failed")
            raise HTTPException(status_code=503, detail="Document storage is unavailable.")

        try:
            session.delete(document)
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.exception("document_metadata_delete_failed")
            raise HTTPException(status_code=503, detail="Document metadata could not be deleted.")

    if app_settings.web_static_path is not None:
        index_path = app_settings.web_static_path / "index.html"
        if index_path.is_file():
            app.mount(
                "/",
                StaticFiles(directory=app_settings.web_static_path, html=True),
                name="web",
            )
        else:
            logger.warning("web_static_assets_unavailable")

    return app


def _safe_filename(filename: str | None) -> str:
    cleaned = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not cleaned or cleaned in {".", ".."} or len(cleaned) > 255:
        raise HTTPException(status_code=400, detail="A valid filename is required.")
    if any(ord(character) < 32 or ord(character) == 127 for character in cleaned):
        raise HTTPException(status_code=400, detail="The filename contains invalid characters.")
    return cleaned


def _validate_content(extension: str, content: bytes) -> None:
    if extension == ".pdf":
        valid = b"%PDF-" in content[:1024]
    elif extension == ".docx":
        valid = has_safe_docx_archive(content)
    else:
        try:
            content.decode("utf-8")
            valid = b"\x00" not in content
        except UnicodeDecodeError:
            valid = False

    if not valid:
        raise HTTPException(status_code=415, detail="The file contents do not match the supported file type.")


def _document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        workspace_id=document.workspace_id,
        filename=document.filename,
        mime_type=document.mime_type,
        file_size=document.file_size,
        sha256=document.sha256,
        status=document.status,
        processing_error=document.processing_error,
        created_at=document.created_at.isoformat(),
    )


def _question_response(result: QuestionAnswer) -> QuestionResponse:
    return QuestionResponse(
        answer=result.answer,
        abstained=result.abstained,
        citations=[
            CitationResponse(
                citation_number=citation.citation_number,
                document_id=citation.document_id,
                document_version_id=citation.document_version_id,
                filename=citation.filename,
                page_number=citation.page_number,
                start_offset=citation.start_offset,
                end_offset=citation.end_offset,
                excerpt=citation.excerpt,
            )
            for citation in result.citations
        ],
    )
