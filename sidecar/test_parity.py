#!/usr/bin/env python3
"""Unit tests for NC Tower sidecar parity helpers (no Docker required)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sidecar"))

from chassis_fan import PROFILE_CURVES, validate_curve  # noqa: E402
from parity import (  # noqa: E402
    apply_recreate_overrides,
    backup_path_contained,
    parse_wg_dump,
    redact_wg_key,
    validate_container_name,
)


class CurveTests(unittest.TestCase):
    def test_valid_curve(self):
        points, err = validate_curve([[30, 10], [40, 20], [50, 30], [60, 40], [70, 50]])
        self.assertIsNone(err)
        self.assertEqual(len(points), 5)

    def test_non_monotonic(self):
        _, err = validate_curve([[30, 10], [25, 20], [50, 30], [60, 40], [70, 50]])
        self.assertEqual(err, "temps_must_be_monotonic")

    def test_wrong_count(self):
        _, err = validate_curve([[30, 10]])
        self.assertEqual(err, "curve_requires_5_points")

    def test_profiles_exist(self):
        self.assertIn("silent", PROFILE_CURVES)
        self.assertIn("balanced", PROFILE_CURVES)
        self.assertIn("performance", PROFILE_CURVES)


class RenameTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_container_name("gcs_sitl"))
        self.assertTrue(validate_container_name("a.b-c_1"))

    def test_invalid(self):
        self.assertFalse(validate_container_name(""))
        self.assertFalse(validate_container_name("../etc"))
        self.assertFalse(validate_container_name("has space"))


class OverrideTests(unittest.TestCase):
    def test_env_merge(self):
        args = ["docker", "run", "-d", "--name", "x", "-e", "FOO=1", "-e", "KEEP=yes", "img"]
        out, err = apply_recreate_overrides(args, {"env_set": ["BAR=2"], "env_unset": ["FOO"]})
        self.assertIsNone(err)
        assert out is not None
        env_pairs = [out[i + 1] for i, t in enumerate(out) if t == "-e"]
        self.assertIn("BAR=2", env_pairs)
        self.assertIn("KEEP=yes", env_pairs)
        self.assertTrue(all(not p.startswith("FOO=") for p in env_pairs))

    def test_memory(self):
        args = ["docker", "run", "-d", "--name", "x", "img"]
        out, err = apply_recreate_overrides(args, {"memory": "512m"})
        self.assertIsNone(err)
        assert out is not None
        self.assertIn("--memory", out)
        self.assertIn("512m", out)


class BackupPathTests(unittest.TestCase):
    def test_containment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.tar").write_text("x", encoding="utf-8")
            self.assertIsNotNone(backup_path_contained(root, "ok.tar"))
            self.assertIsNone(backup_path_contained(root, "../ok.tar"))
            self.assertIsNone(backup_path_contained(root, "missing.tar"))


class WgTests(unittest.TestCase):
    def test_redact(self):
        self.assertTrue(redact_wg_key("abcdefghijklmnopqrstuvwxyz012345").endswith("yz012345"))
        self.assertEqual(redact_wg_key("short"), "********")

    def test_parse_dump(self):
        text = "wg0\tpubkeyiface\t\toff\t\t0\t0\nABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcd\t(none)\t1.2.3.4:51820\t10.0.0.2/32\t1710000000\t100\t200\t\n"
        peers = parse_wg_dump(text)
        self.assertTrue(any(p.get("endpoint") for p in peers))


if __name__ == "__main__":
    unittest.main()
