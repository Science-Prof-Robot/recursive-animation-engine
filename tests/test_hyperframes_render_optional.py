"""
Optional end-to-end render (slow; needs Chrome + ffmpeg).

Enable with: RUN_HYPERFRAMES_RENDER=1
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support_load_render import load_render_module

_render = load_render_module()
render = _render.render


@unittest.skipUnless(
    os.environ.get("RUN_HYPERFRAMES_RENDER") == "1",
    "set RUN_HYPERFRAMES_RENDER=1 to run full Hyperframes render",
)
class TestHyperframesRenderOptional(unittest.TestCase):
    def test_render_scaffolded_project(self) -> None:
        bundled = _render._bundled_hyperframes_bin()
        if bundled is None and not shutil.which("hyperframes"):
            self.skipTest("hyperframes CLI not found (run `npm install` at repo root)")
        hf_bin = str(bundled) if bundled else shutil.which("hyperframes")

        tmp = Path(tempfile.mkdtemp(prefix="reng-hf-"))
        try:
            subprocess.run(
                [hf_bin, "init", "demo"],
                cwd=tmp,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            project = tmp / "demo"
            self.assertTrue((project / "index.html").is_file())

            saved = os.environ.pop("HYPERFRAMES_CLI", None)
            try:
                out, elapsed = render(project, timeout=300.0)
            finally:
                if saved is not None:
                    os.environ["HYPERFRAMES_CLI"] = saved
            self.assertTrue(out.is_file(), f"expected mp4 at {out}")
            self.assertGreater(out.stat().st_size, 1000)
            self.assertGreater(elapsed, 0.0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
