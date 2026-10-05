from collections.abc import Sequence

from openai import AzureOpenAI

from documind.config import Settings
from documind.processing import ProcessingError


class AzureOpenAIEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: AzureOpenAI | None = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
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
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]
