import math
from dataclasses import dataclass
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from documind.models import Chunk, Document, DocumentVersion

EMBEDDING_DIMENSIONS = 1536


class RetrievalError(Exception):
    pass


@dataclass(frozen=True)
class RetrievedSource:
    citation_number: int
    document_id: str
    document_version_id: str
    filename: str
    page_number: int | None
    start_offset: int
    end_offset: int
    text: str
    similarity: float


def retrieve_sources(
    session: Session,
    workspace_id: str,
    query_embedding: list[float],
    top_k: int,
    min_similarity: float,
) -> list[RetrievedSource]:
    _validate_query_embedding(query_embedding)
    if top_k < 1:
        raise ValueError("top_k must be greater than zero")
    if not -1 <= min_similarity <= 1:
        raise ValueError("min_similarity must be between -1 and 1")

    eligible_chunks = (
        select(Chunk, DocumentVersion, Document)
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(
            Document.workspace_id == workspace_id,
            Document.status == "ready",
            DocumentVersion.status == "ready",
        )
    )

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        distance = Chunk.embedding.cosine_distance(query_embedding)
        records = session.execute(
            select(Chunk, DocumentVersion, Document, distance.label("distance"))
            .select_from(Chunk)
            .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                Document.workspace_id == workspace_id,
                Document.status == "ready",
                DocumentVersion.status == "ready",
                distance <= 1 - min_similarity,
            )
            .order_by(distance, Chunk.id)
            .limit(top_k)
        ).all()
        scored_records = [
            (chunk, version, document, max(-1.0, min(1.0, 1 - float(distance_value))))
            for chunk, version, document, distance_value in records
        ]
    else:
        records = session.execute(eligible_chunks).all()
        scored_records = []
        for chunk, version, document in records:
            embedding = cast(list[float], chunk.embedding)
            similarity = _cosine_similarity(query_embedding, embedding)
            if similarity >= min_similarity:
                scored_records.append((chunk, version, document, similarity))
        scored_records.sort(key=lambda record: (-record[3], record[0].id))
        scored_records = scored_records[:top_k]

    return [
        RetrievedSource(
            citation_number=index,
            document_id=document.id,
            document_version_id=version.id,
            filename=document.filename,
            page_number=chunk.page_number,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            text=chunk.text,
            similarity=similarity,
        )
        for index, (chunk, version, document, similarity) in enumerate(scored_records, start=1)
    ]


def _validate_query_embedding(embedding: list[float]) -> None:
    if len(embedding) != EMBEDDING_DIMENSIONS or any(
        not math.isfinite(value) for value in embedding
    ) or not any(embedding):
        raise RetrievalError("The question embedding has an invalid shape or value.")


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(right) != EMBEDDING_DIMENSIONS or any(not math.isfinite(value) for value in right):
        raise RetrievalError("A stored document embedding has an invalid shape or value.")
    left_norm = math.sqrt(math.fsum(value * value for value in left))
    right_norm = math.sqrt(math.fsum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    dot_product = math.fsum(a * b for a, b in zip(left, right, strict=True))
    return max(-1.0, min(1.0, dot_product / (left_norm * right_norm)))
