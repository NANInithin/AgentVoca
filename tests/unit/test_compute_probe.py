"""Unit tests for the auto compute-type probe (Phase E, PE-03)."""

import agentvoca.asr.faster_whisper as fw


def test_cuda_prefers_float16(monkeypatch):
    monkeypatch.setattr(
        fw.ctranslate2,
        "get_supported_compute_types",
        lambda device: {"float16", "int8", "float32"},
    )
    assert fw._probe_compute_type("cuda") == "float16"


def test_cuda_falls_through_to_int8_when_float16_unsupported(monkeypatch):
    monkeypatch.setattr(
        fw.ctranslate2,
        "get_supported_compute_types",
        lambda device: {"int8", "float32"},
    )
    assert fw._probe_compute_type("cuda") == "int8"


def test_cpu_prefers_int8(monkeypatch):
    monkeypatch.setattr(
        fw.ctranslate2,
        "get_supported_compute_types",
        lambda device: {"int8", "int8_float32", "float32"},
    )
    assert fw._probe_compute_type("cpu") == "int8"


def test_cpu_falls_back_to_float32(monkeypatch):
    monkeypatch.setattr(
        fw.ctranslate2,
        "get_supported_compute_types",
        lambda device: {"float32"},
    )
    assert fw._probe_compute_type("cpu") == "float32"


def test_probe_failure_returns_safe_default(monkeypatch):
    def _raise(device):
        raise RuntimeError("ctranslate2 unavailable")

    monkeypatch.setattr(fw.ctranslate2, "get_supported_compute_types", _raise)
    assert fw._probe_compute_type("cuda") == "float16"
    assert fw._probe_compute_type("cpu") == "int8"
