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
import tempfile

from . import encode, hdmv, igs, program
from .errors import BdmvError
from .formats import AUDIO_PID, CODECS, FORMATS, HEIGHT, PG_PID, WIDTH, lang3
from .m2ts import stream_pids
from .program import parse_action
from .nav import DIRS, Navigation, _write, chapter_marks, write_program  # noqa: F401


@dataclasses.dataclass
class Title:
    clip: str                    # an encoded .m2ts
    fps: tuple = (24000, 1001)   # its frame rate: 24000/1001, 25/1 or 30000/1001
    chapters: list = dataclasses.field(default_factory=lambda: [0.0])   # starts, seconds
    audio: list = dataclasses.field(default_factory=lambda: [("ac3", 2, "und")])
    subtitles: list = dataclasses.field(default_factory=list)          # PG tracks: languages
    end: str = None              # the action after it (None: the next title with play_all)
    default_audio: int = None    # the sound track the disc starts with (1-based)
    default_subtitle: int = None  # the subtitle track shown when it starts (None: off)
    prohibit: list = dataclasses.field(default_factory=list)           # uops.KEYS names


@dataclasses.dataclass
class MenuButton:
    id: str
    x: int                       # top-left on the 1920 x 1080 menu
    y: int
    selected: str                # picture files (PNG ...): selected,
    activated: str = None        # activated (default: the selected one),
    normal: str = None           # and before it is selected (default: nothing)
    action: str = None           # where it goes: an action (program.py), e.g. "title:2"
    nav: dict = dataclasses.field(default_factory=dict)    # direction -> button id
    auto: bool = False           # runs as soon as it is selected
    audio: int = None            # switch to this sound track (1-based) first
    subtitle: int = None         # ... and to this subtitle track (0: off)
    override: str = None         # the end action of the title it starts, instead of its own


@dataclasses.dataclass
class Menu:
    id: str
    background: str              # picture (or video) file, fitted into the HD frame
    buttons: list
    fps: tuple = (24000, 1001)
    default: str = None          # the button selected first (default: the first)
    loop: int = None             # held this many times its length, then `end`
    end: str = None
    prohibit: list = dataclasses.field(default_factory=list)
    seconds: float = None        # its clip's length (default: 1, or the video's or music's)
    music: str = None            # sound file played with it
    loop_point: float = None     # where it plays again from (seconds), with motion or music


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


class Disc:
    """first_play: the action the disc starts with (default: the first menu,
    or title 1); title_key: the Top Menu key's (default: the same)."""

    def __init__(self, first_play=None, title_key=None):
        self.titles = []
        self.menus = []
        self.playlists = []
        self.popups = {}                 # title number -> (buttons, default)
        self.first_play = first_play
        self.title_key = title_key

    def add_title(self, clip, fps=(24000, 1001), chapters=(0.0,), audio=(("ac3", 2, "und"),),
                  subtitles=(), end=None, default_audio=None, default_subtitle=None,
                  prohibit=()):
        """Add a title; returns its number (1-based), its id in actions
        ("title:2"). audio: (codec, channels, language) per track, codec
        "ac3", "lpcm" or "dts"; languages are ISO 639-1 ("en") or 639-2
        ("eng") codes. end: the action when it ends (default: the next title
        with play_all). default_audio: the sound track the disc starts with;
        default_subtitle: the subtitle track shown from its start (else
        none); prohibit: remote keys it does not allow (uops.KEYS)."""
        if tuple(fps) not in FORMATS:
            raise BdmvError(f"{fps[0]}/{fps[1]} fps has no Blu-ray format")
        for codec, _, _ in audio:
            if codec not in CODECS:
                raise BdmvError(f"unknown audio codec {codec!r} (ac3, lpcm or dts)")
        if not audio:
            raise BdmvError("a title needs at least one audio track")
        for name, k, n in (("default_audio", default_audio, len(audio)),
                           ("default_subtitle", default_subtitle, len(subtitles))):
            if k is not None and not 1 <= k <= n:
                raise BdmvError(f"{name} {k}: the title has {n} such tracks")
        self.titles.append(Title(clip, tuple(fps), list(chapters) or [0.0], list(audio),
                                 list(subtitles), end, default_audio, default_subtitle,
                                 list(prohibit)))
        return len(self.titles)

    def add_playlist(self, playlist_id, items, order="sequential", end=None):
        """Add a playlist: items (title, first chapter, last chapter), or
        title numbers for whole titles, played one after another
        ("sequential"), picked at random as many times as there are items
        ("random"), or each once in a random order ("shuffle"). It is
        started by "playlist:<id>"."""
        if any(p.id == playlist_id for p in self.playlists):
            raise BdmvError(f"there is a playlist {playlist_id!r} already")
        out = []
        for it in items:
            n, first, last = (it, 1, None) if isinstance(it, int) else tuple(it) + (None,) * \
                (3 - len(it))
            out.append(program.PlaylistItem(str(n), first or 1, last))
        self.playlists.append(program.Playlist(playlist_id, out, order, end))

    def add_menu(self, menu_id, background, buttons, fps=(24000, 1001), default=None, loop=None,
                 end=None, prohibit=(), seconds=None, music=None, loop_point=None):
        """Add a menu: `background` a picture or a video, `buttons`
        MenuButtons, `music` a sound file. The menu's clip (`seconds` long:
        by default 1, or as long as the video, else the music) is made when
        the disc is written (ffmpeg). A still menu holds its last picture;
        one with a video or music plays again, from `loop_point` (seconds)
        the second time round. With `loop`, it does so `loop` times (a
        still one holds its picture for its length each time), then `end`."""
        if tuple(fps) not in FORMATS:
            raise BdmvError(f"{fps[0]}/{fps[1]} fps has no Blu-ray format")
        if any(m.id == menu_id for m in self.menus):
            raise BdmvError(f"there is a menu {menu_id!r} already")
        if not buttons:
            raise BdmvError(f"menu {menu_id!r} needs at least one button")
        if loop_point is not None and loop_point < 0:
            raise BdmvError(f"menu {menu_id!r}: loop point {loop_point} before the start")
        self.menus.append(Menu(menu_id, background, list(buttons), tuple(fps), default, loop,
                               end, list(prohibit), seconds, music, loop_point))

    def add_popup(self, title, buttons, default=None):
        """Give title `title` (its number) a pop-up menu: `buttons`
        (MenuButtons, their pictures placed on the 1920 x 1080 picture over
        the playing title) shown by the remote's Pop-up Menu key. A button
        that switches the sound or subtitle track closes the menu; one that
        goes elsewhere goes there. The menu's IG stream is muxed into the
        title's clip when the disc is written."""
        if not 1 <= title <= len(self.titles):
            raise BdmvError(f"there is no title {title}")
        if not buttons:
            raise BdmvError(f"title {title}: a pop-up menu needs at least one button")
        self.popups[title] = (list(buttons), default)

    def program(self, play_all=True, probe=False):
        """The disc as a program.Program (titles "1", "2" ...; menus with no
        clip yet: write makes them). With `probe`, menu backgrounds are read
        to tell videos from pictures (else they count as pictures)."""
        n_titles = len(self.titles)
        titles = []
        for n, t in enumerate(self.titles, 1):
            end = t.end or (f"title:{n + 1}" if play_all and n < n_titles else None)
            titles.append(program.Title(
                str(n), t.clip, t.fps, list(t.chapters),
                [program.Audio(CODECS[c], ch, _lang(lang), k == t.default_audio)
                 for k, (c, ch, lang) in enumerate(t.audio, 1)],
                [program.Subtitle(_lang(lang), k == t.default_subtitle)
                 for k, lang in enumerate(t.subtitles, 1)], end, list(t.prohibit),
                popup=n in self.popups,
                popup_buttons=[_button(b) for b in self.popups.get(n, ((), None))[0]]))
        menus = []
        for m in self.menus:
            still = not (m.music or (probe and _motion(m)))
            menus.append(program.Menu(
                m.id, None, [_button(b) for b in m.buttons], fps=m.fps, default=m.default,
                still=still,
                still_time=max(1, round(_seconds(m))) if still and m.loop is not None else None,
                loop_point=m.loop_point if not still else None, loop=m.loop, end=m.end,
                music=bool(m.music), prohibit=list(m.prohibit)))
        first_menu = f"menu:{self.menus[0].id}" if self.menus else None
        return program.Program(titles, list(self.playlists), menus,
                               first_play=self.first_play or first_menu,
                               title_key=self.title_key)

    def write(self, out_dir, move=False, play_all=True, fast=False):
        """Write the BDMV folder into `out_dir` (copying the clips into
        BDMV/STREAM, or moving them with `move`; menu clips are encoded,
        quickly with `fast`). Returns {"titles", "menus", "playlists",
        "chapters"}."""
        if not self.titles:
            raise BdmvError("a disc needs at least one title")
        self.program(play_all).check()   # (before any file is read)
        prog = self.program(play_all, probe=True)
        for n, t in enumerate(self.titles, 1):
            _check_streams(n, t)
        nav = Navigation(prog)
        os.makedirs(os.path.join(out_dir, "BDMV", "STREAM"), exist_ok=True)
        for k, (m, pm) in enumerate(zip(self.menus, prog.menus), len(self.titles) + 1):
            pm.clip = os.path.join(out_dir, "BDMV", "STREAM", f"{k:05d}.m2ts")
            self._encode_menu(m, pm, nav, fast)
        for n, (buttons, default) in sorted(self.popups.items()):
            pt = prog.titles[n - 1]
            pt.clip = os.path.join(out_dir, "BDMV", "STREAM", f"{n:05d}.m2ts")
            self._add_popup(self.titles[n - 1], buttons, default, pt, nav)
        out = write_program(prog, out_dir, move=move)
        return {"titles": len(self.titles), "menus": len(self.menus),
                "playlists": out["playlists"], "chapters": out["chapters"]}

    def _encode_menu(self, m, pm, nav, fast):
        """Menu `m`'s clip (pm.clip): its buttons' pictures read, the IG
        stream made with their commands and encoded with its picture."""
        buttons = _ig_buttons(f"menu {m.id!r}", m.buttons, pm.buttons, nav)
        _, frame_rate = FORMATS[m.fps]
        with tempfile.TemporaryDirectory(prefix="bdmvkit-") as work:
            sup = os.path.join(work, "menu.sup")
            with open(sup, "wb") as f:
                f.write(igs.ig_stream(buttons, frame_rate, default=m.default,
                                      follow_selection=nav.follows_selection(m.id)))
            encode.encode_menu(m.background, sup, pm.clip, m.fps, seconds=_seconds(m), fast=fast,
                               motion=_motion(m), music=m.music,
                               keys=[m.loop_point] if m.loop_point else [])


    def _add_popup(self, t, buttons, default, pt, nav):
        """The title's clip with its pop-up menu's IG stream, as pt.clip."""
        _, frame_rate = FORMATS[t.fps]
        ig = _ig_buttons(f"title {pt.id}'s pop-up menu", buttons, pt.popup_buttons, nav,
                         popup=True)
        with tempfile.TemporaryDirectory(prefix="bdmvkit-") as work:
            sup = os.path.join(work, "popup.sup")
            with open(sup, "wb") as f:
                f.write(igs.ig_stream(ig, frame_rate, default=default, popup=True))
            encode.add_ig_stream(t.clip, sup, pt.clip)


def _motion(m):
    """Whether menu m's background is a video (asked once)."""
    if not hasattr(m, "_motion"):
        m._motion = encode.is_video(m.background)
    return m._motion


def _seconds(m):
    if m.seconds is not None:
        return m.seconds
    if _motion(m):
        return encode.media_seconds(m.background)
    return encode.media_seconds(m.music) if m.music else 1.0


def _button(b):
    return program.Button(b.id, b.action, b.audio, b.subtitle, override=b.override)


def _ig_buttons(where, buttons, program_buttons, nav, popup=False):
    """MenuButtons as igs.Buttons: their pictures read, their commands the
    navigation's (in a pop-up menu, a button that only switches streams
    closes the menu too)."""
    out = []
    for b, pb in zip(buttons, program_buttons):
        w, h, sel = encode.picture(b.selected)
        if b.x < 0 or b.y < 0 or b.x + w > WIDTH or b.y + h > HEIGHT:
            raise BdmvError(f"{where}: button {b.id!r} ({w} x {h} at {b.x}, {b.y}) "
                            f"is not inside the {WIDTH} x {HEIGHT} frame")
        act = encode.picture(b.activated, (w, h))[2] if b.activated else None
        nor = encode.picture(b.normal, (w, h))[2] if b.normal else None
        commands = nav.button(pb) if b.action else []
        if popup and b.action and parse_action(b.action)[0] in ("audio", "subtitle"):
            commands.append(hdmv.popup_off())
        out.append(igs.Button(b.id, b.x, b.y, w, h, sel, act, nor, commands, dict(b.nav),
                              b.auto))
    return out


def _lang(code):
    code = (code or "").lower()
    return code if len(code) == 3 and code.isalpha() else lang3(code)
