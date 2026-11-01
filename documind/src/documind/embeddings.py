from collections.abc import Sequence
import math
from typing import Literal

import httpx
from openai import AzureOpenAI

from documind.config import Settings
from documind.constants import EMBEDDING_DIMENSIONS
from documind.processing import EmbeddingProvider, ProcessingError


class AzureOpenAIEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: AzureOpenAI | None = None

    def embed(
        self,
        texts: Sequence[str],
        *,
        input_type: Literal["document", "query"] = "document",
    ) -> list[list[float]]:
        del input_type
        if not texts:
            return []
        if (
            not self.settings.azure_openai_endpoint
            or not self.settings.azure_openai_api_key
            or not self.settings.azure_openai_api_key.get_secret_value()
            or not self.settings.azure_openai_embedding_deployment
        ):
            raise ProcessingError("Azure OpenAI embedding configuration is incomplete.")

        if self._client is None:
            self._client = AzureOpenAI(
                azure_endpoint=self.settings.azure_openai_endpoint,
                api_key=self.settings.azure_openai_api_key.get_secret_value(),
                api_version=self.settings.azure_openai_api_version,
            )
        response = self._client.embeddings.create(
            input=list(texts),
            model=self.settings.azure_openai_embedding_deployment,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]


class OllamaEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed(
        self,
        texts: Sequence[str],
        *,
        input_type: Literal["document", "query"] = "document",
    ) -> list[list[float]]:
        if not texts:
            return []
        prefix = "search_query: " if input_type == "query" else "search_document: "
        try:
            response = httpx.post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/embed",
                json={
                    "model": self.settings.ollama_embedding_model,
                    "input": [f"{prefix}{text}" for text in texts],
                },
                timeout=self.settings.ollama_request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ProcessingError("Ollama embedding service is unavailable.") from error

        vectors = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ProcessingError("Ollama returned an invalid embedding batch.")
        if any(
            not isinstance(vector, list)
            or len(vector) != EMBEDDING_DIMENSIONS
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            )
            for vector in vectors
        ):
            raise ProcessingError("Ollama returned an invalid embedding vector.")
        return [[float(value) for value in vector] for vector in vectors]


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.model_provider == "ollama":
        return OllamaEmbeddingProvider(settings)
    return AzureOpenAIEmbeddingProvider(settings)
