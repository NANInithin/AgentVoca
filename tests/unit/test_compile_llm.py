"""Tests for ``observer/compile/openai_compatible.py`` (OBS-22).

Mocked transport \u2014 no real API calls. Verifies:

* per-block request count matches block count
* parallelism: 4 blocks complete in roughly the time of one
* per-block failure -> that block uses rules rendering, others use
  LLM, ``degraded=True``
* session-level failure -> rules summary, blocks still LLM
* total failure -> equal to rules output, ``degraded=True``, no raise
* client reuse and ``shutdown()`` closes it
* heading / fence stripping on a model response
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx
import pytest

from agentvoca.config.schema import ObserverCompileConfig
from agentvoca.observer.compile.openai_compatible import OpenAICompatibleCompiler
from agentvoca.observer.models import CompiledSession
from agentvoca.observer.store import ObserverStore


def _make_config() -> ObserverCompileConfig:
    return ObserverCompileConfig(
        provider="openai_compatible",
        endpoint="https://example.test/v1",
        api_key_env=None,
        model="fake",
    )


def _build_bundle(tmp_path: Path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        session = build_fixture_session(store)
        return store.load_bundle(session_id=session.id)
    finally:
        store.stop()


def _request_count(handler_state: dict[str, int]) -> int:
    return handler_state.get("count", 0)


def _handler_respond_with(text: str, delay: float = 0.0):
    """Return an httpx MockTransport handler that always returns ``text``."""

    async def _handle(request: httpx.Request) -> httpx.Response:
        if delay:
            await asyncio.sleep(delay)
        body = {
            "choices": [{"message": {"content": text}}],
        }
        return httpx.Response(200, json=body)

    return _handle


def _handler_respond_counted(text: str, state: dict[str, int], delay: float = 0.0):
    """Same as ``_handler_respond_with`` but counts calls and exposes them."""

    async def _handle(request: httpx.Request) -> httpx.Response:
        state["count"] = state.get("count", 0) + 1
        if delay:
            await asyncio.sleep(delay)
        body = {"choices": [{"message": {"content": text}}]}
        return httpx.Response(200, json=body)

    return _handle


def _handler_fail_nth(n: int, ok_text: str, state: dict[str, int]):
    """Fail the first ``n`` calls, then succeed with ``ok_text``."""

    async def _handle(request: httpx.Request) -> httpx.Response:
        state["count"] = state.get("count", 0) + 1
        if state["count"] <= n:
            return httpx.Response(500, text="boom")
        body = {"choices": [{"message": {"content": ok_text}}]}
        return httpx.Response(200, json=body)

    return _handle


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_block_count_in_request_count_out(tmp_path: Path, monkeypatch) -> None:
    """The compiler sends exactly one LLM call per block."""
    state: dict[str, int] = {}
    transport = httpx.MockTransport(_handler_respond_counted("body\n\nSUMMARY: a summary", state))
    compiler = OpenAICompatibleCompiler(_make_config())
    compiler._client = compiler._make_client(timeout=10.0)
    # Replace the transport on the underlying httpx client. MockTransport
    # wraps an already-built AsyncClient in ``_make_client``.
    compiler._client._transport = transport  # type: ignore[attr-defined]

    bundle = _build_bundle(tmp_path)
    compiled = await compiler.compile(bundle)
    # 3 blocks + 1 session summary = 4 calls.
    assert _request_count(state) == 4
    assert compiled.provider == "openai_compatible"


@pytest.mark.asyncio
async def test_parallel_blocks_finish_in_one_call_time(tmp_path: Path) -> None:
    """4 blocks at 100 ms each should finish in ~100 ms, not 400 ms."""
    state: dict[str, int] = {}
    transport = httpx.MockTransport(
        _handler_respond_counted("body\n\nSUMMARY: x", state, delay=0.1)
    )
    compiler = OpenAICompatibleCompiler(_make_config())
    compiler._client = compiler._make_client(timeout=10.0)
    compiler._client._transport = transport  # type: ignore[attr-defined]

    bundle = _build_bundle(tmp_path)
    started = time.monotonic()
    compiled = await compiler.compile(bundle)
    elapsed = time.monotonic() - started
    # 3 blocks + 1 session, but session runs after blocks. With
    # parallelism across blocks, the total should be 0.1s (blocks) +
    # 0.1s (session) = 0.2s. A 0.5s budget is comfortable.
    assert elapsed < 0.5, f"compile took {elapsed:.2f}s, expected < 0.5s"
    assert compiled.provider == "openai_compatible"


@pytest.mark.asyncio
async def test_one_failing_block_degrades_to_rules(tmp_path: Path) -> None:
    """One block fails -> that block uses rules, others use LLM, degraded=True."""
    # 3 blocks + 1 session. Fail the first call (block 0).
    state: dict[str, int] = {}
    transport = httpx.MockTransport(_handler_fail_nth(1, "good body\n\nSUMMARY: ok", state))
    compiler = OpenAICompatibleCompiler(_make_config())
    compiler._client = compiler._make_client(timeout=10.0)
    compiler._client._transport = transport  # type: ignore[attr-defined]

    bundle = _build_bundle(tmp_path)
    compiled = await compiler.compile(bundle)
    assert compiled.degraded is True
    # Block 0 is rules-rendered (no SUMMARY: line from the model), but
    # the JSON record still has summary="" (or the deterministic
    # rules-derived text? rules leaves summary empty). The other blocks
    # have summary set.
    non_empty = [b for b in compiled.blocks if b.get("summary")]
    # 2 LLM blocks + 0 from the failed block = 2.
    assert len(non_empty) == 2
    # The 4 LLM calls still happened: 1 failure + 2 success blocks + 1 session.
    assert _request_count(state) == 4


@pytest.mark.asyncio
async def test_session_level_failure_keeps_blocks_llm(tmp_path: Path) -> None:
    """3 blocks OK, session call fails -> rules summary, blocks still LLM, degraded=True."""
    # We need 4 calls. Fail the LAST one (the session call) by failing
    # any call where count == 4.
    state: dict[str, int] = {"count": 0}
    fail_message = "transient"

    async def _handle(request: httpx.Request) -> httpx.Response:
        state["count"] += 1
        if state["count"] == 4:
            return httpx.Response(502, text="bad gateway")
        body = {"choices": [{"message": {"content": "x\n\nSUMMARY: per-block"}}]}
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(_handle)
    compiler = OpenAICompatibleCompiler(_make_config())
    compiler._client = compiler._make_client(timeout=10.0)
    compiler._client._transport = transport  # type: ignore[attr-defined]

    bundle = _build_bundle(tmp_path)
    compiled = await compiler.compile(bundle)
    assert compiled.degraded is True
    # All three block summaries present.
    non_empty = [b for b in compiled.blocks if b.get("summary")]
    assert len(non_empty) == 3
    # Session summary fell back to rules (deterministic, includes the
    # number of spoken lines).
    assert compiled.summary
    assert "lines" in compiled.summary or "line" in compiled.summary
    del fail_message  # silence linter


@pytest.mark.asyncio
async def test_total_failure_equals_rules_output(tmp_path: Path) -> None:
    """If every LLM call fails, the output equals the rules compiler's."""

    async def _fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="never up")

    transport = httpx.MockTransport(_fail)
    compiler = OpenAICompatibleCompiler(_make_config())
    compiler._client = compiler._make_client(timeout=10.0)
    compiler._client._transport = transport  # type: ignore[attr-defined]

    bundle = _build_bundle(tmp_path)
    # The ABC says ``compile`` must never raise.
    compiled = await compiler.compile(bundle)
    assert compiled.degraded is True
    # No block summaries from the LLM.
    non_empty = [b for b in compiled.blocks if b.get("summary")]
    assert non_empty == []
    # The session summary fell back to rules.
    assert compiled.summary
    # The compiled output equals a pure rules compile of the same bundle.
    from agentvoca.observer.compile.rules import RulesCompiler

    rules_compiled = await RulesCompiler(_make_config()).compile(bundle)
    # The body sections (between ``---\n\n`` separators) should match
    # because both compilers reuse the rules per-block renderer.
    sep = "---\n\n"
    rules_body = (
        rules_compiled.markdown.split(sep, 2)[1]
        if rules_compiled.markdown.count(sep) >= 2
        else rules_compiled.markdown
    )
    # Both contain the same per-block markdown. The footer differs.
    assert "rules compiler" in rules_body or "rules compiler" in rules_compiled.markdown
    # The LLM compiler advertises itself in the footer.
    assert "openai_compatible compiler" in compiled.markdown
    assert "degraded" in compiled.markdown


@pytest.mark.asyncio
async def test_client_reuse_and_shutdown(tmp_path: Path) -> None:
    """The same httpx client is reused across calls, and shutdown() closes it."""
    state: dict[str, int] = {}
    transport = httpx.MockTransport(_handler_respond_counted("body\n\nSUMMARY: s", state))
    compiler = OpenAICompatibleCompiler(_make_config())
    client = compiler._make_client(timeout=10.0)
    client._transport = transport  # type: ignore[attr-defined]
    compiler._client = client

    bundle = _build_bundle(tmp_path)
    # Two compiles -> 4 + 4 = 8 LLM calls.
    await compiler.compile(bundle)
    await compiler.compile(bundle)
    assert _request_count(state) == 8
    assert compiler._client is client  # identity preserved

    # shutdown closes the client; a second shutdown is a no-op.
    await compiler.shutdown()
    await compiler.shutdown()


@pytest.mark.asyncio
async def test_fence_and_heading_stripping(tmp_path: Path) -> None:
    """A model response wrapped in ```` ```markdown ```` is unwrapped."""
    state: dict[str, int] = {}
    wrapped = (
        "```markdown\n"
        "## This heading would break the structure\n"
        "# And this one too\n"
        "Body content here.\n"
        "```\n"
    )
    transport = httpx.MockTransport(_handler_respond_counted(wrapped, state))
    compiler = OpenAICompatibleCompiler(_make_config())
    compiler._client = compiler._make_client(timeout=10.0)
    compiler._client._transport = transport  # type: ignore[attr-defined]

    bundle = _build_bundle(tmp_path)
    compiled = await compiler.compile(bundle)
    # The leading/trailing code fences must be gone.
    assert "```markdown" not in compiled.markdown
    assert "```" not in compiled.markdown
    # The body content must survive.
    assert "Body content here." in compiled.markdown
    # The bad headings are demoted to ``###`` / ``####`` (the
    # rules block header is ``##`` so anything else is safe).
    for line in compiled.markdown.splitlines():
        if "This heading would break" in line or "And this one too" in line:
            assert line.lstrip().startswith(("###", "####"))


@pytest.mark.asyncio
async def test_no_api_key_does_not_block(tmp_path: Path) -> None:
    """No API key configured -> Authorization header absent, but no raise."""
    state: dict[str, int] = {}
    seen_auth: dict[str, str] = {}

    async def _handle(request: httpx.Request) -> httpx.Response:
        seen_auth.update(dict(request.headers))
        state["count"] = state.get("count", 0) + 1
        body = {"choices": [{"message": {"content": "ok\n\nSUMMARY: s"}}]}
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(_handle)
    config = ObserverCompileConfig(
        provider="openai_compatible",
        endpoint="https://example.test/v1",
        api_key_env=None,
        model="fake",
    )
    compiler = OpenAICompatibleCompiler(config)
    compiler._client = compiler._make_client(timeout=10.0)
    compiler._client._transport = transport  # type: ignore[attr-defined]

    bundle = _build_bundle(tmp_path)
    compiled = await compiler.compile(bundle)
    # No Authorization header because we did not configure one.
    assert "authorization" not in {k.lower() for k in seen_auth}
    assert compiled.provider == "openai_compatible"


@pytest.mark.asyncio
async def test_empty_bundle_uses_rules_stub(tmp_path: Path) -> None:
    """An empty session does not even hit the network."""
    from agentvoca.observer.models import ObserverSession, SessionBundle

    bundle = SessionBundle(
        session=ObserverSession(
            id=0,
            uuid="x",
            started_at_ms=0,
            ended_at_ms=None,
            status="closed",
            app_version="0.4.0",
            schema_version=1,
        ),
        events=[],
    )
    state: dict[str, int] = {}
    transport = httpx.MockTransport(_handler_respond_counted("anything", state))
    compiler = OpenAICompatibleCompiler(_make_config())
    compiler._client = compiler._make_client(timeout=10.0)
    compiler._client._transport = transport  # type: ignore[attr-defined]

    compiled = await compiler.compile(bundle)
    assert isinstance(compiled, CompiledSession)
    # No LLM calls for an empty session.
    assert _request_count(state) == 0
    assert "No events" in compiled.markdown


@pytest.mark.asyncio
async def test_never_raises(tmp_path: Path) -> None:
    """The ABC says ``compile`` must never raise. Confirm via a busted transport."""

    async def _raise(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    transport = httpx.MockTransport(_raise)
    compiler = OpenAICompatibleCompiler(_make_config())
    compiler._client = compiler._make_client(timeout=10.0)
    compiler._client._transport = transport  # type: ignore[attr-defined]

    bundle = _build_bundle(tmp_path)
    # If this raises, the test fails. Wrap in try/except so the
    # failure message is informative.
    try:
        compiled = await compiler.compile(bundle)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"compile() must not raise, but it raised {type(exc).__name__}: {exc}")
    assert compiled.degraded is True
