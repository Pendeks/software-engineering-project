import io
import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol

from docx import Document as WordDocument
from pypdf import PdfReader
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from documind.config import Settings
from documind.constants import EMBEDDING_DIMENSIONS
from documind.document_validation import has_safe_docx_archive
from documind.models import Chunk, Document, DocumentVersion, ProcessingJob
from documind.storage import LocalFileStorage

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    pass


class EmbeddingProvider(Protocol):
    def embed(
        self,
        texts: Sequence[str],
        *,
        input_type: Literal["document", "query"] = "document",
    ) -> list[list[float]]: ...


@dataclass(frozen=True)
class ExtractedSection:
    text: str
    page_number: int | None = None


@dataclass(frozen=True)
class TextChunk:
    sequence_number: int
    text: str
    page_number: int | None
    start_offset: int
    end_offset: int


def extract_sections(filename: str, content: bytes) -> list[ExtractedSection]:
    suffix = filename.rsplit(".", 1)[-1].casefold() if "." in filename else ""
    try:
        if suffix == "pdf":
            reader = PdfReader(io.BytesIO(content), strict=True)
            sections = [
                ExtractedSection(_normalize_text(page.extract_text() or ""), index)
                for index, page in enumerate(reader.pages, start=1)
            ]
        elif suffix == "docx":
            if not has_safe_docx_archive(content):
                raise ProcessingError("Document content is not a valid or safe DOCX file.")
            document = WordDocument(io.BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            sections = [ExtractedSection(_normalize_text(text))]
        elif suffix in {"txt", "md"}:
            sections = [ExtractedSection(_normalize_text(content.decode("utf-8-sig")))]
        else:
            raise ProcessingError("Unsupported document format.")
    except (UnicodeDecodeError, ValueError) as error:
        raise ProcessingError("Document text could not be extracted.") from error
    except Exception as error:
        if isinstance(error, ProcessingError):
            raise
        raise ProcessingError("Document text could not be extracted.") from error

    sections = [section for section in sections if section.text]
    if not sections:
        raise ProcessingError("No extractable text was found in the document.")
    return sections


def chunk_sections(
    sections: Sequence[ExtractedSection], chunk_size: int, chunk_overlap: int
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

    chunks: list[TextChunk] = []
    for section in sections:
        start = 0
        text = section.text
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + 1, end + 1)
                if boundary > start:
                    end = boundary
            chunk_text = text[start:end].strip()
            if chunk_text:
                actual_start = start + len(text[start:end]) - len(text[start:end].lstrip())
                chunks.append(
                    TextChunk(
                        sequence_number=len(chunks),
                        text=chunk_text,
                        page_number=section.page_number,
                        start_offset=actual_start,
                        end_offset=actual_start + len(chunk_text),
                    )
                )
            if end == len(text):
                break
            start = max(end - chunk_overlap, start + 1)
            while start < len(text) and text[start].isspace():
                start += 1
    return chunks


def process_next_job(
    session_factory: sessionmaker[Session],
    storage: LocalFileStorage,
    embedding_provider: EmbeddingProvider,
    settings: Settings,
) -> bool:
    job_id = _claim_job(session_factory, settings)
    if job_id is None:
        return False

    try:
        with session_factory() as session:
            job = session.get(ProcessingJob, job_id)
            if job is None:
                raise ProcessingError("Processing job no longer exists.")
            version = session.get(DocumentVersion, job.document_version_id)
            if version is None:
                raise ProcessingError("Document version no longer exists.")
            document = session.get(Document, version.document_id)
            if document is None:
                raise ProcessingError("Document no longer exists.")
            filename = document.filename
            storage_key = document.storage_key
            version_id = version.id

        content = storage.read(storage_key)
        sections = extract_sections(filename, content)
        chunks = chunk_sections(sections, settings.chunk_size, settings.chunk_overlap)
        vectors = embedding_provider.embed([chunk.text for chunk in chunks])
        _validate_embeddings(vectors, len(chunks))

        with session_factory() as session:
            job = session.get(ProcessingJob, job_id)
            version = session.get(DocumentVersion, version_id)
            document = session.scalar(
                select(Document).join(DocumentVersion).where(DocumentVersion.id == version_id)
            )
            if job is None or version is None or document is None:
                raise ProcessingError("Document was deleted during processing.")
            if job.status != "processing":
                raise ProcessingError("Processing job is no longer active.")

            session.execute(delete(Chunk).where(Chunk.document_version_id == version.id))
            session.add_all(
                [
                    Chunk(
                        document_version_id=version.id,
                        sequence_number=chunk.sequence_number,
                        text=chunk.text,
                        page_number=chunk.page_number,
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        embedding=vector,
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ]
            )
            version.status = "ready"
            document.status = "ready"
            document.processing_error = None
            job.status = "completed"
            job.last_error = None
            session.commit()
        logger.info("document_processing_completed job_id=%s chunk_count=%s", job_id, len(chunks))
        return True
    except Exception as error:
        logger.error(
            "document_processing_failed job_id=%s error_type=%s",
            job_id,
            type(error).__name__,
        )
        _mark_job_failed(session_factory, job_id, _safe_error_message(error))
        return True


def _claim_job(session_factory: sessionmaker[Session], settings: Settings) -> str | None:
    try:
        with session_factory() as session:
            stale_before = datetime.now(timezone.utc) - timedelta(
                seconds=settings.processing_job_timeout_seconds
            )
            job = session.scalar(
                select(ProcessingJob)
                .join(DocumentVersion, ProcessingJob.document_version_id == DocumentVersion.id)
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(
                    or_(
                        (ProcessingJob.status == "queued") & (Document.status == "queued"),
                        (ProcessingJob.status == "processing")
                        & (ProcessingJob.updated_at < stale_before)
                        & (Document.status == "processing"),
                    )
                )
                .order_by(ProcessingJob.created_at, ProcessingJob.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.status = "processing"
            job.attempts += 1
            job.last_error = None
            version = session.get(DocumentVersion, job.document_version_id)
            if version is None:
                job.status = "failed"
                job.last_error = "Document version no longer exists."
                session.commit()
                return job.id
            version.status = "processing"
            document = session.get(Document, version.document_id)
            if document is not None:
                document.status = "processing"
            session.commit()
            return job.id
    except SQLAlchemyError:
        logger.exception("document_job_claim_failed")
        raise


def _mark_job_failed(session_factory: sessionmaker[Session], job_id: str, message: str) -> None:
    try:
        with session_factory() as session:
            job = session.get(ProcessingJob, job_id)
            if job is None:
                return
            job.status = "failed"
            job.last_error = message
            version = session.get(DocumentVersion, job.document_version_id)
            if version is not None:
                version.status = "failed"
                document = session.get(Document, version.document_id)
                if document is not None:
                    document.status = "failed"
                    document.processing_error = message
            session.commit()
    except SQLAlchemyError:
        logger.exception("document_job_failure_state_write_failed job_id=%s", job_id)
        raise


def _safe_error_message(error: Exception) -> str:
    if isinstance(error, ProcessingError):
        return str(error)
    return "Document processing failed. Check service configuration and retry."


def _validate_embeddings(vectors: list[list[float]], expected_count: int) -> None:
    if len(vectors) != expected_count:
        raise ProcessingError("Embedding provider returned an unexpected number of vectors.")
    if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
        raise ProcessingError(
            f"Embedding provider must return {EMBEDDING_DIMENSIONS}-dimensional vectors."
        )
    if any(
        not isinstance(value, (float, int)) or not math.isfinite(value)
        for vector in vectors
        for value in vector
    ):
        raise ProcessingError("Embedding provider returned invalid vector values.")
    if any(not any(vector) for vector in vectors):
        raise ProcessingError("Embedding provider returned a zero vector.")


def _normalize_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
