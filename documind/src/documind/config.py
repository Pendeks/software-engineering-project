from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from documind.constants import EMBEDDING_DIMENSIONS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCUMIND_", env_file=".env", extra="ignore")

    api_token: SecretStr | None = None
    api_token_subject: str = "local-owner"
    auth_mode: Literal["local", "entra"] = "local"
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_api_audience: str | None = None
    demo_workspace_id: str | None = None
    demo_rate_limit_requests: int = Field(default=30, gt=0)
    demo_rate_limit_window_seconds: int = Field(default=60, gt=0)
    database_url: str = "sqlite:///./var/documind.db"
    storage_path: Path = Path("var/uploads")
    web_static_path: Path | None = None
    max_upload_bytes: int = 10 * 1024 * 1024
    chunk_size: int = Field(default=1000, gt=0)
    chunk_overlap: int = Field(default=150, ge=0)
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    retrieval_min_similarity: float = Field(default=0.2, ge=-1, le=1)
    processing_job_timeout_seconds: int = Field(default=900, gt=0)
    model_provider: Literal["ollama", "azure_openai"] = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_chat_model: str = "granite3.3:2b"
    ollama_request_timeout_seconds: float = Field(default=300, gt=0)
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: SecretStr | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_embedding_deployment: str | None = None
    azure_openai_chat_deployment: str | None = None

    @property
    def embedding_model_id(self) -> str:
        if self.model_provider == "ollama":
            return f"ollama:{self.ollama_embedding_model}:{EMBEDDING_DIMENSIONS}"
        return (
            f"azure_openai:{self.azure_openai_embedding_deployment or ''}:"
            f"{EMBEDDING_DIMENSIONS}"
        )

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.auth_mode == "entra":
            required_settings = {
                "entra_tenant_id": self.entra_tenant_id,
                "entra_client_id": self.entra_client_id,
                "entra_api_audience": self.entra_api_audience,
            }
            missing = [
                name
                for name, value in required_settings.items()
                if value is None or not value.strip()
            ]
            if missing:
                raise ValueError(
                    "Entra authentication requires " + ", ".join(missing) + "."
                )
        return self
