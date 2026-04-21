"""
Load ``reng/lib/render.py`` in isolation so ``npm test`` does not require ``httpx``.

Full package imports go through ``reng/__init__.py`` → engine → providers → httpx.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_render_module() -> ModuleType:
    """Execute ``render.py`` as a standalone module (stdlib only)."""
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "reng" / "lib" / "render.py"
    spec = importlib.util.spec_from_file_location("reng_lib_render_standalone", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
