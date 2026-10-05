from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCUMIND_", env_file=".env", extra="ignore")

    api_token: SecretStr | None = None
    api_token_subject: str = "local-owner"
    database_url: str = "sqlite:///./var/documind.db"
    storage_path: Path = Path("var/uploads")
    web_static_path: Path | None = None
    max_upload_bytes: int = 10 * 1024 * 1024
    chunk_size: int = Field(default=1000, gt=0)
    chunk_overlap: int = Field(default=150, ge=0)
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    retrieval_min_similarity: float = Field(default=0.2, ge=-1, le=1)
    processing_job_timeout_seconds: int = Field(default=900, gt=0)
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: SecretStr | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_embedding_deployment: str | None = None
    azure_openai_chat_deployment: str | None = None

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self
