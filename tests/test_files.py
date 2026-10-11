"""The navigation files and commands, byte by byte where the format fixes
them."""

import struct
import unittest

from bdmvkit import hdmv, playlist
from bdmvkit.clip import clpi, ep_map
from bdmvkit.m2ts import ClipScan


class TestCommands(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(hdmv.play_pl(3), bytes([0x22, 0x80, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0]))
        self.assertEqual(hdmv.jump_title(2)[:2], bytes([0x21, 0x81]))
        self.assertEqual(hdmv.jump_title(2)[4:8], struct.pack(">I", 2))
        self.assertEqual(hdmv.play_pl_mark(1, 4)[8:], struct.pack(">I", 4))
        self.assertEqual(len(hdmv.set_streams(audio=2, subtitle=0)), 12)

    def test_movie_objects_and_index(self):
        mo = hdmv.movie_objects([[hdmv.play_pl(0)], [hdmv.jump_title(1)]])
        self.assertEqual(mo[:8], b"MOBJ0200")
        n_objects = struct.unpack_from(">H", mo, 40 + 4 + 4)[0]
        self.assertEqual(n_objects, 2)
        ix = hdmv.index_bdmv([0, 1], 2, 2, 6, 1)
        self.assertEqual(ix[:8], b"INDX0200")
        # the AppInfo: video format 6 (1080p), frame rate 1 (23.976)
        self.assertEqual(ix[40 + 4 + 1], 6 << 4 | 1)


class TestPlaylistAndClip(unittest.TestCase):
    SCAN = ClipScan(packets=1000, first_pts=90000, end_pts=90000 + 3 * 90000, pcr_pid=0x1011,
                    entries=[(90000, 0, 50000), (90000 + 90000, 400, 60000)])

    def test_mpls(self):
        item = ("00001", 45000, 45000 * 4, 6, 1, [(0x81, 2, "eng")], ["jpn"], False, 0)
        data = playlist.mpls([item], [(0, 45000), (0, 90000)])
        self.assertEqual(data[:8], b"MPLS0200")
        list_pos, mark_pos = struct.unpack_from(">II", data, 8)
        self.assertEqual(struct.unpack_from(">H", data, list_pos + 6)[0], 1)    # one item
        self.assertIn(b"00001M2TS", data)
        self.assertEqual(struct.unpack_from(">H", data, mark_pos + 4)[0], 2)    # two marks
        self.assertIn(b"eng", data)
        self.assertIn(b"jpn", data)

    def test_clpi(self):
        data = clpi(self.SCAN, 6, 1, [(0x81, 2, "eng")])
        self.assertEqual(data[:8], b"HDMV0200")
        self.assertIn(b"HDMV", data[8:])
        self.assertEqual(len(data) % 4, 0)

    def test_ep_map_coarse_and_fine(self):
        m = ep_map(self.SCAN.entries)
        counts = int.from_bytes(m[4:10], "big")
        self.assertEqual(counts >> 34 & 0xF, 1)            # EP_stream_type: video
        self.assertEqual(counts & 0x3FFFF, 2)              # two fine entries (key frames)
