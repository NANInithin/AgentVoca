"""Tests for ``observer/export/json_sidecar.py`` (OBS-24).

Validates the v0.5.0 Agent contract (contracts \xa75): the
``schema`` field, the ``blocks[]`` shape, and the invariant that
``blob_path`` is relative.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from agentvoca.config.schema import ObserverCompileConfig
from agentvoca.observer.compile.base import split_blocks
from agentvoca.observer.compile.rules import RulesCompiler
from agentvoca.observer.export.json_sidecar import JsonExporter
from agentvoca.observer.models import (
    CompiledSession,
    ObserverEvent,
    ObserverSession,
    SessionBundle,
)
from agentvoca.observer.store import ObserverStore


async def _build(tmp_path: Path) -> tuple[SessionBundle, CompiledSession]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        session = build_fixture_session(store)
        bundle = store.load_bundle(session_id=session.id)
    finally:
        store.stop()
    compiled = await RulesCompiler(ObserverCompileConfig(provider="rules")).compile(bundle)
    return bundle, compiled


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_json_writes_to_expected_path(tmp_path: Path) -> None:
    bundle, compiled = await _build(tmp_path)
    out_dir = tmp_path / "exports"
    exporter = JsonExporter(bundle, out_dir)
    result = await exporter.export(compiled)
    expected = out_dir / bundle.session.uuid / "session.json"
    assert Path(result) == expected
    assert expected.is_file()


@pytest.mark.asyncio
async def test_json_validates_against_contract_v1(tmp_path: Path) -> None:
    """Every required key in contracts \xa75 is present and well-typed."""
    bundle, compiled = await _build(tmp_path)
    out_dir = tmp_path / "exports"
    exporter = JsonExporter(bundle, out_dir)
    path = await exporter.export(compiled)
    doc = _load(Path(path))

    assert doc["schema"] == "agentvoca.observer.session/1"
    session = doc["session"]
    assert session["uuid"] == bundle.session.uuid
    assert isinstance(session["started_at_ms"], int)
    assert session["ended_at_ms"] is None or isinstance(session["ended_at_ms"], int)
    assert isinstance(session["duration_ms"], int)
    assert session["app_version"] == bundle.session.app_version
    assert session["compiler"] == "rules"
    assert session["degraded"] is False

    assert "summary" in doc
    assert isinstance(doc["summary"], str)
    assert isinstance(doc["blocks"], list)
    assert len(doc["blocks"]) == 3  # the fixture's three blocks

    # Per-block shape.
    for b in doc["blocks"]:
        assert isinstance(b["index"], int)
        assert isinstance(b["started_at_ms"], int)
        assert isinstance(b["ended_at_ms"], int)
        assert isinstance(b["app_name"], str)
        assert isinstance(b["window_title"], str)
        assert isinstance(b["summary"], str)
        for key in ("utterances", "selections", "keyframes", "gaps"):
            assert key in b
            assert isinstance(b[key], list)

    # Utterance shape.
    u = doc["blocks"][0]["utterances"][0]
    assert set(u.keys()) == {"ts_ms", "text", "source"}
    assert u["source"] in ("ambient", "dictated")

    # Selection shape.
    s = doc["blocks"][0]["selections"][0]
    assert set(s.keys()) == {"ts_ms", "text", "method", "truncated"}
    assert s["method"] in ("uia", "ocr_rect")
    assert isinstance(s["truncated"], bool)

    # Keyframe shape.
    k = doc["blocks"][0]["keyframes"][0]
    assert set(k.keys()) == {"ts_ms", "blob_path", "trigger", "ocr_text"}

    # Gap shape.
    g = doc["blocks"][1]["gaps"][0]
    assert set(g.keys()) == {"ts_ms", "reason", "dropped"}


@pytest.mark.asyncio
async def test_block_boundaries_match_split_blocks(tmp_path: Path) -> None:
    """The JSON block list and ``split_blocks`` agree on boundaries."""
    bundle, compiled = await _build(tmp_path)
    out_dir = tmp_path / "exports"
    exporter = JsonExporter(bundle, out_dir)
    path = await exporter.export(compiled)
    doc = _load(Path(path))
    expected_blocks = split_blocks(bundle)
    assert len(doc["blocks"]) == len(expected_blocks)
    for b, ev in zip(doc["blocks"], expected_blocks, strict=True):
        assert b["started_at_ms"] == ev[0].ts_ms
        assert b["ended_at_ms"] == ev[-1].ts_ms


@pytest.mark.asyncio
async def test_blob_paths_are_relative(tmp_path: Path) -> None:
    """``blob_path`` MUST be relative so the storage dir is movable."""
    bundle, compiled = await _build(tmp_path)
    out_dir = tmp_path / "exports"
    exporter = JsonExporter(bundle, out_dir)
    path = await exporter.export(compiled)
    doc = _load(Path(path))
    for b in doc["blocks"]:
        for kf in b["keyframes"]:
            assert kf["blob_path"]
            # ``os.path.isabs`` is the source of truth; the
            # fixtures store ``blobs/<uuid>/<ts>-<seq>.jpg`` which
            # is relative.
            from os.path import isabs

            assert not isabs(kf["blob_path"])


@pytest.mark.asyncio
async def test_non_ascii_survives_round_trip(tmp_path: Path) -> None:
    bundle = SessionBundle(
        session=ObserverSession(
            id=1,
            uuid="u",
            started_at_ms=1_768_466_400_000,
            ended_at_ms=1_768_466_500_000,
            status="closed",
            app_version="0.4.0",
            schema_version=1,
        ),
        events=[],
    )
    exporter = JsonExporter(bundle, tmp_path / "exports")
    compiled = CompiledSession(
        markdown="# \u4f60\u597d",
        summary="\u4e2d\u6587 \u00e9 \U0001f31f",
        blocks=[],
        provider="rules",
        degraded=False,
    )
    path = await exporter.export(compiled)
    doc = _load(Path(path))
    assert doc["summary"] == "\u4e2d\u6587 \u00e9 \U0001f31f"


@pytest.mark.asyncio
async def test_atomic_no_tmp_remains(tmp_path: Path) -> None:
    bundle, compiled = await _build(tmp_path)
    out_dir = tmp_path / "exports"
    exporter = JsonExporter(bundle, out_dir)
    path = await exporter.export(compiled)
    target = Path(path)
    assert not target.with_name(target.name + ".tmp").exists()


@pytest.mark.asyncio
async def test_empty_bundle_is_a_valid_document(tmp_path: Path) -> None:
    """An empty bundle still produces a valid (but block-less) JSON."""
    bundle = SessionBundle(
        session=ObserverSession(
            id=0,
            uuid="empty",
            started_at_ms=1_768_466_400_000,
            ended_at_ms=1_768_466_500_000,
            status="closed",
            app_version="0.4.0",
            schema_version=1,
        ),
        events=[],
    )
    compiled = CompiledSession(
        markdown="# empty",
        summary="",
        blocks=[],
        provider="rules",
        degraded=False,
    )
    exporter = JsonExporter(bundle, tmp_path / "exports")
    path = await exporter.export(compiled)
    doc = _load(Path(path))
    assert doc["blocks"] == []
    assert doc["session"]["uuid"] == "empty"


@pytest.mark.asyncio
async def test_includes_keyframes_with_relative_paths(tmp_path: Path) -> None:
    """A keyframe event with a relative blob_path lands in the JSON."""
    bundle = SessionBundle(
        session=ObserverSession(
            id=1,
            uuid="u",
            started_at_ms=1_768_466_400_000,
            ended_at_ms=1_768_466_500_000,
            status="closed",
            app_version="0.4.0",
            schema_version=1,
        ),
        events=[
            ObserverEvent(
                id=1,
                session_id=1,
                ts_ms=1_768_466_400_000,
                kind="focus_change",
                app_name="chrome.exe",
                window_title="T",
            ),
            ObserverEvent(
                id=2,
                session_id=1,
                ts_ms=1_768_466_401_000,
                kind="keyframe",
                app_name="chrome.exe",
                window_title="T",
                text="hello world",
                blob_path="blobs/u/0-0.jpg",
                meta={"trigger": "window_change", "dhash": 1, "width": 1280, "height": 720},
            ),
        ],
    )
    compiled = CompiledSession(
        markdown="x", summary="", blocks=[], provider="rules", degraded=False
    )
    exporter = JsonExporter(bundle, tmp_path / "exports")
    path = await exporter.export(compiled)
    doc = _load(Path(path))
    assert doc["blocks"][0]["keyframes"][0]["blob_path"] == "blobs/u/0-0.jpg"
    assert doc["blocks"][0]["keyframes"][0]["trigger"] == "window_change"
    assert doc["blocks"][0]["keyframes"][0]["ocr_text"] == "hello world"
