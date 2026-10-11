"""Menus: the IG stream of a menu's buttons (its bytes, the arrow keys, the
colours, what is refused), and a disc with a menu played by libbluray with
the remote's keys: the buttons start the titles, a chapter and another
menu, and the titles come back to the menu."""

import os
import shutil
import struct
import subprocess
import tempfile
import unittest

from bdmvkit import BdmvError, Disc, MenuButton, hdmv, igs
from bdmvkit.encode import encode_clip, picture

from .test_disc import ENCODE_OK, source

try:
    from . import bluray_sim
    LIBBLURAY = bluray_sim.load_library()
except Exception:  # pragma: no cover
    LIBBLURAY = None


def box(w, h, rgba):
    return bytes(rgba) * (w * h)


def button(bid, x, y, **kw):
    return igs.Button(bid, x, y, 100, 40, box(100, 40, (255, 200, 0, 255)), **kw)


def segments(data):
    """[(type, payload)] of a .sup stream."""
    out, i = [], 0
    while i < len(data):
        assert data[i:i + 2] == b"PG"
        kind, size = data[i + 10], struct.unpack(">H", data[i + 11:i + 13])[0]
        out.append((kind, data[i + 13:i + 13 + size]))
        i += 13 + size
    return out


class TestStream(unittest.TestCase):
    def test_segments(self):
        data = igs.ig_stream([button("a", 100, 100, commands=[hdmv.jump_title(1)]),
                              button("b", 100, 200)], frame_rate=1, default="b")
        kinds = [k for k, _ in segments(data)]
        # the composition, the palette, a selected and an activated object
        # per button (no normal pictures: none), the end
        self.assertEqual(kinds, [igs.ICS, igs.PDS] + [igs.ODS] * 4 + [igs.END])
        ics = segments(data)[0][1]
        self.assertEqual(struct.unpack(">HH", ics[:4]), (1920, 1080))
        self.assertEqual(ics[4] >> 4, 1)                          # frame rate code
        self.assertIn(hdmv.jump_title(1), ics)
        # the default button: b, number 1
        page = ics.index(bytes(8) + bytes(4)) + 12               # after the page's UO mask, effects
        self.assertEqual(struct.unpack(">H", ics[page + 1:page + 3])[0], 1)

    def test_auto_nav(self):
        nav = igs.auto_nav([button("a", 100, 100), button("b", 100, 300), button("c", 600, 300),
                            button("d", 100, 500, nav={"up": "c"})])
        self.assertEqual(nav["a"], {"up": "a", "down": "b", "left": "a", "right": "c"})
        self.assertEqual(nav["b"]["right"], "c")
        self.assertEqual(nav["c"]["left"], "b")
        self.assertEqual(nav["d"]["up"], "c")                     # as it says

    def test_quantize(self):
        red, half = (255, 0, 0, 255), (0, 0, 255, 128)
        palette, pics = igs.quantize([box(2, 2, red), box(2, 1, half) + bytes(8)])
        self.assertEqual(palette[0], red)
        self.assertEqual(pics[0], bytes([1]) * 4)
        self.assertEqual(pics[1], bytes([2, 2, 0, 0]))           # transparent: index 0
        # more than 255 colours: fewer bits per channel
        many = bytes(c for v in range(1000) for c in (v % 256, v // 4 % 256, 7, 255))
        palette, pics = igs.quantize([many])
        self.assertLessEqual(len(palette), 255)

    def test_refused(self):
        for buttons, why in (([], "at least one"),
                             ([button("a", 0, 0), button("a", 0, 100)], "unique"),
                             ([button("a", 1900, 0)], "inside"),
                             ([button("a", 0, 0, nav={"up": "x"})], "nav"),
                             ([igs.Button("a", 0, 0, 10, 10, bytes(10))], "RGBA")):
            with self.assertRaises(BdmvError) as cm:
                igs.ig_stream(buttons, 1)
            self.assertIn(why, cm.exception.args[0])
        with self.assertRaises(BdmvError):
            igs.ig_stream([button("a", 0, 0)], 1, default="z")


def png(path, w, h, colour):
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c={colour}:s={w}x{h}", "-frames:v", "1", path], check=True)
    return path


@unittest.skipUnless(ENCODE_OK and LIBBLURAY, "needs ffmpeg with libx264, and libbluray")
class TestDisc(unittest.TestCase):
    """Two titles and two menus: main (title 1, title 2, chapter 2 of title
    1, the scenes menu) and scenes (back to main); the titles end on main."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = d = tempfile.mkdtemp(prefix="bdmvkit-menu-")
        a = encode_clip(source(os.path.join(d, "a.mp4"), 3), os.path.join(d, "a.m2ts"),
                        chapters=[0, 1.5], fast=True)
        b = encode_clip(source(os.path.join(d, "b.mp4"), 2), os.path.join(d, "b.m2ts"),
                        fast=True)
        bg = png(os.path.join(d, "bg.png"), 1920, 1080, "navy")
        lit = png(os.path.join(d, "lit.png"), 400, 80, "orange")
        on = png(os.path.join(d, "on.png"), 400, 80, "red")
        off = png(os.path.join(d, "off.png"), 400, 80, "gray")
        disc = Disc()
        disc.add_title(a, chapters=[0, 1.5], end="menu:main")
        disc.add_title(b, end="menu:main")
        disc.add_menu("main", bg, [
            MenuButton("one", 160, 300, lit, on, off, action="title:1"),
            MenuButton("two", 160, 450, lit, on, off, action="title:2"),
            MenuButton("ch2", 160, 600, lit, on, off, action="chapter:1:2"),
            MenuButton("more", 160, 750, lit, action="menu:scenes"),
        ])
        disc.add_menu("scenes", bg, [MenuButton("back", 760, 900, lit, action="menu:main")])
        cls.out = os.path.join(d, "disc")
        cls.result = disc.write(cls.out, fast=True)
        cls.lit = lit

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def events(self, *keys):
        """The titles, playlists and chapters started after each key."""
        with bluray_sim.Disc(LIBBLURAY, self.out) as disc:
            disc.info()
            ev = disc.play(keys=keys)
        out, cur = [], None
        for e in ev:
            if e[0] == "key":
                cur = []
                out.append(cur)
            elif cur is not None and e[0] in ("title", "playlist", "at_chapter") and \
                    e[1] != 0xFFFF:
                cur.append(e)
        return out

    def test_files(self):
        self.assertEqual((self.result["titles"], self.result["menus"]), (2, 2))
        self.assertEqual(self.result["playlists"][-1], "00004.mpls")
        self.assertEqual(picture(self.lit)[:2], (400, 80))

    def test_first_play_is_the_menu(self):
        with bluray_sim.Disc(LIBBLURAY, self.out) as disc:
            info = disc.info()
            ev = disc.play(keys=["enter"])
        self.assertEqual(info["titles"], 4)
        # first play opens main (title 3) and draws its buttons
        before = ev[:next(i for i, e in enumerate(ev) if e[0] == "key")]
        self.assertIn(("title", 3), before)
        self.assertTrue(any(e[0] == "menu" and e[1] for e in ev))

    def test_buttons(self):
        got = self.events("enter")                       # ONE: title 1, then back to main
        self.assertEqual(got[0][:2], [("title", 1), ("playlist", 1)])
        self.assertIn(("title", 3), got[0])
        got = self.events("down", "enter")               # TWO
        self.assertEqual(got[1][:2], [("title", 2), ("playlist", 2)])
        # chapter 2 of title 1: its playlist from the second mark (the
        # player stays in the menu's title: a movie object plays it)
        got = self.events("down", "down", "enter")
        self.assertEqual(got[2][:2], [("playlist", 1), ("at_chapter", 2)])
        got = self.events("enter")                       # (title 1 from its start)
        self.assertIn(("at_chapter", 1), got[0])
        got = self.events("up", "enter")                 # nothing above ONE: still ONE
        self.assertEqual(got[1][:1], [("title", 1)])
        got = self.events("down", "down", "down", "enter", "enter")   # scenes, then back
        self.assertEqual(got[3][:1], [("title", 4)])
        self.assertEqual(got[4][:1], [("title", 3)])


@unittest.skipUnless(ENCODE_OK, "needs ffmpeg with libx264")
class TestCli(unittest.TestCase):
    def test_build_with_a_menu(self):
        import io
        import json
        from contextlib import redirect_stderr, redirect_stdout

        from bdmvkit.__main__ import main
        tmp = tempfile.mkdtemp(prefix="bdmvkit-cli-")
        self.addCleanup(shutil.rmtree, tmp, True)
        encode_clip(source(os.path.join(tmp, "s.mp4"), 2), os.path.join(tmp, "s.m2ts"), fast=True)
        png(os.path.join(tmp, "bg.png"), 1280, 720, "black")
        png(os.path.join(tmp, "b.png"), 300, 60, "white")
        with open(os.path.join(tmp, "disc.json"), "w") as f:
            json.dump({"titles": [{"clip": "s.m2ts", "end": "menu:main"}],
                       "menus": [{"id": "main", "background": "bg.png", "buttons": [
                           {"id": "play", "x": 100, "y": 900, "selected": "b.png",
                            "action": "title:1"}]}]}, f)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["build", os.path.join(tmp, "disc.json"),
                                   os.path.join(tmp, "out"), "--fast"]), 0)
        self.assertIn("1 title(s), 1 menu(s)", out.getvalue())
        self.assertTrue(os.path.isfile(os.path.join(tmp, "out", "BDMV", "STREAM", "00002.m2ts")))


class TestRefused(unittest.TestCase):
    def test_links(self):
        disc = Disc()
        disc.add_title("x.m2ts")
        disc.add_menu("main", "bg.png", [MenuButton("a", 0, 0, "a.png", action="menu:nope")])
        out = tempfile.mkdtemp(prefix="bdmvkit-")
        self.addCleanup(shutil.rmtree, out, True)
        with self.assertRaises(BdmvError) as cm:
            disc.write(out)
        self.assertIn("menu:nope", cm.exception.args[0])
        with self.assertRaises(BdmvError):
            disc.add_menu("main", "bg.png", [MenuButton("a", 0, 0, "a.png")])
        with self.assertRaises(BdmvError):
            disc.add_menu("empty", "bg.png", [])


if __name__ == "__main__":
    unittest.main()
