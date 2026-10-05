import hashlib
import hmac
import io
import logging
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from documind.answering import (
    AnsweringError,
    AzureOpenAIChatProvider,
    ChatProvider,
    QuestionAnswer,
    answer_question,
)
from documind.config import Settings
from documind.database import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
    session_dependency,
)
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
from documind.embeddings import AzureOpenAIEmbeddingProvider

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


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
    question_embedding_provider = embedding_provider or AzureOpenAIEmbeddingProvider(app_settings)
    question_chat_provider = chat_provider or AzureOpenAIChatProvider(app_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        del _app
        initialize_schema(db_engine)
        yield
        db_engine.dispose()

    app = FastAPI(title="DocuMind API", version="0.1.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.engine = db_engine
    app.state.session_factory = session_factory
    app.state.storage = file_storage
    app.state.embedding_provider = question_embedding_provider
    app.state.chat_provider = question_chat_provider

    def get_session():
        yield from session_dependency(session_factory)

    def current_user(authorization: str | None = Header(default=None)) -> str:
        configured_token = app_settings.api_token
        if configured_token is None or not configured_token.get_secret_value():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API authentication is not configured.",
            )
        scheme, separator, supplied_token = (authorization or "").partition(" ")
        if (
            not separator
            or scheme.casefold() != "bearer"
            or not hmac.compare_digest(supplied_token, configured_token.get_secret_value())
        ):
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                valid = "word/document.xml" in archive.namelist()
        except zipfile.BadZipFile:
            valid = False
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
