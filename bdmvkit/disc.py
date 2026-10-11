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
"""

import dataclasses
import os
import shutil

from . import clip as clip_info
from . import hdmv, playlist
from .errors import BdmvError
from .formats import CODECS, FORMATS, lang3
from .m2ts import scan_m2ts

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


def _write(out_dir, rel, data):
    for base in ("BDMV", os.path.join("BDMV", "BACKUP")):
        with open(os.path.join(out_dir, base, rel), "wb") as f:
            f.write(data)


class Disc:
    def __init__(self):
        self.titles = []

    def add_title(self, clip, fps=(24000, 1001), chapters=(0.0,), audio=(("ac3", 2, "und"),),
                  subtitles=()):
        """Add a title; returns its number (1-based). audio: (codec, channels,
        language) per track, codec "ac3", "lpcm" or "dts"; languages are ISO
        639-1 ("en") or 639-2 ("eng") codes."""
        if tuple(fps) not in FORMATS:
            raise BdmvError(f"{fps[0]}/{fps[1]} fps has no Blu-ray format")
        for codec, _, _ in audio:
            if codec not in CODECS:
                raise BdmvError(f"unknown audio codec {codec!r} (ac3, lpcm or dts)")
        if not audio:
            raise BdmvError("a title needs at least one audio track")
        self.titles.append(Title(clip, tuple(fps), list(chapters) or [0.0], list(audio),
                                 list(subtitles)))
        return len(self.titles)

    def write(self, out_dir, move=False, play_all=True):
        """Write the BDMV folder into `out_dir` (copying the clips into
        BDMV/STREAM, or moving them with `move`). Returns {"titles",
        "playlists", "chapters"}."""
        if not self.titles:
            raise BdmvError("a disc needs at least one title")
        for d in DIRS:
            os.makedirs(os.path.join(out_dir, d), exist_ok=True)
        objects, chapters = [], []
        n_titles = len(self.titles)
        for n, t in enumerate(self.titles, 1):
            name = f"{n:05d}"
            scan = scan_m2ts(t.clip)
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
            cmds = [hdmv.play_pl(n)]               # (playlist n is 0000n.mpls)
            if play_all and n < n_titles:
                cmds.append(hdmv.jump_title(n + 1))
            objects.append(cmds)
        # first play and the Top Menu key: title 1
        objects.append([hdmv.jump_title(1)])
        start = len(objects) - 1
        first = FORMATS[self.titles[0].fps]
        _write(out_dir, "index.bdmv", hdmv.index_bdmv(list(range(n_titles)), start, start, *first))
        _write(out_dir, "MovieObject.bdmv", hdmv.movie_objects(objects))
        return {"titles": n_titles, "playlists": [f"{n:05d}.mpls" for n in range(1, n_titles + 1)],
                "chapters": chapters}


def _lang(code):
    code = (code or "").lower()
    return code if len(code) == 3 and code.isalpha() else lang3(code)
