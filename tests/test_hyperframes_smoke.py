"""Smoke tests against installed Hyperframes CLI (skipped if npm deps missing)."""

from __future__ import annotations

import subprocess
import unittest

from support_load_render import load_render_module

_render = load_render_module()


class TestHyperframesSmoke(unittest.TestCase):
    def test_hyperframes_version(self) -> None:
        hf = _render._bundled_hyperframes_bin()
        if hf is None:
            self.skipTest("node_modules/.bin/hyperframes missing — run `npm install` at repo root")

        proc = subprocess.run(
            [str(hf), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
