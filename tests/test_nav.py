"""Navigation: what each action, title, playlist and menu turns into (the
movie objects and their commands), and a disc using all of it played by
libbluray with the remote's keys."""

import os
import shutil
import tempfile
import unittest

from bdmvkit import BdmvError, Disc, MenuButton, hdmv, nav, uops
from bdmvkit.encode import encode_clip
from bdmvkit.program import (Audio, Button, Menu, Playlist, PlaylistItem, Program, Subtitle,
                             Title, parse_action)

from .test_disc import ENCODE_OK, source
from .test_menus import png

try:
    from . import bluray_sim
    LIBBLURAY = bluray_sim.load_library()
except Exception:  # pragma: no cover
    LIBBLURAY = None


def program(**kw):
    """Two titles (the second with two subtitle tracks, the second one
    shown) and a menu with a button per title, plus `kw`."""
    titles = [Title("a", "a.m2ts", audio=[Audio(0x81)], end="menu:main"),
              Title("b", "b.m2ts", audio=[Audio(0x81), Audio(0x81, default=True)],
                    subtitles=[Subtitle("eng"), Subtitle("jpn", default=True)],
                    end="lastmenu")]
    menus = [Menu("main", "m.m2ts", [Button("one", "title:a"), Button("two", "chapter:b:2")])]
    args = dict(titles=titles, menus=menus)
    args.update(kw)
    return Program(**args)


class TestActions(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_action("chapter:t:2"), ("chapter", "t", 2))
        self.assertEqual(parse_action("menu:m:b"), ("menu", "m", "b"))
        self.assertEqual(parse_action("subtitle:off"), ("subtitle", None, 0))
        self.assertEqual(parse_action("lastmenu"), ("lastmenu", None, None))

    def test_go(self):
        n = nav.Navigation(program())
        # titles a, b, then the menu: Blu-ray titles 1, 2, 3
        self.assertEqual(n.numbers, {"title:a": 1, "title:b": 2, "menu:main": 3})
        self.assertEqual(n.go("title:b"), [hdmv.jump_title(2)])
        self.assertEqual(n.go("chapter:a:1"), [hdmv.jump_title(1)])
        # chapter 2 of b: an object of its own after first play and the top menu
        self.assertEqual(n.chapter_objects, {("b", 2): 5})
        self.assertEqual(n.go("chapter:b:2"), [hdmv.jump_object(5)])
        self.assertEqual(n.go("lastmenu"), [hdmv.jump_title_reg(nav.LAST_MENU_REG)])
        self.assertEqual(n.go("resume"), [hdmv.resume()])
        self.assertEqual(n.go("stop"), [])
        self.assertEqual(n.go("menu:main:two"),
                         [hdmv.move(nav.ENTRY_REG, 1), hdmv.jump_title(3)])

    def test_refused(self):
        with self.assertRaises(BdmvError):
            program(first_play="title:nope").check()
        with self.assertRaises(BdmvError):
            program(first_play="menu:main:nope").check()
        with self.assertRaises(BdmvError):
            program(playlists=[Playlist("p", [PlaylistItem("x")])]).check()
        p = program()
        p.titles[0].prohibit = ["eject"]
        with self.assertRaises(BdmvError):
            p.check()


class TestObjects(unittest.TestCase):
    def test_titles_menus_and_first_play(self):
        n = nav.Navigation(program())
        objs = n.objects()
        # title a: no subtitles; then its end action
        self.assertEqual(objs[0], [hdmv.play_pl(1), hdmv.jump_title(3)])
        # title b starts with its second subtitle track, ends on the last menu
        self.assertEqual(objs[1], [hdmv.set_subtitles(2), hdmv.play_pl(2),
                                   hdmv.jump_title_reg(nav.LAST_MENU_REG)])
        # the menu says it is the last menu shown, then holds its picture
        self.assertEqual(objs[2], [hdmv.move(nav.LAST_MENU_REG, 3), hdmv.play_pl(3)])
        # first play: the starting sound track (b's second), then title 1
        self.assertEqual(objs[n.first_play], [hdmv.set_streams(audio=2), hdmv.jump_title(1)])
        # the Top Menu key: the first menu
        self.assertEqual(objs[n.top_menu], [hdmv.jump_title(3)])
        # chapter 2 of b: its subtitles, from its second mark
        self.assertEqual(objs[5], [hdmv.set_subtitles(2), hdmv.play_pl_mark(2, 1),
                                   hdmv.jump_title_reg(nav.LAST_MENU_REG)])

    def test_buttons(self):
        p = program()
        p.menus[0].buttons += [Button("jp", "title:b", audio=2, subtitle=0),
                               Button("sub", "subtitle:1")]
        n = nav.Navigation(p)
        jp, sub = p.menus[0].buttons[2:]
        # streams first; a link that plays keeps them (STREAMS_REG)
        self.assertEqual(n.button(jp), [hdmv.set_streams(2, 0), hdmv.move(nav.STREAMS_REG, 1),
                                        hdmv.jump_title(2)])
        self.assertEqual(n.button(sub), [hdmv.set_streams(None, 1)])
        # ... and the title then sets its default subtitles only if not chosen
        self.assertEqual(n.objects()[1][:3], [hdmv.if_equal(nav.STREAMS_REG, 0),
                                              hdmv.set_subtitles(2),
                                              hdmv.move(nav.STREAMS_REG, 0)])

    def test_override(self):
        p = program()
        p.menus[0].buttons.append(Button("then", "title:a", override="title:b"))
        n = nav.Navigation(p)
        self.assertEqual(n.button(p.menus[0].buttons[2]),
                         [hdmv.move(nav.OVERRIDE_REG, 1), hdmv.jump_title(1)])
        # a plain link clears it
        self.assertEqual(n.button(p.menus[0].buttons[0])[0], hdmv.move(nav.OVERRIDE_REG, 0))
        objs = n.objects()
        # title a looks at the override before its own end action
        self.assertEqual(objs[0][1:], [hdmv.if_equal(nav.OVERRIDE_REG, 1),
                                       hdmv.jump_object(len(objs) - 1), hdmv.jump_title(3)])
        self.assertEqual(objs[-1], [hdmv.move(nav.OVERRIDE_REG, 0), hdmv.jump_title(2)])

    def test_entry_button_and_loop(self):
        p = program(first_play="menu:main:two")
        p.menus[0].loop, p.menus[0].end = 2, "title:b"
        n = nav.Navigation(p)
        self.assertTrue(n.follows_selection("main"))
        menu = n.objects()[2]
        self.assertEqual(menu[:5], [hdmv.if_not_equal(nav.ENTRY_REG, 0),
                                    hdmv.set_button(reg=nav.ENTRY_REG),
                                    hdmv.if_equal(nav.ENTRY_REG, 0), hdmv.set_button(0),
                                    hdmv.move(nav.ENTRY_REG, 0)])
        # played twice, then title b
        self.assertEqual(menu[5:], [hdmv.move(nav.LAST_MENU_REG, 3), hdmv.move(nav.LOOP_REG, 1),
                                    hdmv.play_pl(3), hdmv.if_at_least(nav.LOOP_REG, 2),
                                    hdmv.goto(13), hdmv.add(nav.LOOP_REG, 1),
                                    hdmv.play_pl_mark(3, 0), hdmv.goto(8),
                                    hdmv.jump_title(2)])

    def test_playlists(self):
        items = [PlaylistItem("a"), PlaylistItem("b", 2)]
        p = program(playlists=[Playlist("seq", items), Playlist("mix", items, "shuffle")],
                    title_key="playall")
        n = nav.Navigation(p)
        # titles, playlists, play all, then the menu
        self.assertEqual([t[0] for t in n.titles],
                         ["title", "title", "playlist", "playlist", "playall", "menu"])
        # the shuffled one: a playlist file per item after the titles'
        self.assertEqual(n.item_playlists, {"mix": [7, 8]})
        mix = n.objects()[3]
        self.assertIn(hdmv.rnd(nav.PICK_REG, 2), mix)
        self.assertEqual([c for c in mix if c[:2] == hdmv.play_pl(7)[:2]],
                         [hdmv.play_pl(7), hdmv.play_pl(8)])

    def test_uo_mask(self):
        self.assertEqual(uops.mask(["next"]), 1 << 59)
        self.assertEqual(uops.mask(["menu"]), (1 << 63) | (1 << 39))


@unittest.skipUnless(ENCODE_OK and LIBBLURAY, "needs ffmpeg with libx264, and libbluray")
class TestDisc(unittest.TestCase):
    """A disc that opens on its menu: PLAY ALL (the titles in order), MIX (a
    shuffled playlist of both), SCENE (chapter 2 of title 1, then the menu
    it came from), TWO (title 2, which cannot be skipped or fast-forwarded).
    The disc starts on another menu that holds its picture twice and then
    goes on to the main one by itself."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = d = tempfile.mkdtemp(prefix="bdmvkit-nav-")
        a = encode_clip(source(os.path.join(d, "a.mp4"), 3), os.path.join(d, "a.m2ts"),
                        chapters=[0, 1.5], fast=True)
        b = encode_clip(source(os.path.join(d, "b.mp4"), 2), os.path.join(d, "b.m2ts"),
                        fast=True)
        bg = png(os.path.join(d, "bg.png"), 1920, 1080, "navy")
        lit = png(os.path.join(d, "lit.png"), 400, 80, "orange")
        disc = Disc(first_play="menu:timed", title_key="menu:main")
        disc.add_title(a, chapters=[0, 1.5], end="lastmenu")
        disc.add_title(b, end="lastmenu", prohibit=["next", "fast_forward"])
        disc.add_playlist("mix", [1, 2], order="shuffle", end="menu:main")
        disc.add_menu("main", bg, [
            MenuButton("all", 160, 200, lit, action="playall"),
            MenuButton("mix", 160, 350, lit, action="playlist:mix"),
            MenuButton("scene", 160, 500, lit, action="chapter:1:2"),
            MenuButton("two", 160, 650, lit, action="title:2"),
        ])
        disc.add_menu("timed", bg, [MenuButton("go", 160, 200, lit, action="menu:main")],
                      loop=2, end="menu:main", seconds=0.5)
        cls.out = os.path.join(d, "disc")
        cls.result = disc.write(cls.out, play_all=False, fast=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def play(self, *keys):
        with bluray_sim.Disc(LIBBLURAY, self.out) as disc:
            return disc.play(keys=keys)

    def after(self, events, k):
        """The titles and playlists started after key k (0-based)."""
        out, n = [], -1
        for e in events:
            if e[0] == "key":
                n += 1
            elif n == k and e[0] in ("title", "playlist") and e[1] != 0xFFFF:
                out.append(e)
        return out

    def test_play_all(self):
        ev = self.play("enter")
        # play all is its own title (after the playlist): both clips, then the last menu
        got = self.after(ev, 0)
        self.assertEqual(got[:2], [("title", 4), ("playlist", 4)])
        self.assertIn(("title", 5), got)

    def test_shuffle_plays_each_once(self):
        ev = self.play("down", "enter")
        got = self.after(ev, 1)
        played = [v for k, v in got if k == "playlist" and v >= 7]
        self.assertEqual(sorted(played), [7, 8])           # its items' own playlists
        self.assertIn(("title", 5), got)                    # then the menu

    def test_scene_then_back(self):
        ev = self.play("down", "down", "enter")
        got = self.after(ev, 2)
        self.assertEqual(got[0], ("playlist", 1))
        self.assertIn(("title", 5), got)                    # lastmenu: back to main

    def test_title_two_keys_off(self):
        # its playlist's UO mask: Next and Fast forward off; title 1's: none
        def mask(n):
            with open(os.path.join(self.out, "BDMV", "PLAYLIST", f"{n:05d}.mpls"), "rb") as f:
                return f.read()[48:56]
        self.assertEqual(mask(2), uops.mask(["next", "fast_forward"]).to_bytes(8, "big"))
        self.assertEqual(mask(1), bytes(8))
        # (and title 2 still plays from the menu)
        ev = self.play("down", "down", "down", "enter")
        self.assertEqual(self.after(ev, 3)[:2], [("title", 2), ("playlist", 2)])

    def test_menu_times_out(self):
        # the first menu holds its picture twice (two still times), then the main one
        ev = self.play("enter")
        before = ev[:next(i for i, e in enumerate(ev) if e[0] == "key")]
        self.assertEqual([v for k, v in before if k == "title" and v != 0xFFFF], [6, 5])
        self.assertEqual(len([e for e in before if e[0] == "still"]), 2)
