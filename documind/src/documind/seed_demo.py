import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from documind.config import Settings
from documind.database import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from documind.demo_content import (
    DEMO_DOCUMENT_CONTENT,
    DEMO_DOCUMENT_FILENAME,
    DEMO_OWNER_ID,
    DEMO_WORKSPACE_NAME,
)
from documind.models import (
    Document,
    DocumentVersion,
    ProcessingJob,
    User,
    Workspace,
)
from documind.storage import LocalFileStorage

logger = logging.getLogger(__name__)


def seed_demo_workspace(
    session: Session,
    storage: LocalFileStorage,
    workspace_id: str,
) -> None:
    if not workspace_id.strip() or len(workspace_id) > 36:
        raise ValueError("A valid demo workspace ID is required.")

    workspace = session.get(Workspace, workspace_id)
    if workspace is not None and (
        not workspace.is_public_demo or workspace.name != DEMO_WORKSPACE_NAME
    ):
        raise RuntimeError(
            "The configured demo workspace ID belongs to a private or conflicting workspace."
        )

    owner = session.get(User, DEMO_OWNER_ID)
    if owner is None:
        session.add(User(id=DEMO_OWNER_ID))
        session.flush()

    if workspace is None:
        workspace = Workspace(
            id=workspace_id,
            name=DEMO_WORKSPACE_NAME,
            is_public_demo=True,
        )
        session.add(workspace)
        session.flush()

    documents = list(
        session.scalars(
            select(Document).where(Document.workspace_id == workspace_id)
        )
    )
    if documents:
        _verify_existing_fixture(session, storage, documents)
        return

    content_hash = hashlib.sha256(DEMO_DOCUMENT_CONTENT).hexdigest()
    storage_key = hashlib.sha256(
        f"documind-demo:{workspace_id}:{content_hash}".encode("utf-8")
    ).hexdigest()[:32]
    try:
        existing_file = storage.read(storage_key)
    except FileNotFoundError:
        storage.put(storage_key, DEMO_DOCUMENT_CONTENT)
    else:
        if existing_file != DEMO_DOCUMENT_CONTENT:
            raise RuntimeError("Demo storage key contains conflicting content.")

    document = Document(
        workspace_id=workspace_id,
        uploaded_by=DEMO_OWNER_ID,
        filename=DEMO_DOCUMENT_FILENAME,
        mime_type="text/plain",
        file_size=len(DEMO_DOCUMENT_CONTENT),
        sha256=content_hash,
        storage_key=storage_key,
        status="queued",
    )
    try:
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            status="queued",
        )
        session.add(version)
        session.flush()
        session.add(ProcessingJob(document_version_id=version.id, status="queued"))
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        try:
            storage.delete(storage_key)
        except OSError:
            logger.exception("demo_seed_storage_cleanup_failed")
        raise RuntimeError("Demo metadata could not be saved.") from None


def _verify_existing_fixture(
    session: Session,
    storage: LocalFileStorage,
    documents: list[Document],
) -> None:
    if len(documents) != 1:
        raise RuntimeError("The public demo workspace contains unexpected documents.")

    document = documents[0]
    if (
        document.uploaded_by != DEMO_OWNER_ID
        or document.filename != DEMO_DOCUMENT_FILENAME
        or document.sha256 != hashlib.sha256(DEMO_DOCUMENT_CONTENT).hexdigest()
        or document.file_size != len(DEMO_DOCUMENT_CONTENT)
    ):
        raise RuntimeError("The existing public demo fixture conflicts with the seed.")

    try:
        stored_content = storage.read(document.storage_key)
    except OSError as error:
        raise RuntimeError("The existing public demo file is unavailable.") from error
    if stored_content != DEMO_DOCUMENT_CONTENT:
        raise RuntimeError("The existing public demo file conflicts with the seed.")

    versions = list(
        session.scalars(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
    )
    if len(versions) != 1:
        raise RuntimeError("The existing public demo document has an invalid version.")
    jobs = list(
        session.scalars(
            select(ProcessingJob).where(
                ProcessingJob.document_version_id == versions[0].id
            )
        )
    )
    if len(jobs) != 1:
        raise RuntimeError("The existing public demo document has an invalid job.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings()
    if settings.demo_workspace_id is None:
        raise SystemExit("DOCUMIND_DEMO_WORKSPACE_ID must be configured before seeding.")

    engine = create_database_engine(settings.database_url)
    try:
        initialize_schema(engine, settings.embedding_model_id)
        session_factory = create_session_factory(engine)
        storage = LocalFileStorage(settings.storage_path)
        with session_factory() as session:
            seed_demo_workspace(session, storage, settings.demo_workspace_id)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
