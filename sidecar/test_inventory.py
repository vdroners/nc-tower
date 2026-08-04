#!/usr/bin/env python3
"""Unit tests for NC Tower inventory parsers (no host privileges required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sidecar"))

from inventory import (  # noqa: E402
    decode_taint,
    parse_dmidecode_memory,
    parse_ethtool,
    parse_ethtool_i,
    parse_mdstat,
    parse_ss_tlnp,
    smart_history_summarize,
    tag_kernel_line,
)


DMIDECODE_MEM = """
# dmidecode 3.5
Memory Device
	Size: No Module Installed
	Locator: DIMM_A1

Memory Device
	Size: 32 GB
	Locator: DIMM_A2
	Type: DDR4
	Speed: 3200 MT/s
	Manufacturer: Samsung
	Part Number: M393A4K40DB3-CWE
	Configured Memory Speed: 3200 MT/s
	Error Correction Type: Multi-bit ECC
"""

MDSTAT = """Personalities : [raid1] [raid6] [raid5]
md0 : active raid1 sdb1[0] sdc1[1]
      976630464 blocks super 1.2 [2/2] [UU]

md1 : active raid5 sdd1[0] sde1[1] sdf1[2]
      1000000 blocks super 1.2 level 5, 512k chunk, algorithm 2 [3/2] [U_U]
unused devices: <none>
"""

SS_TLNP = """State  Recv-Q Send-Q Local Address:Port  Peer Address:Port Process
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=1,fd=3))
LISTEN 0      511        127.0.0.1:8080       0.0.0.0:*    users:(("apache2",pid=2,fd=4))
"""

ETHTOOL = """Settings for enp1s0:
	Speed: 1000Mb/s
	Duplex: Full
	Port: Twisted Pair
	Link detected: yes
"""

ETHTOOL_I = """driver: igb
version: 5.15.0
firmware-version: 1.63, 0x800009fa
bus-info: 0000:01:00.0
"""


class TaintTests(unittest.TestCase):
    def test_mce_bit(self):
        # bit 4 = MCE
        out = decode_taint(1 << 4)
        self.assertTrue(out["hardware_tainted"])
        self.assertIn("mce", out["flags"])

    def test_clean(self):
        out = decode_taint(0)
        self.assertFalse(out["hardware_tainted"])
        self.assertEqual(out["flags"], [])


class DmidecodeTests(unittest.TestCase):
    def test_skips_empty_slots(self):
        dimms = parse_dmidecode_memory(DMIDECODE_MEM)
        self.assertEqual(len(dimms), 1)
        self.assertEqual(dimms[0]["locator"], "DIMM_A2")
        self.assertEqual(dimms[0]["size"], "32 GB")
        self.assertEqual(dimms[0]["part_number"], "M393A4K40DB3-CWE")


class MdstatTests(unittest.TestCase):
    def test_degraded(self):
        raid = parse_mdstat(MDSTAT)
        self.assertTrue(raid["degraded"])
        self.assertEqual(len(raid["arrays"]), 2)
        self.assertEqual(raid["arrays"][0]["name"], "md0")

    def test_empty(self):
        raid = parse_mdstat("")
        self.assertFalse(raid["degraded"])
        self.assertEqual(raid["arrays"], [])


class SsTests(unittest.TestCase):
    def test_listeners(self):
        rows = parse_ss_tlnp(SS_TLNP)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["local"], "0.0.0.0:22")
        self.assertEqual(rows[0]["process"], "sshd")


class EthtoolTests(unittest.TestCase):
    def test_link(self):
        out = parse_ethtool(ETHTOOL)
        self.assertEqual(out["speed"], "1000Mb/s")
        self.assertEqual(out["duplex"], "Full")

    def test_driver(self):
        out = parse_ethtool_i(ETHTOOL_I)
        self.assertEqual(out["driver"], "igb")
        self.assertIn("1.63", out["firmware"])


class KernelTagTests(unittest.TestCase):
    def test_tags(self):
        self.assertIn("mce", tag_kernel_line("mce: Hardware Error"))
        self.assertIn("oom", tag_kernel_line("Out of memory: Killed process 123"))
        self.assertIn("disk_reset", tag_kernel_line("nvme0n1: reset controller"))


class SmartHistoryTests(unittest.TestCase):
    def test_summarize(self):
        samples = [
            {
                "ts": 1,
                "disks": [{"serial": "ABC", "device": "/dev/sda", "temp_c": 30, "reallocated": 0}],
            },
            {
                "ts": 2,
                "disks": [{"serial": "ABC", "device": "/dev/sda", "temp_c": 42, "reallocated": 1}],
            },
        ]
        rows = smart_history_summarize(samples)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["temp_min"], 30)
        self.assertEqual(rows[0]["temp_max"], 42)
        self.assertEqual(rows[0]["temp_now"], 42)
        self.assertEqual(rows[0]["reallocated"], 1)


if __name__ == "__main__":
    unittest.main()
