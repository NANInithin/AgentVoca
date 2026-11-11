"""VAD.is_speech scores each 512-sample silero window of a capture block."""

from __future__ import annotations

import numpy as np

from agentvoca.audio.vad import VAD


class _FakeModel:
    def __init__(self, probs: list[float]) -> None:
        self._probs = iter(probs)
        self.sizes: list[int] = []

    def __call__(self, chunk, _sr: int):
        self.sizes.append(int(chunk.shape[-1]))
        return _Prob(next(self._probs))


class _Prob:
    def __init__(self, value: float) -> None:
        self._value = value

    def item(self) -> float:
        return self._value


def _block(frames: int = 1024) -> bytes:
    return np.zeros(frames, dtype=np.float32).tobytes()


def test_capture_block_split_into_silero_windows() -> None:
    vad = VAD()
    model = _FakeModel([0.1, 0.9])
    vad._model = model
    assert vad.is_speech(_block()) is True
    assert model.sizes == [512, 512]


def test_all_windows_below_threshold_is_silence() -> None:
    vad = VAD()
    vad._model = _FakeModel([0.1, 0.2])
    assert vad.is_speech(_block()) is False


def test_partial_window_is_padded() -> None:
    vad = VAD()
    model = _FakeModel([0.1, 0.1])
    vad._model = model
    assert vad.is_speech(_block(700)) is False
    assert model.sizes == [512, 512]
