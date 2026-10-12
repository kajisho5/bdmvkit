"""Discs written by bdmvkit, read back and played by libbluray (the library
VLC, mpv and Kodi play Blu-ray with): the titles, their lengths, chapters
and streams, and first play running through the titles in order."""

import os
import shutil
import subprocess
import tempfile
import unittest

from bdmvkit import BdmvError, Disc, pgs
from bdmvkit.encode import AudioTrack, encode_clip
from bdmvkit.formats import AUDIO_PID, CODING_AC3, CODING_LPCM, CODING_PG
from bdmvkit.m2ts import stream_pids

try:
    from . import bluray_sim
    LIBBLURAY = bluray_sim.load_library()
except Exception:  # pragma: no cover
    LIBBLURAY = None


def x264():
    if not shutil.which("ffmpeg"):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True,
                         text=True).stdout
    return "libx264" in out


ENCODE_OK = x264() and shutil.which("ffprobe")


def source(path, seconds, tone=True):
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
           f"testsrc2=size=640x360:rate=24000/1001:duration={seconds}"]
    if tone:
        cmd += ["-f", "lavfi", "-i", f"sine=d={seconds}:r=48000", "-shortest"]
    subprocess.run(cmd + [path], check=True)
    return path


def subtitle_sup(path, start, end):
    """A PGS stream with one subtitle: a white box with a black edge."""
    W, H = 1920, 1080
    rgba = bytearray(W * H * 4)
    for y in range(900, 960):
        for x in range(800, 1120):
            edge = y in (900, 959) or x in (800, 1119)
            rgba[4 * (y * W + x):4 * (y * W + x) + 4] = bytes([0, 0, 0, 255] if edge
                                                              else [255, 255, 255, 255])
    pic = pgs.indexed(bytes(rgba), W, H)
    return pgs.write_sup(path, [(start, end, pic, pgs.palette("#FFFFFF", "#000000"))], (W, H))


@unittest.skipUnless(ENCODE_OK, "needs ffmpeg with libx264")
class TestDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="bdmvkit-")
        a = encode_clip(source(os.path.join(cls.tmp, "a.mp4"), 4), os.path.join(cls.tmp, "a.m2ts"),
                        chapters=[0, 1, 2], fast=True,
                        sups=[subtitle_sup(os.path.join(cls.tmp, "a.sup"), 1.0, 2.0)])
        b = encode_clip(source(os.path.join(cls.tmp, "b.mp4"), 2, tone=False),
                        os.path.join(cls.tmp, "b.m2ts"), fps=(25, 1), fast=True)
        disc = Disc()
        disc.add_title(a, chapters=[0, 1, 2], audio=[("ac3", 2, "en")], subtitles=["ja"])
        disc.add_title(b, fps=(25, 1))
        cls.out = os.path.join(cls.tmp, "disc")
        cls.result = disc.write(cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_files(self):
        self.assertEqual(self.result["chapters"], [3, 1])
        for rel in ("BDMV/index.bdmv", "BDMV/MovieObject.bdmv", "BDMV/PLAYLIST/00001.mpls",
                    "BDMV/CLIPINF/00002.clpi", "BDMV/STREAM/00002.m2ts",
                    "BDMV/BACKUP/index.bdmv", "BDMV/BACKUP/PLAYLIST/00002.mpls"):
            self.assertTrue(os.path.isfile(os.path.join(self.out, rel)), rel)

    @unittest.skipUnless(LIBBLURAY, "needs libbluray")
    def test_read_by_libbluray(self):
        with bluray_sim.Disc(LIBBLURAY, self.out) as d:
            info = d.info()
            self.assertTrue(info["bluray"])
            self.assertTrue(info["first_play"])
            self.assertEqual(info["hdmv_titles"], 2)
            a, b = d.playlist(1), d.playlist(2)
        self.assertAlmostEqual(a["duration"], 4, delta=0.2)
        self.assertEqual(len(a["chapters"]), 3)
        for got, want in zip(a["chapters"], (0, 1, 2)):
            self.assertAlmostEqual(got, want, delta=0.1)
        self.assertEqual(a["video"], [(0x1B, 6, 1)])           # H.264, 1080p, 23.976
        self.assertEqual(a["audio"], [(CODING_AC3, 3, "eng")])
        self.assertEqual(a["pg"], [(CODING_PG, "jpn")])
        self.assertEqual(b["video"], [(0x1B, 4, 3)])           # 1080i 25
        self.assertAlmostEqual(b["duration"], 2, delta=0.2)

    @unittest.skipUnless(LIBBLURAY, "needs libbluray")
    def test_first_play_runs_the_titles(self):
        with bluray_sim.Disc(LIBBLURAY, self.out) as d:
            events = d.play()
        self.assertNotIn("error", [e[0] for e in events])
        # (title 0xFFFF: libbluray reporting the first-play object itself)
        self.assertEqual([v for k, v in events if k == "title" and v != 0xFFFF], [1, 2])
        self.assertEqual([v for k, v in events if k == "playlist"], [1, 2])
        self.assertEqual([v for k, v in events if k == "chapter"], [1, 2, 3, 1])

    def test_one_title_on_its_own(self):
        out = os.path.join(self.tmp, "single")
        disc = Disc()
        disc.add_title(os.path.join(self.out, "BDMV", "STREAM", "00002.m2ts"), fps=(25, 1))
        self.assertEqual(disc.write(out, play_all=False)["titles"], 1)


@unittest.skipUnless(ENCODE_OK, "needs ffmpeg with libx264")
class TestAudioTracks(unittest.TestCase):
    """Several sound tracks: from the video, from other files, silence."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = d = tempfile.mkdtemp(prefix="bdmvkit-audio-")
        video = source(os.path.join(d, "v.mp4"), 3)
        other = os.path.join(d, "other.wav")      # shorter than the picture
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=660:d=1.5:r=48000", other], check=True)
        quiet = source(os.path.join(d, "quiet.mp4"), 3, tone=False)
        cls.clip = encode_clip(video, os.path.join(d, "v.m2ts"), fast=True, audio=[
            AudioTrack(), AudioTrack(other, "lpcm"), AudioTrack(quiet, "ac3", 6)])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def probe(self, path):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "stream=id,codec_name,channels,duration", "-of", "json", path],
                             capture_output=True, text=True, check=True).stdout
        return {int(s["id"], 16): s for s in __import__("json").loads(out)["streams"]}

    def test_each_track_with_its_pid(self):
        pids = stream_pids(self.clip)
        self.assertEqual([pid for pid in pids if pid >= AUDIO_PID], [AUDIO_PID + k for k in range(3)])
        streams = self.probe(self.clip)
        self.assertEqual([(streams[AUDIO_PID + k]["codec_name"], streams[AUDIO_PID + k]["channels"])
                          for k in range(3)],
                         [("ac3", 2), ("pcm_bluray", 2), ("ac3", 6)])

    def test_tracks_last_as_long_as_the_picture(self):
        # (the 1.5 s sound is made up with silence; the clip still ends with the picture)
        streams = self.probe(self.clip)
        video = float(streams[0x1011]["duration"])
        self.assertAlmostEqual(video, 3, delta=0.1)
        for k in range(3):
            self.assertAlmostEqual(float(streams[AUDIO_PID + k]["duration"]), video, delta=0.15)

    @unittest.skipUnless(LIBBLURAY, "needs libbluray")
    def test_declared_and_read_back(self):
        out = os.path.join(self.tmp, "disc")
        disc = Disc()
        disc.add_title(self.clip, audio=[("ac3", 2, "en"), ("lpcm", 2, "ja"), ("ac3", 6, "fr")])
        disc.write(out)
        with bluray_sim.Disc(LIBBLURAY, out) as d:
            a = d.playlist(1)
        self.assertEqual(a["audio"], [(CODING_AC3, 3, "eng"), (CODING_LPCM, 3, "jpn"),
                                      (CODING_AC3, 6, "fre")])

    def test_a_track_the_clip_lacks_is_refused(self):
        disc = Disc()
        disc.add_title(self.clip, audio=[("ac3", 2, "en")] * 4)
        with self.assertRaises(BdmvError) as cm:
            disc.write(os.path.join(self.tmp, "bad"))
        self.assertIn("audio track 4", str(cm.exception))
        disc = Disc()
        disc.add_title(self.clip, subtitles=["en"])
        with self.assertRaises(BdmvError) as cm:
            disc.write(os.path.join(self.tmp, "bad2"))
        self.assertIn("subtitle track 1", str(cm.exception))


class TestChecks(unittest.TestCase):
    def test_refused(self):
        d = Disc()
        with self.assertRaises(BdmvError):
            d.add_title("x.m2ts", fps=(30, 1))
        with self.assertRaises(BdmvError):
            d.add_title("x.m2ts", audio=[("mp3", 2, "en")])
        with self.assertRaises(BdmvError):
            Disc().write(tempfile.gettempdir())


@unittest.skipUnless(ENCODE_OK, "needs ffmpeg with libx264")
class TestCli(unittest.TestCase):
    def test_encode_and_build(self):
        import io
        import json
        from contextlib import redirect_stderr, redirect_stdout

        from bdmvkit.__main__ import main
        tmp = tempfile.mkdtemp(prefix="bdmvkit-cli-")
        self.addCleanup(shutil.rmtree, tmp, True)
        src = source(os.path.join(tmp, "s.mp4"), 3)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["encode", src, os.path.join(tmp, "s.m2ts"),
                                   "--chapters", "0,1.5", "--fast"]), 0)
        with open(os.path.join(tmp, "disc.json"), "w") as f:
            json.dump({"titles": [{"clip": "s.m2ts", "chapters": [0, 1.5],
                                   "audio": [["ac3", 2, "fr"]]}]}, f)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["build", os.path.join(tmp, "disc.json"),
                                   os.path.join(tmp, "out")]), 0)
        self.assertIn("chapters [2]", out.getvalue())
