"""Wizard and settings-window page widgets.

Each page is a ``ConfigPage`` subclass bound to a ``ConfigController``.
Both the wizard (``setup.wizard``) and the tabbed settings window
(``setup.settings_window``) compose these pages.
"""

from agentvoca.setup.pages.advanced_page import AdvancedPage
from agentvoca.setup.pages.app_basics import AppBasicsPage
from agentvoca.setup.pages.asr_page import AsrPage
from agentvoca.setup.pages.audio_page import AudioPage
from agentvoca.setup.pages.base import ConfigPage
from agentvoca.setup.pages.cleanup_page import CleanupPage
from agentvoca.setup.pages.finish_page import FinishPage
from agentvoca.setup.pages.hotkeys_page import HotkeysPage
from agentvoca.setup.pages.observer_page import ObserverPage
from agentvoca.setup.pages.vocab_snippets_page import VocabSnippetsPage
from agentvoca.setup.pages.welcome import WelcomePage

__all__ = [
    "AdvancedPage",
    "AppBasicsPage",
    "AsrPage",
    "AudioPage",
    "CleanupPage",
    "ConfigPage",
    "FinishPage",
    "HotkeysPage",
    "ObserverPage",
    "VocabSnippetsPage",
    "WelcomePage",
]
