"""Tests for R11: a single shared executor serializes pyautogui/pyperclip.

Concurrent ``insert()`` + ``undo_last()`` on the keyboard strategy must
not interleave their pyautogui calls. Keyboard and clipboard strategies
must both resolve to the same executor object.
"""

import asyncio
import time

import agentvoca.insertion.clipboard as clipboard_mod
import agentvoca.insertion.keyboard as keyboard_mod
from agentvoca.config.schema import InsertionConfig
from agentvoca.insertion._executor import get_input_executor
from agentvoca.insertion.keyboard import KeyboardInsertionStrategy


def test_keyboard_and_clipboard_share_executor():
    """Both strategies route through the same single-worker executor."""
    # Both call sites must resolve to the same executor object instance.
    assert keyboard_mod.get_input_executor() is clipboard_mod.get_input_executor()
    # And the factory is the same one the module exposes.
    assert keyboard_mod.get_input_executor is get_input_executor
    assert clipboard_mod.get_input_executor is get_input_executor


def test_concurrent_insert_and_undo_do_not_interleave(monkeypatch):
    """Stubs that record start/end timestamps: the two calls' intervals
    must not overlap (proving serialization through one executor)."""
    intervals: list[tuple[str, float, float]] = []

    def make_stub(name: str, sleep_s: float):
        def stub(*args, **kwargs):
            start = time.perf_counter()
            time.sleep(sleep_s)
            end = time.perf_counter()
            intervals.append((name, start, end))
        return stub

    fake_pyautogui = type(
        "P",
        (),
        {
            "typewrite": make_stub("typewrite", 0.10),
            "press": make_stub("press", 0.10),
            "hotkey": make_stub("hotkey", 0.10),
            "FAILSAFE": False,
        },
    )
    monkeypatch.setattr(keyboard_mod, "pyautogui", fake_pyautogui)
    monkeypatch.setattr(keyboard_mod, "get_foreground_hwnd", lambda: 0)
    monkeypatch.setattr(keyboard_mod, "is_windows", lambda: False)
    monkeypatch.setattr(keyboard_mod, "is_macos", lambda: False)
    # also patch the platform.win focus_window referenced from keyboard
    monkeypatch.setattr(keyboard_mod, "focus_window", lambda hwnd: None)

    config = InsertionConfig(strategy="keyboard")
    strat = KeyboardInsertionStrategy(config)

    async def run():
        # Fire insert() and undo_last() concurrently. They each make one
        # 100 ms pyautogui call. If the executor were shared but
        # multi-worker, intervals could overlap; with max_workers=1 they
        # must be sequential.
        await asyncio.gather(
            strat.insert("abc"),
            strat.undo_last(),
        )

    asyncio.run(run())

    # We may have 1 (insert) + 1 (undo press) or 2 (insert + undo hotkey)
    # pyautogui calls depending on the path — at least 2.
    assert len(intervals) >= 2, f"expected >= 2 pyautogui calls, got {intervals}"

    # Sort by start to recover the serial order.
    intervals_sorted = sorted(intervals, key=lambda x: x[1])
    for prev, curr in zip(intervals_sorted, intervals_sorted[1:]):
        assert prev[2] <= curr[1], (
            f"intervals overlap: {prev} vs {curr} (executor is not serializing)"
        )
