# Contributing

Thanks for contributing to AgentVoca. This project favors small, focused changes with tests.

---

## Setup

```bash
# Python 3.11+ and uv required
uv sync
```

---

## Running tests

```bash
# all tests
uv run pytest

# specific module
uv run pytest tests/unit/test_state_machine.py

# with verbose output
uv run pytest -v

# stop on first failure
uv run pytest -x
```

Tests use `pytest-asyncio` in `auto` mode — async test functions are detected and run
automatically. Do not add `@pytest.mark.asyncio` decorators.

---

## Lint and format

```bash
# check for issues
uv run ruff check src/ tests/

# auto-fix fixable issues
uv run ruff check --fix src/ tests/

# format
uv run ruff format src/ tests/
```

The CI pipeline runs both lint and format checks. All PRs must pass both.
Line length limit is 100 characters (configured in `pyproject.toml`).

---

## Architecture

The app is a six-layer event-bus pipeline with an event bus at the centre.
No module calls another directly — all communication goes through the orchestrator.

Key modules:

| Module | Responsibility |
|---|---|
| `src/agentvoca/core/orchestrator.py` | Drives the pipeline; owns retry and fallback logic |
| `src/agentvoca/core/state_machine.py` | Pure state validator; no side effects |
| `src/agentvoca/core/event_bus.py` | Pub/sub message broker |
| `src/agentvoca/core/registry.py` | Provider factory; maps names to classes |
| `src/agentvoca/audio/` | Microphone capture and VAD |
| `src/agentvoca/asr/` | Speech-to-text provider adapters |
| `src/agentvoca/cleanup/` | Transcript cleanup providers |
| `src/agentvoca/insertion/` | Text insertion strategies |
| `src/agentvoca/vocab/` | Vocabulary substitution and snippet expansion |
| `src/agentvoca/config/` | Config schema and loader |
| `src/agentvoca/app/` | UI shell: tray, overlay, hotkeys, settings |

---

## Adding a provider

See [docs/providers.md](docs/providers.md) for step-by-step instructions and code
examples for:

- Adding an ASR provider
- Adding a cleanup provider
- Adding an insertion strategy

**Rules:**

- Do not change the abstract base class interfaces without an architecture review.
- Raise domain errors from `src/agentvoca/utils/errors.py`, never raw exceptions.
- Keep provider constructors compatible with the registry (accept only the config object).
- Do not add package dependencies without explicit approval.

---

## Adding tests

- Place unit tests in `tests/unit/` and integration tests in `tests/integration/`.
- Mock all network calls — do not hit real APIs in CI.
- Mock `sounddevice`, `pyautogui`, and `pyperclip` in tests that touch audio or insertion.
- Keep fixtures small and deterministic. Add audio fixtures to `tests/fixtures/audio/`.
- Integration tests should use the `EventBus` + `Orchestrator` with mock providers
  (see `tests/integration/test_pipeline.py` as a reference).

---

## PR workflow

1. Open an issue or draft PR with a short description of the change.
2. Keep changes small and scoped to one concern per PR.
3. Add or update tests for any behavioral change.
4. Update the relevant doc in `docs/` if config or behavior changes.
5. Ensure `uv run pytest` and `uv run ruff check src/ tests/` both pass.

---

## Dependency policy

New runtime dependencies require explicit approval. Before proposing a dependency:

- Check if the functionality can be achieved with the existing stack.
- Confirm the dependency supports Python 3.11–3.13 and both macOS and Windows.
- Review the dependency's license for compatibility with MIT.

Dev-only dependencies (test helpers, linting tools) have a lower bar but still require
a brief justification in the PR description.

---

## Commit style

Use short, present-tense summaries:

```
Add OpenAI-compatible ASR provider
Fix VAD silence detection timeout off-by-one
Update config reference for vocabulary.inline field
```

Do not reference issue numbers in the commit subject line — keep them in the PR
description where context is available.
