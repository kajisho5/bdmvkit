"""What a disc holds and where each thing leads: the model nav.py writes.

A Program is the disc's titles (encoded clips with chapters, sound and
subtitle tracks), its playlists (titles or ranges of their chapters played
one after another, in order, at random or shuffled), its menus (clips that
carry their buttons as an IG stream, igs.ig_stream) and where everything
goes: actions.

Actions are strings:

    title:<id>            play a title from its start
    chapter:<id>:<n>      play a title from its chapter n (1-based)
    playlist:<id>         play a playlist
    playall               play every title, in order
    menu:<id>             open a menu
    menu:<id>:<button>    open a menu with that button selected
    lastmenu              the menu shown last
    resume                go on with the title a menu was opened over
    audio:<n>             switch to sound track n (a button's action)
    subtitle:<n> | off    switch to subtitle track n, or off
    stop                  stop
"""

import dataclasses

from .errors import BdmvError
from .uops import KEYS


def parse_action(s):
    """'menu:x' -> ('menu', 'x', None); 'menu:x:b' -> ('menu', 'x', 'b') (button b
    selected); 'chapter:t:2' -> ('chapter', 't', 2); 'stop';
    'audio:2' -> ('audio', None, 2); 'subtitle:off' -> ('subtitle', None, 0);
    'playall' -> ('playall', None, None); 'playlist:p' -> ('playlist', 'p', None);
    'resume' -> ('resume', None, None); 'lastmenu' -> ('lastmenu', None, None)."""
    if s in ("stop", "playall", "resume", "lastmenu"):
        return (s, None, None)
    kind, _, rest = s.partition(":")
    if kind == "chapter":
        tid, _, n = rest.rpartition(":")
        return ("chapter", tid, int(n))
    if kind in ("audio", "subtitle"):
        return (kind, None, 0 if rest == "off" else int(rest))
    if kind == "menu":
        mid, _, button = rest.partition(":")
        return ("menu", mid, button or None)
    return (kind, rest, None)


@dataclasses.dataclass
class Audio:
    """A sound track as the playlist declares it (the clip carries it with
    PID AUDIO_PID + its index, as encode.encode_clip muxes it)."""
    coding: int                  # formats.CODING_AC3, CODING_LPCM or CODING_DTS
    channels: int = 2
    lang: str = "und"            # ISO 639-2 ("eng")
    default: bool = False        # the disc starts with it (first play)


@dataclasses.dataclass
class Subtitle:
    lang: str = "und"            # ISO 639-2
    default: bool = False        # shown when its title starts (else: subtitles off)


@dataclasses.dataclass
class Title:
    id: str
    clip: str                    # an encoded .m2ts
    fps: tuple = (24000, 1001)
    chapters: list = dataclasses.field(default_factory=lambda: [0.0])   # starts, seconds
    audio: list = dataclasses.field(default_factory=list)              # Audio
    subtitles: list = dataclasses.field(default_factory=list)          # Subtitle
    end: str = None              # action after it (None: stop)
    prohibit: list = dataclasses.field(default_factory=list)           # uops.KEYS names
    popup: bool = False          # its clip carries a pop-up menu (an IG stream)
    hold: bool = False           # each chapter a picture held until Next (a slideshow)


@dataclasses.dataclass
class Button:
    id: str
    action: str = None
    audio: int = None            # switch to this sound track (1-based) first
    subtitle: int = None         # ... and to this subtitle track (0: off)
    transition: str = None       # a clip (Program.transitions key) played before
    override: str = None         # the end action of the title it starts, instead of its own


@dataclasses.dataclass
class Menu:
    id: str
    clip: str                    # its picture and its buttons (IG stream), encoded
    buttons: list                # Button, in the order of the IG stream's buttons
    fps: tuple = None            # (None: the Program's)
    default: str = None          # button selected first (None: the first)
    still: bool = True           # its last picture held; else it plays again
    still_time: int = None       # a still menu that waits this long (whole seconds)
    loop_point: float = None     # where it plays again from (seconds)
    loop: int = None             # played this many times, then `end`
    end: str = None
    music: bool = False          # its clip carries a sound track
    prohibit: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class PlaylistItem:
    title: str
    first: int = 1               # chapters first..last of it (1-based, inclusive)
    last: int = None


@dataclasses.dataclass
class Playlist:
    id: str
    items: list                  # PlaylistItem
    order: str = "sequential"    # "sequential", "random" or "shuffle"
    end: str = None


@dataclasses.dataclass
class Program:
    titles: list
    playlists: list = dataclasses.field(default_factory=list)
    menus: list = dataclasses.field(default_factory=list)
    first_play: str = None       # (None: title 1)
    title_key: str = None        # the Top Menu key (None: the first menu, or title 1)
    fps: tuple = None            # menus' and transitions' rate (None: the first title's)
    video: str = "1080"          # "1080" or "720"
    transitions: dict = dataclasses.field(default_factory=dict)   # name -> encoded .m2ts

    def title(self, tid):
        return next(t for t in self.titles if t.id == tid)

    def menu(self, mid):
        return next(m for m in self.menus if m.id == mid)

    def playlist(self, pid):
        return next(p for p in self.playlists if p.id == pid)

    def actions(self):
        """Every action of the disc: first play, Title key, buttons and their
        overrides, menu, title and playlist end actions."""
        out = [self.first_play, self.title_key]
        for m in self.menus:
            out += [b.action for b in m.buttons] + [b.override for b in m.buttons]
            if m.loop is not None:
                out.append(m.end)
        out += [t.end for t in self.titles] + [p.end for p in self.playlists]
        return [a for a in out if a]

    @property
    def uses_playall(self):
        return "playall" in self.actions()

    @property
    def overrides(self):
        """End-action overrides buttons use, in a fixed order (1-based numbers
        in the override register)."""
        return sorted({b.override for m in self.menus for b in m.buttons if b.override})

    @property
    def link_transitions(self):
        """The transitions the disc plays: one per (clip, action, override,
        audio, subtitle) of a button, in menu and button order."""
        out = []
        for m in self.menus:
            for b in m.buttons:
                if b.transition and transition_key(b) not in out:
                    out.append(transition_key(b))
        return out

    @property
    def entry_buttons(self):
        """{menu id: {button ids}} that links open with that button selected."""
        out = {}
        for a in self.actions():
            kind, mid, button = parse_action(a)
            if kind == "menu" and button:
                out.setdefault(mid, set()).add(button)
        return out

    def check(self):
        """BdmvError for what cannot be written: no titles, ids used twice,
        actions that lead nowhere, unknown keys."""
        if not self.titles:
            raise BdmvError("a disc needs at least one title")
        for kind, things in (("title", self.titles), ("menu", self.menus),
                             ("playlist", self.playlists)):
            ids = [x.id for x in things]
            for i in ids:
                if ids.count(i) > 1:
                    raise BdmvError(f"there are two {kind}s {i!r}")
        titles = {t.id: t for t in self.titles}
        menus = {m.id: m for m in self.menus}
        playlists = {p.id for p in self.playlists}
        for a in self.actions():
            kind, ident, n = parse_action(a)
            ok = (kind in ("stop", "playall", "resume", "lastmenu", "audio", "subtitle")
                  or (kind == "title" and ident in titles)
                  or (kind == "chapter" and ident in titles and n >= 1)
                  or (kind == "playlist" and ident in playlists)
                  or (kind == "menu" and ident in menus and
                      (n is None or n in [b.id for b in menus[ident].buttons])))
            if not ok:
                raise BdmvError(f"{a!r} leads nowhere on this disc")
        for p in self.playlists:
            if not p.items:
                raise BdmvError(f"playlist {p.id!r} has no items")
            if p.order not in ("sequential", "random", "shuffle"):
                raise BdmvError(f"playlist {p.id!r}: order {p.order!r}")
            for it in p.items:
                if it.title not in titles:
                    raise BdmvError(f"playlist {p.id!r}: no title {it.title!r}")
        for x in self.titles + self.menus:
            for k in x.prohibit:
                if k not in KEYS:
                    raise BdmvError(f"{x.id!r}: unknown key {k!r} ({', '.join(KEYS)})")
        for m in self.menus:
            for b in m.buttons:
                if b.transition and b.transition not in self.transitions:
                    raise BdmvError(f"menu {m.id!r}, button {b.id!r}: no transition "
                                    f"{b.transition!r}")


def transition_key(button):
    """What a button with a transition does: buttons that play the same clip
    and then do the same share one transition on the disc."""
    return (button.transition, button.action, button.override, button.audio, button.subtitle)
