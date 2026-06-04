"""Context Engine — resolves active application, style profile, and language hints.

The context engine is an isolated module that the orchestrator consults
before cleanup to choose a style profile and language hint. It emits no
insertions and imports no other pipeline layer beyond its own files and
shared types.

Privacy: reads only app name and window title by default. Screen/clipboard
reading is off by default and requires explicit opt-in.
"""

from agentvoca.context.active_app import ActiveAppDetector
from agentvoca.context.base import ContextProvider, ResolvedContext
from agentvoca.context.language import LanguageResolver
from agentvoca.context.profiles import ProfileResolver

__all__ = [
    "ContextProvider",
    "ResolvedContext",
    "ActiveAppDetector",
    "ProfileResolver",
    "LanguageResolver",
]
