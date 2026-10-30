<p><img src="docs/images/logo/lockup-dark.svg" alt="bdmvkit" height="56"></p>

# bdmvkit

**Blu-ray (BDMV) authoring in pure Python.** bdmvkit writes the files a
Blu-ray player navigates by:

* playlists with chapter marks (`.mpls`);
* clip information with the entry-point map players seek with (`.clpi`);
* `index.bdmv` and `MovieObject.bdmv` with HDMV navigation commands;
* menus: Interactive Graphics streams with buttons, the arrow keys between
  them and the commands they run;
* PGS subtitle streams (`.sup`).

It also encodes the clips with ffmpeg and x264, using the Blu-ray settings.
There are no dependencies beyond the standard library, and ffmpeg is needed
only to encode.

日本語の説明は [README.ja.md](README.ja.md) にあります。

**Status: 0.7.** Titles with chapters, sound and subtitle tracks;
playlists (in order, at random or shuffled) and play all; menus whose
buttons start titles, chapters, playlists and other menus, switch sound and
subtitle tracks, or open a menu on a chosen button; loop counts, end-action
overrides, link transitions, remote keys a title turns off, and 720p. This
navigation is the one [oncemore](https://github.com/kajisho5/oncemore)
writes, byte for byte. 0.4 adds pop-up menus over a playing title, 0.5
menus with motion or music, 0.6 button streams for 720p menus, 0.7 DTS-HD
sound tracks.

## Why

Open-source Blu-ray tools mux streams into a BDMV folder (tsMuxer, for one),
but they stop short of the navigation layer: menus, movie objects, playlists
and commands. bdmvkit writes that layer itself, and is tested by playing
every disc back with libbluray.

## Install

```sh
pip install bdmvkit
```

A release is made by the version: when the version in `pyproject.toml`
(and `bdmvkit/__init__.py`) reaches `main` without a tag of its own,
`.github/workflows/release.yml` runs the tests, builds the package, makes
the GitHub release with its tag and publishes to PyPI (trusted publishing,
environment `pypi`). Merging the version bump is all it takes.

## Use

```python
from bdmvkit import Disc
from bdmvkit.encode import encode_clip

encode_clip("feature.mov", "feature.m2ts", chapters=[0, 300, 600])   # key frames at the chapters
encode_clip("extras.mp4", "extras.m2ts", fps=(25, 1))

disc = Disc()
disc.add_title("feature.m2ts", chapters=[0, 300, 600], audio=[("ac3", 2, "en")])
disc.add_title("extras.m2ts", fps=(25, 1))
disc.write("out")                       # out/BDMV/...
```

A clip can carry several sound tracks, each from the video itself or from
another file; track k is the title's audio track k (silence when a file has
no sound, and sound shorter than the picture is made up with silence):

```python
from bdmvkit.encode import AudioTrack

encode_clip("feature.mov", "feature.m2ts", audio=[
    AudioTrack(),                                   # the video's own sound, AC-3
    AudioTrack("commentary.wav", "lpcm"),           # another file, LPCM
    AudioTrack("feature.mov", "ac3", 6, stream=1),  # its second sound stream, 5.1
])
disc.add_title("feature.m2ts", audio=[("ac3", 2, "en"), ("lpcm", 2, "en"), ("ac3", 6, "ja")])
```

`Disc.write` checks that every track a title declares is in its clip.

DTS copied with its extensions is declared as what it is: `"dtshd"` (DTS-HD
High Resolution Audio) or `"dtshd_ma"` (DTS-HD Master Audio), with its
sampling rate when it is above 48 kHz (`("dtshd_ma", 8, "en", 96000)`;
LPCM may run at 96 or 192 kHz too). ffmpeg marks a DTS stream in the clip by
its channels, not by its extensions, so `Disc.write` marks each DTS track
with the type the title declares, in the copy it puts on the disc:

```python
encode_clip("feature.mkv", "feature.m2ts", audio=[AudioTrack("feature.mkv", "copy", 8)])
disc.add_title("feature.m2ts", audio=[("dtshd_ma", 8, "en")])
```

A menu is a picture and its buttons. Each button is a picture of how it
looks when selected (and, if given, when activated and before it is
selected), placed on the 1920 x 1080 menu, and a link:

```python
from bdmvkit import Disc, MenuButton

disc = Disc()
disc.add_title("feature.m2ts", chapters=[0, 300, 600], end="menu:main")
disc.add_menu("main", "menu.png", [
    MenuButton("play", 160, 700, "play-lit.png", "play-on.png", action="title:1"),
    MenuButton("scene2", 160, 800, "scene2-lit.png", action="chapter:1:2"),
])
disc.write("out")
```

A button's `action`, a title's `end` and the disc's first play are
actions: `title:<n>`, `chapter:<n>:<c>`, `playlist:<id>`, `playall`,
`menu:<id>` (or `menu:<id>:<button>`, that button selected), `lastmenu`,
`resume`, `audio:<n>`, `subtitle:<n>` or `subtitle:off`, and `stop`. The
arrow keys go to the nearest button that way unless a button's `nav` says
(`{"down": "scene2"}`). `bdmvkit.igs` makes the button stream on its own,
for other tools: `igs.ig_stream(buttons, frame_rate, size=(1280, 720))`
places the buttons on a 720p menu.

```python
disc = Disc(title_key="menu:main")
a = disc.add_title("feature.m2ts", chapters=[0, 300], audio=[("ac3", 6, "en"), ("ac3", 6, "ja")],
                   subtitles=["en", "ja"], default_subtitle=1, end="lastmenu")
n = disc.add_title("notice.m2ts", prohibit=["next", "fast_forward", "menu"], end="title:1")
disc.add_playlist("both", [n, (a, 2, None)], order="shuffle", end="menu:main")
disc.add_menu("main", "menu.png", [
    MenuButton("play", 160, 700, "play.png", action="title:2"),          # the notice first
    MenuButton("ja", 160, 800, "ja.png", action="title:1", audio=2, subtitle=0),
    MenuButton("both", 160, 900, "both.png", action="playlist:both"),
], loop=3, end="playall", seconds=10)
```

A menu's background may be a video, and a menu may have music. Such a menu
plays again when it ends, from `loop_point` (seconds) the second time
round; it lasts as long as its video, else its music, unless `seconds`
says:

```python
disc.add_menu("main", "loop.mp4", buttons, music="theme.wav", loop_point=2.0)
```

A title can have a pop-up menu: buttons over its picture, opened with the
remote's Pop-up Menu key. Their pictures are placed on the 1920 x 1080 frame
as a menu's are; a button that only switches the sound or subtitle track
closes the menu.

```python
disc.add_popup(a, [
    MenuButton("scenes", 160, 900, "scenes.png", "scenes-on.png", "scenes-off.png",
               action="menu:main"),
    MenuButton("ja", 560, 900, "ja.png", normal="ja-off.png", action="audio:2"),
])
```

Underneath, `bdmvkit.program` describes a disc made of encoded clips
(titles, playlists, menu clips that carry their buttons, transitions) and
`bdmvkit.nav.write_program` writes it; `nav.Navigation` gives the commands a
menu's buttons run, for tools that make their own IG streams.

```sh
bdmvkit encode feature.mov feature.m2ts --chapters 0,300,600
bdmvkit build disc.json out
bdmvkit contract --json      # machine-readable contract (AI Video Production OS registry)
```

`disc.json` looks like this:

```json
{"titles": [{"clip": "feature.m2ts", "fps": "24000/1001", "chapters": [0, 300, 600],
             "audio": [["ac3", 2, "en"]], "subtitles": ["ja"], "end": "menu:main"}],
 "menus": [{"id": "main", "background": "menu.png",
            "buttons": [{"id": "play", "x": 160, "y": 700, "selected": "play-lit.png",
                         "action": "title:1"}]}],
 "play_all": true}
```

How the disc is laid out:

* Frame rates are 23.976 (1080p), 25 and 29.97. The last two are coded as
  progressive frames in a 1080i stream, as the format asks. A program can
  also be 720p (23.976, 50, 59.94; 25 and 29.97 go on at twice their rate);
  `encode_clip` makes 1080 clips.
* Sound is AC-3, LPCM, DTS, DTS-HD High Resolution Audio or DTS-HD Master
  Audio (a DTS-HD track above 48 kHz is marked as such over its 48 kHz core).
* Subtitles are PGS streams muxed into the clip. `pgs.write_sup` makes them
  from pictures, and `encode_clip(..., sups=[...])` muxes them in.
* First play and the Top Menu key open the first menu, or start title 1
  when there is none (`Disc(first_play=..., title_key=...)` choose).
* Each title, playlist, play all and menu is a Blu-ray title, in that
  order; random and shuffled playlists play a playlist file per item, picked
  with the player's random number command. The general registers 1 to 8
  hold the last menu, the button a link selects, a menu's loop count, an
  end-action override, a stream choice, and a random playlist's state
  (`nav.py`).
* A menu is an interactive title after the titles: its picture held as a
  still, with its buttons as an Interactive Graphics stream in its clip.
  The menus are encoded when the disc is written (ffmpeg).

To make a disc image of the folder, use
[udfkit](https://github.com/kajisho5/udfkit) (UDF 2.50):
`udfkit bluray out disc.iso --label MY_DISC`.

## Tests

```sh
python -m unittest discover -s tests -t .
```

The tests encode real clips, write a disc, and read it back with
**libbluray**, the library VLC, mpv and Kodi play Blu-ray with. They check:

* the titles and their lengths;
* the chapter positions;
* the video, audio and subtitle streams and their languages;
* that running the disc from first play reaches the titles and chapters in
  order;
* that a menu's buttons, chosen and pressed with the remote's keys, start
  the titles, chapters, playlists and menus they link to, that a shuffled
  playlist plays each item once, and that a menu with a loop count goes on
  by itself;
* that a menu with a video and music plays again from its loop point, and
  that one with a loop count goes on by itself after playing that often;
* that a pop-up menu opens over a playing title with the Pop-up Menu key and
  its buttons start another title or a chapter;
* the commands every kind of action, title, playlist and menu turns into.

The files' fixed bytes are checked as well.

## Support

bdmvkit is free and stays free. If it saves you time, you can support its
development through [GitHub Sponsors](https://github.com/sponsors/kajisho5)
(the **Sponsor** button at the top of this repository). Bug reports help just
as much: [Issues](https://github.com/kajisho5/bdmvkit/issues).

The logo, colours and writing rules: [docs/DESIGN.md](docs/DESIGN.md).

## License

GNU Lesser General Public License, version 3 or later. See
[COPYING.LESSER](COPYING.LESSER) and [COPYING](COPYING). You may use
bdmvkit in programs under any license. Changes to bdmvkit itself stay under
the LGPL.
