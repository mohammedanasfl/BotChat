"""Python <-> JavaScript conversion for binding calls (no-ops under plain CPython tests)."""

from __future__ import annotations

from typing import Any


def to_python(value: Any) -> Any:
    """Convert a JS proxy returned by a binding into plain Python."""
    return value.to_py() if hasattr(value, "to_py") else value


def to_js(value: Any) -> Any:
    """Convert Python dicts/lists into JS objects/arrays for binding calls."""
    try:
        from js import Object
        from pyodide.ffi import to_js as _to_js
    except ImportError:
        return value
    return _to_js(value, dict_converter=Object.fromEntries)
