import argparse
import logging
import time

from documind.config import Settings
from documind.database import create_database_engine, create_session_factory, initialize_schema
from documind.embeddings import AzureOpenAIEmbeddingProvider
from documind.processing import process_next_job
from documind.storage import LocalFileStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued DocuMind document jobs.")
    parser.add_argument("--once", action="store_true", help="Process at most one job, then exit.")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be greater than zero")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    initialize_schema(engine)
    session_factory = create_session_factory(engine)
    storage = LocalFileStorage(settings.storage_path)
    embedding_provider = AzureOpenAIEmbeddingProvider(settings)

    try:
        while True:
            found_job = process_next_job(session_factory, storage, embedding_provider, settings)
            if args.once:
                if not found_job:
                    logging.info("No queued document jobs.")
                break
            if not found_job:
                time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        logging.info("Document worker stopping.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
