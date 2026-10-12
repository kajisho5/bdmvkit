"""A Program (program.py) written as a BDMV folder: its titles, playlists and
menus as Blu-ray titles, the movie objects that play them, and the HDMV
commands every action turns into.

Blu-ray titles, in order: one per title, one per playlist, "play all" when
an action starts it, one per menu, then one per link transition (a clip a
button plays before doing what it does). Movie objects: one per Blu-ray
title, in title order; then first play; then the Top Menu key; then one per
(title, chapter) an action starts from; then one per end-action override.
The general registers the commands keep their state in are the *_REG
numbers below.
"""

import dataclasses
import os
import shutil

from .clip import clpi
from .errors import BdmvError
from .formats import AUDIO_PID, CODING_AC3, DTS_CODINGS, video_codes
from .hdmv import (add, goto, if_at_least, if_equal, if_not_equal, index_bdmv, jump_object,
                   jump_title, jump_title_reg, move, movie_objects, play_pl, play_pl_mark, resume,
                   rnd, set_button, set_streams, set_subtitles)
from .m2ts import scan_m2ts, set_stream_types, stream_pids
from .playlist import mpls
from .program import parse_action, transition_key
from .uops import mask

LAST_MENU_REG = 1              # GPR: title number of the menu shown last
ENTRY_REG = 2                  # GPR: button a link selects in the menu it opens (0 = none)
LOOP_REG = 3                   # GPR: times the current menu has played (menus with a loop count)
OVERRIDE_REG = 4               # GPR: end-action override k of the playing title (0 = none)
STREAMS_REG = 5                # GPR: 1 = the link chose the streams, the title keeps them
COUNT_REG = 6                  # GPR: items a random or shuffled playlist has played
PICK_REG = 7                   # GPR: the item it picked (1-based)
PLAYED_REG = 8                 # GPRs 8..: 1 = shuffle has played that item

PLAYS = ("title", "chapter", "playlist", "playall")      # actions that start playing

DIRS = ["BDMV/PLAYLIST", "BDMV/CLIPINF", "BDMV/STREAM", "BDMV/AUXDATA", "BDMV/BDJO",
        "BDMV/JAR", "BDMV/META", "BDMV/BACKUP/PLAYLIST", "BDMV/BACKUP/CLIPINF",
        "BDMV/BACKUP/BDJO", "CERTIFICATE/BACKUP"]


def _write(out_dir, rel, data):
    for base in ("BDMV", os.path.join("BDMV", "BACKUP")):
        with open(os.path.join(out_dir, base, rel), "wb") as f:
            f.write(data)


def chapter_marks(chapters, scan):
    """Chapter marks (45 kHz): each chapter on the key frame nearest to it,
    the first at the start of the clip."""
    marks = [scan.first_pts // 2]
    keys = [pts for pts, _, _ in scan.entries]
    for t in sorted(c for c in chapters if c > 0):
        want = scan.first_pts + round(t * 90000)
        near = min(keys, key=lambda k: abs(k - want))
        if near // 2 > marks[-1]:
            marks.append(near // 2)
    return marks


@dataclasses.dataclass
class Piece:
    """An encoded clip as the playlists see it."""
    clip: str             # clip name, e.g. "00001"
    video_format: int
    frame_rate: int
    audio: list           # [(coding, channels, lang3, rate)]
    pg: list              # subtitle tracks [lang3]
    marks: list           # chapter starts, 45 kHz on the clip's time line
    end: int              # end of the clip, 45 kHz
    ig: bool = False      # the clip carries buttons (a menu, or a pop-up menu)
    hold: bool = False    # every chapter its own item held as a still (a slideshow)
    still: object = 0     # 2: hold the last picture (a still menu); (1, s): for s seconds
    uo: int = 0           # UO mask: the remote keys it does not allow (uops.mask)

    def item(self, first=1, last=None):
        """PlayItem covering chapters first..last (1-based, inclusive)."""
        start = self.marks[first - 1]
        stop = self.marks[last] if last and last < len(self.marks) else self.end
        return (self.clip, start, stop, self.video_format, self.frame_rate, self.audio, self.pg,
                self.ig, self.still, self.uo)


class Navigation:
    """The disc's Blu-ray titles, the movie objects that play them, and the
    commands an action (a button's, an end action, first play) turns into.
    A link transition's object plays it and then does what its button would
    have done."""

    def __init__(self, program):
        self.program = p = program
        titles = [("title", t.id, t.end) for t in p.titles]
        titles += [("playlist", x.id, x.end) for x in p.playlists]
        if p.uses_playall:
            titles.append(("playall", None, p.titles[-1].end))
        titles += [("menu", m.id, None) for m in p.menus]
        self.transitions = p.link_transitions
        titles += [("transition", k, None) for k in range(1, len(self.transitions) + 1)]
        self.titles = titles
        self.numbers = {f"{k}:{i}" if i else k: n for n, (k, i, _) in enumerate(titles, 1)}
        chapters = []
        for a in p.actions():           # buttons, end actions, first play ...
            kind, tid, n = parse_action(a)
            if kind == "chapter" and (tid, n) not in chapters:
                chapters.append((tid, n))
        # random and shuffled playlists: a playlist file per item (after the
        # titles' own), played one by one in the order the object picks
        self.item_playlists = {}
        k = len(titles) + 1
        for x in p.playlists:
            if x.order != "sequential":
                self.item_playlists[x.id] = list(range(k, k + len(x.items)))
                k += len(x.items)
        self.first_play = len(titles)
        self.top_menu = len(titles) + 1
        self.chapter_objects = {key: len(titles) + 2 + k for k, key in enumerate(chapters)}
        # links that switch streams and then play: the title must not set its
        # own default subtitles over the chosen ones (_start)
        self.stream_links = any(
            (b.audio or b.subtitle is not None) and b.action and parse_action(b.action)[0] in PLAYS
            for b in p.buttons())

    def menu_number(self, menu_id):
        return self.numbers.get(f"menu:{menu_id}")

    def go(self, action):
        """Commands that go where `action` says, or [] (stop, or nowhere)."""
        kind, ident, n = parse_action(action or "stop")
        if kind == "chapter":
            if n == 1:
                return [jump_title(self.numbers[f"title:{ident}"])]
            return [jump_object(self.chapter_objects[(ident, n)])]
        if kind == "lastmenu":
            return [jump_title_reg(LAST_MENU_REG)] if self.program.menus else []
        if kind == "resume":
            return [resume()]
        if kind == "menu" and n:
            # that button selected: the menu's object picks it up (objects)
            ids = [b.id for b in self.program.menu(ident).buttons]
            return [move(ENTRY_REG, ids.index(n)), jump_title(self.numbers[f"menu:{ident}"])]
        key = f"{kind}:{ident}" if ident else kind
        return [jump_title(self.numbers[key])] if key in self.numbers else []

    def button(self, b):
        """A menu button's commands: its streams, then its action; or, with a
        link transition, the transition (whose object then does them)."""
        if b.transition:
            k = self.transitions.index(transition_key(b)) + 1
            return [jump_title(self.numbers[f"transition:{k}"])]
        return self.link(b.action, b.override, b.audio, b.subtitle)

    def link(self, action, override=None, audio=None, subtitle=None):
        kind, _, n = parse_action(action or "stop")
        cmds = []
        audio = n if kind == "audio" else audio
        sub = n if kind == "subtitle" else subtitle
        if audio or sub is not None:
            cmds.append(set_streams(audio, sub))
            if kind in PLAYS:
                cmds.append(move(STREAMS_REG, 1))
        if kind not in ("audio", "subtitle"):
            if override:
                # the title's object takes the override when it ends (_ends)
                cmds.append(move(OVERRIDE_REG, self.program.overrides.index(override) + 1))
            elif self.program.overrides and kind in PLAYS:
                cmds.append(move(OVERRIDE_REG, 0))
            cmds += self.go(action)
        return cmds

    def _ends(self, end):
        """A title's commands after it played: an override a button set, else
        `end`. Overrides are objects of their own after the chapter ones."""
        p = self.program
        first = len(self.titles) + 2 + len(self.chapter_objects)
        out = []
        for k in range(1, len(p.overrides) + 1):
            out += [if_equal(OVERRIDE_REG, k), jump_object(first + k - 1)]
        return out + self.go(end)

    def _entry(self, menu):
        """For a menu that links open on a particular button: select that
        button, or else its default one, before it plays (its buttons follow
        the selection: igs.ig_stream(follow_selection=True))."""
        if menu.id not in self.program.entry_buttons:
            return []
        ids = [b.id for b in menu.buttons]
        default = ids.index(menu.default) if menu.default else 0
        return [if_not_equal(ENTRY_REG, 0), set_button(reg=ENTRY_REG),
                if_equal(ENTRY_REG, 0), set_button(default), move(ENTRY_REG, 0)]

    def follows_selection(self, menu_id):
        """Whether the menu's IG stream must take the selected button from
        the player (it is opened on a button)."""
        return menu_id in self.program.entry_buttons

    def _start(self, title):
        """Subtitles as the title starts: its default track, or none; unless
        the link that started it chose them (a button with `subtitle`)."""
        keep = [move(STREAMS_REG, 0)] if self.stream_links else []
        if not title.subtitles:
            return keep
        on = next((k for k, sub in enumerate(title.subtitles, 1) if sub.default), 0)
        if keep:
            return [if_equal(STREAMS_REG, 0), set_subtitles(on)] + keep
        return [set_subtitles(on)]

    def _picked(self, pl, numbers, base):
        """Commands playing a random or shuffled playlist's items, each its
        own playlist file (`numbers`), from command `base` of the object on.
        Random: as many picks as there are items, an item may come again;
        shuffle: each item once (a pick already played is picked again)."""
        n, shuffle = len(numbers), pl.order == "shuffle"
        cmds = [move(COUNT_REG, 0)] + ([move(PLAYED_REG + k, 0) for k in range(n)]
                                       if shuffle else [])
        top = base + len(cmds)
        size = 6 if shuffle else 3
        blocks = top + 3 + 2 * n + 1
        end = blocks + size * n
        cmds += [if_at_least(COUNT_REG, n), goto(end), rnd(PICK_REG, n)]
        for k in range(n):
            cmds += [if_equal(PICK_REG, k + 1), goto(blocks + size * k)]
        cmds.append(goto(top))
        for k, number in enumerate(numbers):
            if shuffle:
                cmds += [if_equal(PLAYED_REG + k, 1), goto(top + 2),
                         move(PLAYED_REG + k, 1)]
            cmds += [play_pl(number), add(COUNT_REG, 1), goto(top)]
        assert base + len(cmds) == end
        return cmds

    def objects(self, menus=None):
        """All movie objects. menus: {menu id: (still, loop_mark)} for the
        menus' own objects (a still menu holds its picture; others play
        again from the loop point, mark 1, or from the start)."""
        p = self.program
        menus = menus or {}
        out = []
        for n, (kind, ident, end) in enumerate(self.titles, 1):
            if kind == "transition":
                _, action, override, audio, subtitle = self.transitions[ident - 1]
                out.append([play_pl(n)] + self.link(action, override, audio, subtitle))
                continue
            if kind == "menu":
                still, loop_mark = menus.get(ident, (True, 0))
                m = p.menu(ident)
                cmds = self._entry(m) + [move(LAST_MENU_REG, n)]
                if m.loop is not None:
                    # played m.loop times (a still one holds its picture for its
                    # length each time), then its end action
                    cmds += [move(LOOP_REG, 1), play_pl(n)]
                    top = len(cmds)
                    end = self.go(m.end)
                    cmds += [if_at_least(LOOP_REG, m.loop), goto(top + 5), add(LOOP_REG, 1),
                             play_pl_mark(n, loop_mark), goto(top)] + end
                    out.append(cmds)
                    continue
                cmds.append(play_pl(n))
                if not still:
                    cmds += [play_pl_mark(n, loop_mark), goto(len(cmds))]
                out.append(cmds)
                continue
            first = p.title(ident) if kind == "title" else \
                p.title(p.playlist(ident).items[0].title) if kind == "playlist" \
                else p.titles[0]
            ends = self._ends(end) if kind == "title" else self.go(end)
            start = self._start(first)
            if kind == "playlist" and ident in self.item_playlists:
                out.append(start + self._picked(p.playlist(ident), self.item_playlists[ident],
                                                len(start)) + ends)
                continue
            out.append(start + [play_pl(n)] + ends)
        # first play: the disc's starting sound track, once (titles set their
        # own subtitles as they start, _start)
        aud = next((j for t in p.titles for j, tr in enumerate(t.audio, 1) if tr.default), None)
        out.append(([set_streams(audio=aud)] if aud else []) +
                   (self.go(p.first_play) or [jump_title(1)]))
        top = p.title_key or (f"menu:{p.menus[0].id}" if p.menus else None)
        out.append(self.go(top) or [jump_title(1)])
        for (tid, n), _ in sorted(self.chapter_objects.items(), key=lambda kv: kv[1]):
            t = p.title(tid)
            out.append(self._start(t) + [play_pl_mark(self.numbers[f"title:{tid}"], n - 1)] +
                       self._ends(t.end))
        for action in p.overrides:
            out.append([move(OVERRIDE_REG, 0)] + self.go(action))
        return out


def parts_items(parts):
    """(items, marks) of a playlist of (piece, first chapter, last chapter)."""
    if any(piece.hold for piece, _, _ in parts):
        # (a slideshow advanced by hand: one item per picture, each held)
        split = []
        for piece, first, last in parts:
            if piece.hold:
                last = last or len(piece.marks)
                split += [(piece, k, k) for k in range(first, last + 1)]
            else:
                split.append((piece, first, last))
        parts = split
    items, marks = [], []
    for k, (piece, first, last) in enumerate(parts):
        item = piece.item(first, last)
        if piece.hold:
            item = item[:8] + (2,) + item[9:]
        items.append(item)
        marks += [(k, m) for m in piece.marks if item[1] <= m < item[2]]
    return items, marks


def _codes(fps, program):
    codes = video_codes(fps, program.video)
    if codes is None:
        raise BdmvError(f"{fps[0]}/{fps[1]} fps has no Blu-ray {program.video} format")
    return codes


def write_program(program, out_dir, move=True):
    """Write `program` as the BDMV folder in `out_dir`: the clips go into
    BDMV/STREAM (moved, or copied when `move` is false). Returns {"titles",
    "playlists", "chapters"}."""
    program.check()
    p = program
    fps = p.fps or p.titles[0].fps
    place = shutil.move if move else shutil.copyfile
    for d in DIRS:
        os.makedirs(os.path.join(out_dir, d), exist_ok=True)

    def clip(src, name):
        dest = os.path.join(out_dir, "BDMV", "STREAM", f"{name}.m2ts")
        if os.path.abspath(src) != os.path.abspath(dest):
            place(src, dest)
        return dest

    pieces, chapters = {}, []
    for n, t in enumerate(p.titles, 1):
        name = f"{n:05d}"
        scan = scan_m2ts(t.clip)
        video_format, frame_rate = _codes(t.fps, p)
        audio = [(a.coding, a.channels, a.lang, a.rate) for a in t.audio]
        pg = [s.lang for s in t.subtitles]
        marks = chapter_marks(t.chapters, scan)
        chapters.append(len(marks))
        pieces[t.id] = Piece(name, video_format, frame_rate, audio, pg, marks,
                             scan.end_pts // 2, ig=t.popup, hold=t.hold, uo=mask(t.prohibit))
        types = audio_stream_types(t)
        _write(out_dir, os.path.join("CLIPINF", f"{name}.clpi"),
               clpi(scan, video_format, frame_rate, audio, pg, ig=t.popup))
        if types:
            set_stream_types(clip(t.clip, name), types)
        else:
            clip(t.clip, name)
    for a in p.actions():
        kind, tid, c = parse_action(a)
        if kind == "chapter" and c > chapters[p.titles.index(p.title(tid))]:
            raise BdmvError(f"{a!r}: title {tid!r} has fewer chapters")
    loops = {}
    for k, m in enumerate(p.menus, len(p.titles) + 1):
        name = f"{k:05d}"
        scan = scan_m2ts(m.clip)
        video_format, frame_rate = _codes(m.fps or fps, p)
        audio = [(CODING_AC3, 2, "und")] if m.music else []
        marks = [scan.first_pts // 2]
        if m.loop_point:
            # the second time round the menu plays from its loop point
            want = scan.first_pts + round(m.loop_point * 90000)
            marks.append(min((e[0] for e in scan.entries), key=lambda x: abs(x - want)) // 2)
        still = ((1, m.still_time) if m.still_time else 2) if m.still else 0
        pieces[f"menu:{m.id}"] = Piece(name, video_format, frame_rate, audio, [], marks,
                                       scan.end_pts // 2, ig=True, still=still,
                                       uo=mask(m.prohibit))
        loops[m.id] = (m.still, len(marks) - 1)
        _write(out_dir, os.path.join("CLIPINF", f"{name}.clpi"),
               clpi(scan, video_format, frame_rate, audio, (), ig=True))
        clip(m.clip, name)
    first = len(p.titles) + len(p.menus) + 1
    for k, key in enumerate(sorted({key[0] for key in p.link_transitions}), first):
        name = f"{k:05d}"
        scan = scan_m2ts(p.transitions[key])
        video_format, frame_rate = _codes(fps, p)
        audio = [(CODING_AC3, 2, "und")]
        pieces[key] = Piece(name, video_format, frame_rate, audio, [], [scan.first_pts // 2],
                            scan.end_pts // 2)
        _write(out_dir, os.path.join("CLIPINF", f"{name}.clpi"),
               clpi(scan, video_format, frame_rate, audio))
        clip(p.transitions[key], name)
    nav = Navigation(p)
    for n, (kind, ident, _) in enumerate(nav.titles, 1):
        items, marks = parts_items(_parts(p, nav, kind, ident, pieces))
        # a title's or a menu's keys are off for its whole playlist; in a
        # playlist or play all, each item keeps its own title's
        whole = pieces[ident if kind == "title" else f"menu:{ident}"].uo \
            if kind in ("title", "menu") else 0
        _write(out_dir, os.path.join("PLAYLIST", f"{n:05d}.mpls"), mpls(items, marks, whole))
    for pid, numbers in nav.item_playlists.items():
        for it, n in zip(p.playlist(pid).items, numbers):
            items, marks = parts_items([(pieces[it.title], it.first, it.last)])
            _write(out_dir, os.path.join("PLAYLIST", f"{n:05d}.mpls"), mpls(items, marks))
    first_piece = pieces[p.titles[0].id]
    interactive = {n for n, (kind, _, _) in enumerate(nav.titles, 1) if kind == "menu"}
    _write(out_dir, "index.bdmv", index_bdmv(list(range(len(nav.titles))), nav.first_play,
                                             nav.top_menu, first_piece.video_format,
                                             first_piece.frame_rate, interactive))
    _write(out_dir, "MovieObject.bdmv", movie_objects(nav.objects(loops)))
    return {"titles": len(nav.titles),
            "playlists": [f"{n:05d}.mpls" for n in range(1, len(nav.titles) + 1)],
            "chapters": chapters}


def audio_stream_types(title):
    """{PID: stream type} the title's clip needs changed so that its sound
    tracks are marked as the title declares them. ffmpeg marks DTS by its
    channels (0x85 above 6, else 0x82), not by the extensions it carries, so
    a DTS track takes the declared DTS, DTS-HD or DTS-HD Master Audio type; a
    track of another kind than declared is an error."""
    have = stream_pids(title.clip)
    out = {}
    for k, a in enumerate(title.audio):
        got = have.get(AUDIO_PID + k)
        if got is None or got == a.coding:
            continue
        if got in DTS_CODINGS and a.coding in DTS_CODINGS:
            out[AUDIO_PID + k] = a.coding
        else:
            raise BdmvError(f"title {title.id!r}: sound track {k + 1} has stream type "
                            f"{got:#04x} in {title.clip}, not the declared {a.coding:#04x}")
    return out


def _parts(p, nav, kind, ident, pieces):
    """(piece, first chapter, last chapter) of one Blu-ray title's playlist."""
    if kind == "title":
        return [(pieces[ident], 1, None)]
    if kind == "playlist":
        return [(pieces[it.title], it.first, it.last) for it in p.playlist(ident).items]
    if kind == "menu":
        return [(pieces[f"menu:{ident}"], 1, None)]
    if kind == "transition":
        return [(pieces[nav.transitions[ident - 1][0]], 1, None)]
    return [(pieces[t.id], 1, None) for t in p.titles]
