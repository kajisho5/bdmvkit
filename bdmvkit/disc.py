"""A BDMV folder from encoded clips: titles with chapters, played from the
first one on (or each on its own), with their sound and subtitle tracks.

    disc = Disc()
    disc.add_title("feature.m2ts", chapters=[0, 300, 600], audio=[("ac3", 6, "en")],
                   subtitles=["en", "ja"])
    disc.add_title("extras.m2ts")
    disc.write("out")            # out/BDMV/...

Each title is a playlist with a chapter mark at every chapter (on the key
frame nearest to it: encode the clip with key frames there, as
encode.encode_clip does) and a movie object that plays it. First play and
the Top Menu key start title 1; with `play_all`, each title goes on to the
next when it ends. Clips are BDAV streams with the PIDs formats.py names.

Menus: a picture with buttons, each linked to a title, a chapter or
another menu:

    disc.add_menu("main", "menu.png", [
        MenuButton("play", 160, 700, "play.png", action="title:1"),
        MenuButton("scenes", 160, 800, "scenes.png", "scenes-lit.png", action="menu:scenes"),
    ])
    disc.add_title("feature.m2ts", end="menu:main")     # back to the menu at the end

A button's pictures are its selected (and activated) look, drawn over the
menu where it is; with a `normal` picture it is drawn there before it is
selected too. The arrow keys go to the nearest button that way unless
`nav` says otherwise. Each menu is an interactive title after the titles:
its picture held as a still, its buttons an IG stream (igs.py) in its clip.
With menus, first play and the Top Menu key open the first menu.
"""

import dataclasses
import os
import shutil

import tempfile

from . import clip as clip_info
from . import encode, hdmv, igs, playlist
from .errors import BdmvError
from .formats import AUDIO_PID, CODECS, FORMATS, HEIGHT, PG_PID, WIDTH, lang3
from .m2ts import scan_m2ts, stream_pids

DIRS = ["BDMV/PLAYLIST", "BDMV/CLIPINF", "BDMV/STREAM", "BDMV/AUXDATA", "BDMV/BDJO",
        "BDMV/JAR", "BDMV/META", "BDMV/BACKUP/PLAYLIST", "BDMV/BACKUP/CLIPINF",
        "BDMV/BACKUP/BDJO", "CERTIFICATE/BACKUP"]


@dataclasses.dataclass
class Title:
    clip: str                    # an encoded .m2ts
    fps: tuple = (24000, 1001)   # its frame rate: 24000/1001, 25/1 or 30000/1001
    chapters: list = dataclasses.field(default_factory=lambda: [0.0])   # starts, seconds
    audio: list = dataclasses.field(default_factory=lambda: [("ac3", 2, "und")])
    subtitles: list = dataclasses.field(default_factory=list)          # PG tracks: languages
    end: str = None              # after it: "title:<n>", "menu:<id>" (None: the next with play_all)


@dataclasses.dataclass
class MenuButton:
    id: str
    x: int                       # top-left on the 1920 x 1080 menu
    y: int
    selected: str                # picture files (PNG ...): selected,
    activated: str = None        # activated (default: the selected one),
    normal: str = None           # and before it is selected (default: nothing)
    action: str = None           # "title:<n>", "chapter:<n>:<c>", "menu:<id>"
    nav: dict = dataclasses.field(default_factory=dict)    # direction -> button id
    auto: bool = False           # runs as soon as it is selected


@dataclasses.dataclass
class Menu:
    id: str
    background: str              # picture file, fitted into the HD frame
    buttons: list
    fps: tuple = (24000, 1001)
    default: str = None          # the button selected first (default: the first)


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


def _check_streams(n, title):
    """The title's sound and subtitle tracks must be in its clip, with the
    PIDs the playlist gives them (encode.encode_clip makes them so)."""
    pids = stream_pids(title.clip)
    want = [("audio", AUDIO_PID, k) for k in range(len(title.audio))] + \
        [("subtitle", PG_PID, k) for k in range(len(title.subtitles))]
    for kind, first, k in want:
        if first + k not in pids:
            raise BdmvError(f"title {n}: {kind} track {k + 1} is not in {title.clip} "
                            f"(no stream with PID {first + k:#06x})")


def _write(out_dir, rel, data):
    for base in ("BDMV", os.path.join("BDMV", "BACKUP")):
        with open(os.path.join(out_dir, base, rel), "wb") as f:
            f.write(data)


class Disc:
    def __init__(self):
        self.titles = []
        self.menus = []

    def add_title(self, clip, fps=(24000, 1001), chapters=(0.0,), audio=(("ac3", 2, "und"),),
                  subtitles=(), end=None):
        """Add a title; returns its number (1-based). audio: (codec, channels,
        language) per track, codec "ac3", "lpcm" or "dts"; languages are ISO
        639-1 ("en") or 639-2 ("eng") codes. end: where it goes when it ends,
        "title:<n>" or "menu:<id>" (default: the next title with play_all)."""
        if tuple(fps) not in FORMATS:
            raise BdmvError(f"{fps[0]}/{fps[1]} fps has no Blu-ray format")
        for codec, _, _ in audio:
            if codec not in CODECS:
                raise BdmvError(f"unknown audio codec {codec!r} (ac3, lpcm or dts)")
        if not audio:
            raise BdmvError("a title needs at least one audio track")
        self.titles.append(Title(clip, tuple(fps), list(chapters) or [0.0], list(audio),
                                 list(subtitles), end))
        return len(self.titles)

    def add_menu(self, menu_id, background, buttons, fps=(24000, 1001), default=None):
        """Add a menu: `background` a picture, `buttons` MenuButtons. The
        menu's clip is made when the disc is written (ffmpeg)."""
        if tuple(fps) not in FORMATS:
            raise BdmvError(f"{fps[0]}/{fps[1]} fps has no Blu-ray format")
        if any(m.id == menu_id for m in self.menus):
            raise BdmvError(f"there is a menu {menu_id!r} already")
        if not buttons:
            raise BdmvError(f"menu {menu_id!r} needs at least one button")
        self.menus.append(Menu(menu_id, background, list(buttons), tuple(fps), default))

    def _links(self):
        """{action: commands} for every link the titles and buttons use, and
        the chapter objects [(title, chapter)] they need."""
        n_titles = len(self.titles)
        menu_title = {m.id: n_titles + k for k, m in enumerate(self.menus, 1)}
        actions = [t.end for t in self.titles if t.end] + \
            [b.action for m in self.menus for b in m.buttons if b.action]
        links, chapter_objects = {}, []
        for a in actions:
            kind, _, rest = a.partition(":")
            if kind == "title" and rest.isdigit() and 1 <= int(rest) <= n_titles:
                links[a] = [hdmv.jump_title(int(rest))]
            elif kind == "menu" and rest in menu_title:
                links[a] = [hdmv.jump_title(menu_title[rest])]
            elif kind == "chapter":
                n, _, c = rest.partition(":")
                if not (n.isdigit() and c.isdigit() and 1 <= int(n) <= n_titles):
                    raise BdmvError(f"{a!r}: no such title")
                key = (int(n), int(c))
                if key not in chapter_objects:
                    chapter_objects.append(key)
                links[a] = key                  # (its object's number: once known)
            else:
                raise BdmvError(f"{a!r}: not title:<n>, chapter:<n>:<c> or menu:<id> "
                                "of this disc")
        return links, chapter_objects, menu_title

    def write(self, out_dir, move=False, play_all=True, fast=False):
        """Write the BDMV folder into `out_dir` (copying the clips into
        BDMV/STREAM, or moving them with `move`; menu clips are encoded,
        quickly with `fast`). Returns {"titles", "menus", "playlists",
        "chapters"}."""
        if not self.titles:
            raise BdmvError("a disc needs at least one title")
        links, chapter_objects, menu_title = self._links()
        n_titles = len(self.titles)
        # movie objects: one per title, one per menu, first play, top menu,
        # then one per chapter a link starts
        first_chapter_object = n_titles + len(self.menus) + 2
        for a, v in links.items():
            if isinstance(v, tuple):
                links[a] = [hdmv.jump_object(first_chapter_object + chapter_objects.index(v))]
        for d in DIRS:
            os.makedirs(os.path.join(out_dir, d), exist_ok=True)
        objects, chapters = [], []
        for n, t in enumerate(self.titles, 1):
            name = f"{n:05d}"
            scan = scan_m2ts(t.clip)
            _check_streams(n, t)
            video_format, frame_rate = FORMATS[t.fps]
            audio = [(CODECS[c], ch, _lang(lang)) for c, ch, lang in t.audio]
            pg = [_lang(lang) for lang in t.subtitles]
            marks = chapter_marks(t.chapters, scan)
            chapters.append(len(marks))
            _write(out_dir, os.path.join("CLIPINF", f"{name}.clpi"),
                   clip_info.clpi(scan, video_format, frame_rate, audio, pg))
            item = (name, marks[0], scan.end_pts // 2, video_format, frame_rate, audio, pg,
                    False, 0)
            _write(out_dir, os.path.join("PLAYLIST", f"{name}.mpls"),
                   playlist.mpls([item], [(0, m) for m in marks]))
            dest = os.path.join(out_dir, "BDMV", "STREAM", f"{name}.m2ts")
            if os.path.abspath(t.clip) != os.path.abspath(dest):
                (shutil.move if move else shutil.copyfile)(t.clip, dest)
            objects.append([hdmv.play_pl(n)] + self._end(t, n, play_all, links))
        for k, m in enumerate(self.menus, n_titles + 1):
            self._write_menu(out_dir, k, m, links, fast)
            objects.append([hdmv.play_pl(k)])     # (its last picture held: a still)
        # first play and the Top Menu key: the first menu, or title 1
        objects.append([hdmv.jump_title(n_titles + 1 if self.menus else 1)])
        start = len(objects) - 1
        objects.append([hdmv.jump_title(n_titles + 1 if self.menus else 1)])
        for n, c in chapter_objects:
            t = self.titles[n - 1]
            if c > chapters[n - 1]:
                raise BdmvError(f"chapter:{n}:{c}: title {n} has {chapters[n - 1]} chapters")
            objects.append([hdmv.play_pl_mark(n, c - 1)] + self._end(t, n, play_all, links))
        first = FORMATS[self.titles[0].fps]
        total = n_titles + len(self.menus)
        _write(out_dir, "index.bdmv", hdmv.index_bdmv(
            list(range(total)), start, start + 1, *first,
            interactive=range(n_titles + 1, total + 1)))
        _write(out_dir, "MovieObject.bdmv", hdmv.movie_objects(objects))
        return {"titles": n_titles, "menus": len(self.menus),
                "playlists": [f"{n:05d}.mpls" for n in range(1, total + 1)],
                "chapters": chapters}

    def _end(self, t, n, play_all, links):
        if t.end:
            return list(links[t.end])
        return [hdmv.jump_title(n + 1)] if play_all and n < len(self.titles) else []

    def _write_menu(self, out_dir, k, m, links, fast):
        """Menu `m` as title / playlist / clip k: its buttons' pictures read,
        the IG stream made and encoded with its picture into the clip."""
        name = f"{k:05d}"
        buttons = []
        for b in m.buttons:
            w, h, sel = encode.picture(b.selected)
            if b.x < 0 or b.y < 0 or b.x + w > WIDTH or b.y + h > HEIGHT:
                raise BdmvError(f"menu {m.id!r}: button {b.id!r} ({w} x {h} at {b.x}, {b.y}) "
                                f"is not inside the {WIDTH} x {HEIGHT} frame")
            act = encode.picture(b.activated, (w, h))[2] if b.activated else None
            nor = encode.picture(b.normal, (w, h))[2] if b.normal else None
            buttons.append(igs.Button(b.id, b.x, b.y, w, h, sel, act, nor,
                                      list(links[b.action]) if b.action else [],
                                      dict(b.nav), b.auto))
        video_format, frame_rate = FORMATS[m.fps]
        dest = os.path.join(out_dir, "BDMV", "STREAM", f"{name}.m2ts")
        with tempfile.TemporaryDirectory(prefix="bdmvkit-") as work:
            sup = os.path.join(work, "menu.sup")
            with open(sup, "wb") as f:
                f.write(igs.ig_stream(buttons, frame_rate, default=m.default))
            encode.encode_menu(m.background, sup, dest, m.fps, fast=fast)
        scan = scan_m2ts(dest)
        _write(out_dir, os.path.join("CLIPINF", f"{name}.clpi"),
               clip_info.clpi(scan, video_format, frame_rate, [], [], ig=True))
        item = (name, scan.first_pts // 2, scan.end_pts // 2, video_format, frame_rate, [], [],
                True, 2)
        _write(out_dir, os.path.join("PLAYLIST", f"{name}.mpls"),
               playlist.mpls([item], [(0, scan.first_pts // 2)]))


def _lang(code):
    code = (code or "").lower()
    return code if len(code) == 3 and code.isalpha() else lang3(code)
