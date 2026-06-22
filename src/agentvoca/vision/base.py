"""Vision provider abstract base class (v3).

All vision/VLM adapters must subclass ``VisionProvider`` and implement the
required methods. The orchestrator constructs instances via the provider
registry. A vision provider turns a captured screenshot plus the spoken
dictation (used as the extraction instruction) into clean markdown/text.
"""

from abc import ABC, abstractmethod
from typing import Optional

from agentvoca.core.types import VisionContext


class VisionProvider(ABC):
    """Abstract base class for screenshot-to-text vision providers.

    Implementations must handle their own internal errors and surface them
    as ``VisionError`` (or a subclass) defined in ``agentvoca.utils.errors``.
    """

    async def warm_up(self) -> None:
        """Prime connection pool / load local model. Must not raise. Default no-op."""
        return None

    @abstractmethod
    def get_name(self) -> str:
        """Return the registry key for this provider."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider can accept requests right now.

        This should check that required models are loaded, API keys are
        configured, or remote endpoints are reachable.
        """

    @abstractmethod
    async def extract(
        self,
        image_data: bytes,
        instruction: str,
        context: Optional[VisionContext] = None,
        mime_type: str = "image/png",
    ) -> str:
        """Extract the useful content of an image as markdown/text.

        The ``instruction`` is the spoken dictation; the model uses it to
        decide the output shape (e.g. "make a table of the expenses" yields a
        markdown table, "describe the chart" yields prose). The result must be
        the extracted content only — no preamble such as "Here is the table:".

        Must never return content that mangles code identifiers, paths, URLs,
        or numeric values unless ``context.preserve_code`` is explicitly False.
        On any internal failure, raise ``VisionError``.

        Args:
            image_data: Encoded image bytes.
            instruction: The spoken dictation text guiding extraction.
            context: Optional style/preservation hints.
            mime_type: MIME type of ``image_data``.

        Returns:
            The extracted content as a string.
        """
