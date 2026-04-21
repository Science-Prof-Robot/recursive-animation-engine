"""Unit tests for Hyperframes CLI resolution (no real render)."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from support_load_render import load_render_module

_render = load_render_module()
RenderError = _render.RenderError
resolve_hyperframes_invocation = _render.resolve_hyperframes_invocation


class TestResolveHyperframesInvocation(unittest.TestCase):
    def test_js_path_uses_node_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cli = root / "cli.js"
            cli.write_text("// placeholder", encoding="utf-8")
            proj = root / "my_project"
            proj.mkdir()

            argv, expected = resolve_hyperframes_invocation(proj, cli_override=str(cli))

            self.assertEqual(argv[:3], ["node", str(cli), "render"])
            self.assertEqual(argv[3], str(proj.resolve()))
            self.assertEqual(expected, proj.resolve() / "out.mp4")

    def test_non_js_executable_adds_output_flag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root / "fake-hyperframes"
            exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            os.chmod(exe, stat.S_IRWXU)
            proj = root / "my_project"
            proj.mkdir()

            argv, expected = resolve_hyperframes_invocation(proj, cli_override=str(exe))

            self.assertEqual(argv[0], str(exe))
            self.assertEqual(
                argv,
                [
                    str(exe),
                    "render",
                    "-o",
                    str(proj.resolve() / "out.mp4"),
                    str(proj.resolve()),
                ],
            )
            self.assertEqual(expected, proj.resolve() / "out.mp4")

    def test_missing_override_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            missing = Path(td) / "nope.js"

            with self.assertRaises(RenderError):
                resolve_hyperframes_invocation(proj, cli_override=str(missing))

    def test_bundled_bin_when_present(self) -> None:
        """When repo has node_modules/.bin/hyperframes, argv uses -o out.mp4."""
        bundled = _render._bundled_hyperframes_bin()
        if bundled is None:
            self.skipTest("run `npm install` at repo root to test bundled resolution")

        saved = os.environ.pop("HYPERFRAMES_CLI", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                proj = Path(td) / "composition"
                proj.mkdir()
                argv, expected = resolve_hyperframes_invocation(proj, cli_override=None)
                self.assertEqual(argv[0], str(bundled))
                self.assertIn("-o", argv)
                self.assertEqual(expected, proj.resolve() / "out.mp4")
        finally:
            if saved is not None:
                os.environ["HYPERFRAMES_CLI"] = saved
