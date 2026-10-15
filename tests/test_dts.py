"""DTS-HD sound tracks: a title declares DTS-HD High Resolution or Master
Audio (above 48 kHz too), the clip's PMT is marked so (ffmpeg marks DTS by
its channels), and libbluray reads the streams as declared."""

import os
import shutil
import subprocess
import tempfile
import unittest

from bdmvkit import BdmvError, Disc
from bdmvkit.encode import AudioTrack, encode_clip
from bdmvkit.formats import (AUDIO_PID, CODING_DTS, CODING_DTSHD, CODING_DTSHD_MA, PMT_PID,
                             rate_code)
from bdmvkit.igs import crc32
from bdmvkit.m2ts import set_stream_types, stream_pids

from .test_disc import ENCODE_OK, LIBBLURAY, bluray_sim, source


def pmts(path):
    """[(stream type of the first sound track, section CRC good)] of every
    PMT of a clip."""
    out = []
    with open(path, "rb") as f:
        while len(pkt := f.read(192)) == 192:
            if (pkt[5] & 0x1F) << 8 | pkt[6] != PMT_PID or not pkt[5] & 0x40:
                continue
            q = 8 + 1 + pkt[8]
            end = q + 3 + ((pkt[q + 1] & 0x0F) << 8 | pkt[q + 2])
            e = q + 12 + ((pkt[q + 10] & 0x0F) << 8 | pkt[q + 11])
            while (pkt[e + 1] & 0x1F) << 8 | pkt[e + 2] != AUDIO_PID:
                e += 5 + ((pkt[e + 3] & 0x0F) << 8 | pkt[e + 4])
            out.append((pkt[e], crc32(pkt[q:end]) == 0))
    return out


class TestRates(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(rate_code(CODING_DTS), 1)
        self.assertEqual(rate_code(CODING_DTSHD_MA, 96000), 14)      # (over a 48 kHz core)
        self.assertEqual(rate_code(CODING_DTSHD, 192000), 12)
        self.assertEqual(rate_code(0x80, 96000), 4)                  # LPCM
        for coding, rate in ((0x81, 96000), (CODING_DTS, 96000), (CODING_DTSHD_MA, 44100)):
            with self.assertRaises(BdmvError):
                rate_code(coding, rate)

    def test_add_title(self):
        d = Disc()
        d.add_title("a.m2ts", audio=[("dtshd_ma", 8, "en", 96000), ("dtshd", 6, "ja")])
        a = d.program().titles[0].audio
        self.assertEqual([(x.coding, x.rate) for x in a],
                         [(CODING_DTSHD_MA, 96000), (CODING_DTSHD, 48000)])
        with self.assertRaises(BdmvError):
            d.add_title("a.m2ts", audio=[("ac3", 2, "en", 96000)])
        with self.assertRaises(BdmvError):
            d.add_title("a.m2ts", audio=[("dts-hd", 6, "en")])


@unittest.skipUnless(ENCODE_OK, "needs ffmpeg with libx264")
class TestDtsHd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = d = tempfile.mkdtemp(prefix="bdmvkit-dts-")
        # a 5.1 DTS stream (ffmpeg's encoder writes the core alone; what
        # bdmvkit does is the same for a core with extensions)
        dts = os.path.join(d, "sound.dts")
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "sine=d=3:r=48000", "-ac", "6", "-c:a", "dca", "-strict", "-2", dts],
                       check=True)
        cls.clip = encode_clip(source(os.path.join(d, "v.mp4"), 3, tone=False),
                               os.path.join(d, "v.m2ts"), fast=True,
                               audio=[AudioTrack(dts, "copy", 6)])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def write(self, *audio):
        out = tempfile.mkdtemp(dir=self.tmp)
        disc = Disc()
        for a in audio:
            disc.add_title(self.clip, audio=[a])
        disc.write(out)
        return out

    def test_marked_as_declared(self):
        self.assertEqual(stream_pids(self.clip)[AUDIO_PID], CODING_DTS)   # (ffmpeg: 6 channels)
        out = self.disc()
        for name, want in (("00001", CODING_DTSHD_MA), ("00002", CODING_DTSHD),
                           ("00003", CODING_DTS)):
            got = pmts(os.path.join(out, "BDMV", "STREAM", f"{name}.m2ts"))
            self.assertGreater(len(got), 1)
            self.assertEqual(set(got), {(want, True)}, name)       # every PMT, CRC made again
        self.assertEqual(set(pmts(self.clip)), {(CODING_DTS, True)})   # (the source as it was)

    @unittest.skipUnless(LIBBLURAY, "needs libbluray")
    def test_read_by_libbluray(self):
        with bluray_sim.Disc(LIBBLURAY, self.disc()) as d:
            a, b, c = d.playlist(1), d.playlist(2), d.playlist(3)
        self.assertEqual(a["audio"], [(CODING_DTSHD_MA, 6, "eng")])
        self.assertEqual((b["audio"], b["audio_rate"]), ([(CODING_DTSHD, 6, "eng")], [14]))
        self.assertEqual((c["audio"], c["audio_rate"]), ([(CODING_DTS, 6, "eng")], [1]))

    def disc(self):
        """Three titles of the same clip: DTS-HD Master Audio, DTS-HD High
        Resolution at 96 kHz (over its 48 kHz core) and DTS."""
        return self.write(("dtshd_ma", 6, "en"), ("dtshd", 6, "en", 96000), ("dts", 6, "en"))

    def test_not_dts(self):
        with self.assertRaises(BdmvError) as e:
            self.write(("ac3", 6, "en"))
        self.assertIn("stream type 0x82", e.exception.message)

    def test_retyped_a_piece_at_a_time(self):
        copy = os.path.join(self.tmp, "copy.m2ts")
        shutil.copyfile(self.clip, copy)
        set_stream_types(copy, {AUDIO_PID: CODING_DTSHD_MA}, chunk=192 * 7)
        got = pmts(copy)
        self.assertEqual(set(got), {(CODING_DTSHD_MA, True)})
        self.assertEqual(len(got), len(pmts(self.clip)))
        with open(copy, "rb") as f, open(self.clip, "rb") as g:
            a, b = f.read(), g.read()
        self.assertEqual(len(a), len(b))
        diff = {i // 192 for i in range(len(a)) if a[i] != b[i]}
        self.assertEqual(len(diff), len(got))                         # (only the PMTs)


if __name__ == "__main__":
    unittest.main()
