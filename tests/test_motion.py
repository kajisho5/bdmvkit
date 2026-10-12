"""Menus with motion or music: a video as the background, a sound file as
the menu's sound, played again from a loop point; and a menu with music and
a loop count that goes on by itself. Played by libbluray."""

import os
import shutil
import subprocess
import tempfile
import unittest

from bdmvkit import Disc, MenuButton
from bdmvkit.encode import encode_clip, is_video, media_seconds
from bdmvkit.formats import AUDIO_PID, CODING_AC3, IG_PID
from bdmvkit.m2ts import stream_pids

from .test_disc import ENCODE_OK, source
from .test_menus import png

try:
    from . import bluray_sim
    LIBBLURAY = bluray_sim.load_library()
except Exception:  # pragma: no cover
    LIBBLURAY = None


def tone(path, seconds):
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=frequency=330:d={seconds}:r=48000", path], check=True)
    return path


@unittest.skipUnless(ENCODE_OK and LIBBLURAY, "needs ffmpeg with libx264, and libbluray")
class TestMotionMenus(unittest.TestCase):
    """Menu "moving": a 2 s video with 3 s of music, from 0.5 s the second time
    (the video decides its length). Menu "music": a picture with 1.5 s of
    music, played twice, then title 1."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = d = tempfile.mkdtemp(prefix="bdmvkit-motion-")
        a = encode_clip(source(os.path.join(d, "a.mp4"), 2), os.path.join(d, "a.m2ts"),
                        fast=True)
        cls.video = source(os.path.join(d, "bg.mp4"), 2, tone=False)
        cls.bg = png(os.path.join(d, "bg.png"), 1920, 1080, "navy")
        lit = png(os.path.join(d, "lit.png"), 300, 60, "orange")
        disc = Disc(first_play="menu:moving")
        disc.add_title(a, end="menu:music")
        disc.add_menu("moving", cls.video, [MenuButton("play", 160, 900, lit, action="title:1")],
                      music=tone(os.path.join(d, "m.wav"), 3), loop_point=0.5)
        disc.add_menu("music", cls.bg, [MenuButton("play", 160, 900, lit, action="title:1")],
                      music=tone(os.path.join(d, "m2.wav"), 1.5), loop=2, end="title:1")
        cls.out = os.path.join(d, "disc")
        disc.write(cls.out, play_all=False, fast=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def clip(self, n):
        return os.path.join(self.out, "BDMV", "STREAM", f"{n:05d}.m2ts")

    def test_pictures_and_videos_told_apart(self):
        self.assertTrue(is_video(self.video))
        self.assertFalse(is_video(self.bg))

    def test_clips_carry_the_music_and_the_buttons(self):
        for n in (2, 3):
            pids = stream_pids(self.clip(n))
            self.assertEqual(pids.get(AUDIO_PID), CODING_AC3)
            self.assertIn(IG_PID, pids)
        # the video decides the moving menu's length; the music the other's
        self.assertAlmostEqual(media_seconds(self.clip(2)), 2, delta=0.2)
        self.assertAlmostEqual(media_seconds(self.clip(3)), 1.5, delta=0.2)

    def test_read_back(self):
        with bluray_sim.Disc(LIBBLURAY, self.out) as disc:
            moving, music = disc.playlist(2), disc.playlist(3)
        self.assertEqual(moving["audio"], [(CODING_AC3, 3, "und")])
        # two marks: the start, and the loop point
        self.assertEqual(len(moving["chapters"]), 2)
        self.assertAlmostEqual(moving["chapters"][1], 0.5, delta=0.1)
        self.assertEqual(len(music["chapters"]), 1)

    def test_played_again_from_the_loop_point(self):
        with bluray_sim.Disc(LIBBLURAY, self.out) as disc:
            ev = disc.play(max_bytes=40 * 2**20)
        seen = [e for e in ev if e[0] in ("playlist", "at_chapter")]
        # the moving menu, then again and again from its loop point (mark 2)
        self.assertEqual(seen[:4], [("playlist", 2), ("at_chapter", 1),
                                    ("playlist", 2), ("at_chapter", 2)])

    def test_a_loop_count_goes_on_by_itself(self):
        disc = Disc(first_play="menu:music")
        disc.add_title(self.clip(1), end="stop")
        lit = os.path.join(self.tmp, "lit.png")
        disc.add_menu("music", self.bg, [MenuButton("play", 160, 900, lit, action="title:1")],
                      music=os.path.join(self.tmp, "m2.wav"), loop=2, end="title:1")
        out = os.path.join(self.tmp, "disc2")
        disc.write(out, play_all=False, fast=True)
        with bluray_sim.Disc(LIBBLURAY, out) as d:
            ev = d.play()
        plays = [v for k, v in ev if k == "playlist"]
        # the menu twice (playlist 2), then title 1
        self.assertEqual(plays[:3], [2, 2, 1])
