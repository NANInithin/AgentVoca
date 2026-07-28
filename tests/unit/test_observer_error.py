"""Tests for the exception hierarchy in agentvoca.utils.errors."""

from __future__ import annotations

import pytest

from agentvoca.utils.errors import AgentVocaError, ObserverError


class TestObserverError:
    def test_subclasses_agent_voca_error(self) -> None:
        assert issubclass(ObserverError, AgentVocaError)
        assert issubclass(ObserverError, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(ObserverError, match="boom"):
            raise ObserverError("boom")

    def test_caught_as_agent_voca_error(self) -> None:
        """Callers that catch AgentVocaError also catch ObserverError."""
        with pytest.raises(AgentVocaError):
            raise ObserverError("anything")
