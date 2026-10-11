"""PGS (Blu-ray subtitle) streams: palette, picture coding, display sets."""

import struct
import unittest

from collections import namedtuple

from bdmvkit import hdmv, pgs

Cue = namedtuple("Cue", "start end lines")


def frame(W, H, pixels):
    """RGBA frame with {(x, y): (grey, alpha)}."""
    px = bytearray(W * H * 4)
    for (x, y), (g, a) in pixels.items():
        px[4 * (y * W + x):4 * (y * W + x) + 4] = bytes([g, g, g, a])
    return bytes(px)


class TestPgs(unittest.TestCase):
    def test_bt709_colours(self):
        self.assertEqual(pgs.ycbcr((255, 255, 255)), (235, 128, 128))
        self.assertEqual(pgs.ycbcr((0, 0, 0)), (16, 128, 128))
        self.assertEqual(pgs.ycbcr((255, 0, 0)), (63, 102, 240))

    def test_palette_runs_from_outline_to_fill(self):
        pal = pgs.palette("#FFFF00", "#000080")
        self.assertEqual(len(pal), 65)
        self.assertEqual(pal[0][4], 0)                       # transparent
        y, cb, cr = pgs.ycbcr((255, 255, 0))
        self.assertEqual(pal[64], (64, y, cr, cb, 255))      # fill, opaque
        y, cb, cr = pgs.ycbcr((0, 0, 128))
        self.assertEqual(pal[8], (8, y, cr, cb, 255))        # outline, opaque
        self.assertEqual([e[4] for e in pal[1:9]], [32, 64, 96, 128, 159, 191, 223, 255])

    def test_indexed_crops_and_grades(self):
        W, H = 10, 4
        idx, w, h, x, y = pgs.indexed(frame(W, H, {(2, 1): (255, 255), (3, 1): (0, 255),
                                                  (4, 1): (128, 255), (5, 2): (0, 100),
                                                  (7, 3): (255, 10)}), W, H)
        self.assertEqual((w, h, x, y), (4, 2, 2, 1))         # alpha 10 is not visible
        self.assertEqual(list(idx), [64, 8, 40, 0, 0, 0, 0, 4])
        self.assertIsNone(pgs.indexed(bytes(W * H * 4), W, H))

    def test_run_length_round_trip(self):
        w, h = 300, 3
        idx = bytes([0] * 100 + [5] * 2 + [7] * 3 + [9] * 195 +      # short and long runs
                    [1] * 300 +
                    [0] * 64 + [2] + [0] * 235)
        data = pgs.rle(idx, w, h)
        self.assertEqual(data[:2], b"\x00\x40")               # 100 transparent: long form
        self.assertEqual(pgs.unrle(data, w, h), idx)

    def test_display_sets(self):
        W, H = 1920, 1080
        pic = pgs.indexed(frame(W, H, {(900, 1000): (255, 255), (901, 1000): (0, 255)}), W, H)
        pal = pgs.palette("#FFFFFF", "#000000")
        data = pgs.clear_set(0, (W, H), 0, None) + pgs.display_set(45000, (W, H), 1, pic, pal) + \
            pgs.clear_set(90000, (W, H), 2, (900, 1000, 2, 1))
        sets = pgs.decode(data)
        self.assertEqual([(t, len(p)) for t, p, _ in sets], [(0, 0), (45000, 1), (90000, 0)])
        self.assertEqual(sets[1][1][0], (900, 1000, 2, 1, bytes([64, 8])))
        # every segment: "PG", PTS, DTS 0, type, size
        self.assertEqual(data[:2], b"PG")
        pcs = data[13:13 + struct.unpack(">H", data[11:13])[0]]
        self.assertEqual(struct.unpack(">HHB", pcs[:5]), (W, H, 0x10))

    def test_big_objects_are_split(self):
        W, H = 1920, 200
        import random
        rnd = random.Random(1)
        px = {(x, y): (rnd.choice((0, 255)), 255) for y in range(H) for x in range(0, W, 2)}
        pic = pgs.indexed(frame(W, H, px), W, H)
        data = pgs.display_set(0, (1920, 1080), 1, pic, pgs.palette("#FFFFFF", "#000000"))
        sizes, pos, ods = [], 0, []
        while pos < len(data):
            kind, size = data[pos + 10], struct.unpack(">H", data[pos + 11:pos + 13])[0]
            if kind == pgs.ODS:
                ods.append(data[pos + 13 + 3])
            pos += 13 + size
        self.assertGreater(len(ods), 1)
        self.assertEqual(ods[0] & 0x80, 0x80)                 # first in sequence
        self.assertEqual(ods[-1] & 0x40, 0x40)                # last in sequence
        self.assertEqual(pgs.decode(data)[0][1][0][4], pic[0])

    def test_gap_before_the_next_cue(self):
        cues = [Cue(1.0, 3.0, ["a"]), Cue(3.0, 4.0, ["b"]), Cue(4.05, 4.1, ["c"]),
                Cue(4.1, 6.0, ["d"])]
        self.assertEqual(pgs.timeline(cues), [(1.0, 2.8), (3.0, 3.85), None, (4.1, 6.0)])

    def test_default_subtitles_command(self):
        # Set Stream with immediate operands: PG stream 2 valid and shown
        self.assertEqual(hdmv.set_subtitles(2),
                         bytes([0x51, 0xC0, 0, 0x01, 0, 0, 0xC0, 0x02, 0, 0, 0, 0]))
        self.assertEqual(hdmv.set_subtitles(0)[4:8], bytes(4))   # none shown


if __name__ == "__main__":
    unittest.main()
