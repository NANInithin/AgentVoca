"""AgentVoca Observer subsystem (v0.4.0).

Background recording of what the user said, what was on screen, what was
highlighted, and what app was in front. The result is a markdown + JSON
sidecar compiled at the end of the session.

This package is the implementation seam. Three tracks (Foundation,
Capture, Compilation) own disjoint files inside it; see
``docs/proposals/v0.4.0-observer-mode.md`` for the split.
"""

from __future__ import annotations
