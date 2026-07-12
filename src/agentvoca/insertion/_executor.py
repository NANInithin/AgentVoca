"""Single-worker executor serializing all OS input injection.

pyautogui (and the clipboard+paste dance) are not thread-safe; running an
undo concurrently with an in-flight typewrite interleaves keystrokes in the
target app. Every pyautogui/pyperclip call in the insertion package must go
through ``get_input_executor()``.

The executor is self-healing: ``shutdown_input_executor()`` shuts it down
(so a wedged pyautogui call does not delay process exit), but the next
``get_input_executor()`` call after that transparently creates a fresh
executor. This is important for test isolation — integration tests that
drive ``main()`` may shut the executor down as part of the app's
``finally`` block, after which unit tests still need a working pool.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

_input_executor: ThreadPoolExecutor | None = None


def get_input_executor() -> ThreadPoolExecutor:
    """Return the single shared input executor, creating it on first use
    and replacing it after a previous shutdown."""
    global _input_executor
    if _input_executor is None or _input_executor._shutdown:  # type: ignore[attr-defined]
        _input_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agentvoca-input")
    return _input_executor


def shutdown_input_executor() -> None:
    """Best-effort shutdown; wait=False so a stuck typewrite can't hang exit.

    A subsequent call to ``get_input_executor()`` will lazily create a
    fresh executor, so the next test (or, in practice, never — the
    process is exiting) gets a working pool.
    """
    global _input_executor
    if _input_executor is not None:
        _input_executor.shutdown(wait=False, cancel_futures=True)
        _input_executor = None
