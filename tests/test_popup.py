"""Pop-up menus: buttons over a playing title, muxed into its clip as an IG
stream, opened with the remote's Pop-up Menu key and played by libbluray."""

import os
import shutil
import tempfile
import unittest

from bdmvkit import BdmvError, Disc, MenuButton, hdmv
from bdmvkit.encode import encode_clip
from bdmvkit.formats import CODING_IG, IG_PID
from bdmvkit.m2ts import stream_pids

from .test_disc import ENCODE_OK, source
from .test_menus import png

try:
    from . import bluray_sim
    LIBBLURAY = bluray_sim.load_library()
except Exception:  # pragma: no cover
    LIBBLURAY = None


@unittest.skipUnless(ENCODE_OK and LIBBLURAY, "needs ffmpeg with libx264, and libbluray")
class TestPopup(unittest.TestCase):
    """Title 1 has a pop-up menu: TWO (title 2) and SCENE (its own chapter 2)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = d = tempfile.mkdtemp(prefix="bdmvkit-popup-")
        a = encode_clip(source(os.path.join(d, "a.mp4"), 8), os.path.join(d, "a.m2ts"),
                        chapters=[0, 4], fast=True)
        b = encode_clip(source(os.path.join(d, "b.mp4"), 2), os.path.join(d, "b.m2ts"),
                        fast=True)
        lit = png(os.path.join(d, "lit.png"), 300, 60, "orange")
        off = png(os.path.join(d, "off.png"), 300, 60, "gray")
        disc = Disc()
        cls.a = a
        disc.add_title(a, chapters=[0, 4], end="stop")
        disc.add_title(b, end="stop")
        disc.add_popup(1, [MenuButton("two", 160, 900, lit, normal=off, action="title:2"),
                           MenuButton("scene", 760, 900, lit, normal=off,
                                      action="chapter:1:2"),
                           MenuButton("sub", 1360, 900, lit, normal=off, action="subtitle:off")])
        cls.out = os.path.join(d, "disc")
        disc.write(cls.out, play_all=False, fast=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_in_the_clip(self):
        clip = os.path.join(self.out, "BDMV", "STREAM", "00001.m2ts")
        self.assertEqual(stream_pids(clip).get(IG_PID), CODING_IG)
        # (the clip given is left as it was)
        self.assertNotIn(IG_PID, stream_pids(self.a))
        # the second title has none
        self.assertNotIn(IG_PID, stream_pids(os.path.join(self.out, "BDMV", "STREAM",
                                                          "00002.m2ts")))

    def test_opens_and_its_buttons_work(self):
        with bluray_sim.Disc(LIBBLURAY, self.out) as disc:
            disc.info()
            ev = [e for e in disc.play(keys=("live:popup", "live:enter"))
                  if e[0] in ("title", "key", "menu") and e[1] != 0xFFFF]
        keys = [e for e in ev if e[0] in ("title", "key")]
        # title 1, the pop-up opened over it, TWO chosen: title 2
        self.assertEqual(keys[:4], [("title", 1), ("key", "live:popup"), ("key", "live:enter"),
                                    ("title", 2)])
        drawn = [d for e in ev if e[0] == "menu" for d in e[1]]
        xs = sorted({d[1] for d in drawn if d[0] == "draw"})
        self.assertTrue({160, 760, 1360} <= set(xs), drawn)

    def test_a_chapter_from_the_popup(self):
        with bluray_sim.Disc(LIBBLURAY, self.out) as disc:
            disc.info()
            ev = disc.play(keys=("live:popup", "live:right", "live:enter"))
        after = ev[next(i for i, e in enumerate(ev) if e == ("key", "live:enter")):]
        self.assertIn(("at_chapter", 2), after)

    def test_a_stream_button_closes_the_menu(self):
        disc = Disc()
        disc.add_title("x.m2ts")
        p = disc.program()
        from bdmvkit.disc import _ig_buttons
        from bdmvkit.nav import Navigation
        lit = os.path.join(self.tmp, "lit.png")
        nav = Navigation(p)
        sub = MenuButton("sub", 100, 100, lit, action="subtitle:off")
        two = MenuButton("one", 100, 300, lit, action="title:1")
        from bdmvkit.disc import _button
        ig = _ig_buttons("t", [sub, two], [_button(sub), _button(two)], nav, popup=True)
        self.assertEqual(ig[0].commands[-1], hdmv.popup_off())
        self.assertNotIn(hdmv.popup_off(), ig[1].commands)


class TestChecks(unittest.TestCase):
    def test_refused(self):
        disc = Disc()
        with self.assertRaises(BdmvError):
            disc.add_popup(1, [MenuButton("a", 0, 0, "a.png", action="title:1")])
        disc.add_title("x.m2ts")
        with self.assertRaises(BdmvError):
            disc.add_popup(1, [])
        disc.add_popup(1, [MenuButton("a", 0, 0, "a.png", action="title:9")])
        with self.assertRaises(BdmvError):               # leads nowhere
            disc.program().check()
