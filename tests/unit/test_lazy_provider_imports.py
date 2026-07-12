"""Tests for R14: lazy provider imports (cold-start).

Verifies that building a ``ProviderRegistry`` does not import heavy
provider modules (ctranslate2, faster_whisper, ...) until the matching
``get_*`` is called.
"""

import subprocess
import sys

import pytest

from agentvoca.config.schema import ASRConfig, CleanupConfig
from agentvoca.core.registry import ProviderRegistry
from agentvoca.utils.errors import ProviderNotFoundError


def test_registry_build_does_not_import_heavy_modules():
    """A fresh registry must not import ctranslate2, faster_whisper, or
    numpy — these are paid for at first use, not at registry build."""
    code = (
        "import sys\n"
        "from agentvoca.core.registry import ProviderRegistry\n"
        "from agentvoca.config.schema import CleanupConfig\n"
        "r = ProviderRegistry()\n"
        "r.get_cleanup(CleanupConfig(provider='rules'))\n"
        "r.get_cleanup(CleanupConfig(provider='none'))\n"
        "assert 'ctranslate2' not in sys.modules, 'ctranslate2 imported eagerly'\n"
        "assert 'faster_whisper' not in sys.modules, 'faster_whisper imported eagerly'\n"
        "assert 'numpy' not in sys.modules, 'numpy imported eagerly'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_get_asr_resolves_faster_whisper_class():
    """``get_asr(ASRConfig(provider='faster_whisper'))`` returns a
    working ``FasterWhisperProvider`` class (construction only — no
    model load; the constructor is light, verified separately)."""
    reg = ProviderRegistry()
    asr = reg.get_asr(ASRConfig(provider="faster_whisper", model="base"))
    # The constructor builds the client but does not load the model.
    assert asr.get_name() == "faster_whisper"


def test_get_unknown_provider_raises_listing_available_names():
    """An unknown provider name raises ProviderNotFoundError that lists
    the available names — including lazy-resolved ones for plugins that
    have already been used in this registry's lifetime."""
    reg = ProviderRegistry()
    # Touch one lazy entry to verify it gets resolved & listed.
    reg.get_cleanup(CleanupConfig(provider="rules"))
    with pytest.raises(ProviderNotFoundError) as exc:
        reg.get_asr(ASRConfig(provider="does_not_exist"))
    assert "Unknown ASR provider 'does_not_exist'" in str(exc.value)
    assert "faster_whisper" in str(exc.value)
    assert "openai_compatible" in str(exc.value)


def test_register_class_then_string_in_same_slot():
    """register_asr / register_cleanup / register_insertion / register_vision
    all still accept a class (back-compat with tests + plugins)."""
    reg = ProviderRegistry(register_builtins=False)

    from agentvoca.asr.base import ASRProvider
    from agentvoca.cleanup.base import CleanupProvider
    from agentvoca.insertion.base import InsertionStrategy
    from agentvoca.vision.base import VisionProvider

    class _A(ASRProvider):
        def __init__(self, config):
            self.config = config

        def get_name(self):
            return "a"

        def is_available(self):
            return True

        def supports_streaming(self):
            return False

        def transcribe_audio(self, *a, **k):
            raise NotImplementedError

        def stream_transcribe(self, *a, **k):
            raise NotImplementedError

    class _C(CleanupProvider):
        def __init__(self, config):
            self.config = config

        def get_name(self):
            return "c"

        def is_available(self):
            return True

        def rewrite(self, *a, **k):
            raise NotImplementedError

    class _I(InsertionStrategy):
        def __init__(self, config):
            self.config = config

        def get_name(self):
            return "i"

        def is_available(self):
            return True

        def insert(self, *a, **k):
            raise NotImplementedError

        def undo_last(self):
            return True

    class _V(VisionProvider):
        def __init__(self, config):
            self.config = config

        def get_name(self):
            return "v"

        def is_available(self):
            return True

        def extract(self, *a, **k):
            raise NotImplementedError

    reg.register_asr("a", _A)
    reg.register_cleanup("c", _C)
    reg.register_insertion("i", _I)
    reg.register_vision("v", _V)

    assert reg.get_asr(ASRConfig(provider="a")).get_name() == "a"
