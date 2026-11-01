from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def initialize_schema(engine: Engine, embedding_model_id: str | None = None) -> None:
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    _migrate_embedding_dimensions(engine)
    document_columns = {column["name"] for column in inspect(engine).get_columns("documents")}
    if "processing_error" not in document_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN processing_error TEXT"))
    if embedding_model_id is not None:
        _validate_embedding_model(engine, embedding_model_id)


def _migrate_embedding_dimensions(engine: Engine) -> None:
    from documind.constants import EMBEDDING_DIMENSIONS

    if engine.dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector

        embedding_column = next(
            column
            for column in inspect(engine).get_columns("chunks")
            if column["name"] == "embedding"
        )
        current_type = embedding_column["type"]
        if isinstance(current_type, Vector) and current_type.dim != EMBEDDING_DIMENSIONS:
            with engine.begin() as connection:
                existing_chunks = connection.scalar(text("SELECT COUNT(*) FROM chunks"))
                if existing_chunks:
                    raise RuntimeError(
                        "The database contains embeddings with an incompatible dimension. "
                        "Re-index existing documents before switching embedding models."
                    )
                connection.execute(
                    text(
                        "ALTER TABLE chunks ALTER COLUMN embedding "
                        f"TYPE vector({EMBEDDING_DIMENSIONS}) "
                        f"USING embedding::vector({EMBEDDING_DIMENSIONS})"
                    )
                )
    elif engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            incompatible_chunks = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM chunks "
                    "WHERE json_array_length(embedding) IS NULL "
                    "OR json_array_length(embedding) != :dimensions"
                ),
                {"dimensions": EMBEDDING_DIMENSIONS},
            )
        if incompatible_chunks:
            raise RuntimeError(
                "The database contains embeddings with an incompatible dimension. "
                "Re-index existing documents before switching embedding models."
            )


def _validate_embedding_model(engine: Engine, embedding_model_id: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS documind_metadata "
                "(key VARCHAR(100) PRIMARY KEY, value TEXT NOT NULL)"
            )
        )
        recorded_model = connection.scalar(
            text("SELECT value FROM documind_metadata WHERE key = 'embedding_model'")
        )
        existing_chunks = connection.scalar(text("SELECT COUNT(*) FROM chunks"))
        if recorded_model is None:
            if existing_chunks:
                raise RuntimeError(
                    "The database contains embeddings without a recorded model identity. "
                    "Re-index existing documents before starting with a model provider."
                )
            connection.execute(
                text(
                    "INSERT INTO documind_metadata (key, value) "
                    "VALUES ('embedding_model', :embedding_model_id)"
                ),
                {"embedding_model_id": embedding_model_id},
            )
        elif recorded_model != embedding_model_id:
            if existing_chunks:
                raise RuntimeError(
                    "The configured embedding model differs from the model used for stored "
                    "vectors. Re-index existing documents before switching embedding models."
                )
            connection.execute(
                text(
                    "UPDATE documind_metadata SET value = :embedding_model_id "
                    "WHERE key = 'embedding_model'"
                ),
                {"embedding_model_id": embedding_model_id},
            )


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(connection, _record) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_dependency(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    with factory() as session:
        yield session
