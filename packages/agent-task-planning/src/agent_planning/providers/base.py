"""Base provider interface."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class ProviderResponse(BaseModel):
    """Response from an LLM provider."""

    content: str
    tokens_used: int = 0
    cost_usd: float = 0.0
    model: str = ""
    raw_response: dict | None = None


class BaseProvider(ABC):
    """
    Abstract base class for LLM providers.

    Implement this to add support for new providers.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        system: str | None = None,
        **kwargs,
    ) -> ProviderResponse:
        """
        Generate a completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system: Optional system prompt
            **kwargs: Provider-specific arguments

        Returns:
            ProviderResponse with the completion
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass
