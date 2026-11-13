"""Windows CUDA DLL discovery for pip-installed NVIDIA wheels."""

from __future__ import annotations

import os
import site
import sys

from agentvoca.asr import faster_whisper


def _fake_site(tmp_path):
    for pkg in ("cublas", "cudnn"):
        (tmp_path / "nvidia" / pkg / "bin").mkdir(parents=True)
    (tmp_path / "nvidia" / "no_bin").mkdir()
    return [str(tmp_path / "nvidia" / p / "bin") for p in ("cublas", "cudnn")]


def test_bin_dirs_are_prepended_to_path(tmp_path, monkeypatch):
    expected = _fake_site(tmp_path)
    added: list[str] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(site, "getsitepackages", lambda: [str(tmp_path)])
    monkeypatch.setattr(site, "getusersitepackages", lambda: "")
    monkeypatch.setattr(os, "add_dll_directory", added.append, raising=False)
    monkeypatch.setenv("PATH", "sys32")

    faster_whisper._register_cuda_dlls()

    assert added == expected
    assert os.environ["PATH"].split(os.pathsep) == [*expected, "sys32"]


def test_path_is_not_duplicated_on_repeat(tmp_path, monkeypatch):
    expected = _fake_site(tmp_path)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(site, "getsitepackages", lambda: [str(tmp_path)])
    monkeypatch.setattr(site, "getusersitepackages", lambda: "")
    monkeypatch.setattr(os, "add_dll_directory", lambda _p: None, raising=False)
    monkeypatch.setenv("PATH", "")

    faster_whisper._register_cuda_dlls()
    faster_whisper._register_cuda_dlls()

    assert os.environ["PATH"].split(os.pathsep) == expected


def test_noop_off_windows(tmp_path, monkeypatch):
    _fake_site(tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(site, "getsitepackages", lambda: [str(tmp_path)])
    monkeypatch.setenv("PATH", "/usr/bin")

    faster_whisper._register_cuda_dlls()

    assert os.environ["PATH"] == "/usr/bin"
