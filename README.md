# bdmvkit

**Blu-ray (BDMV) authoring in pure Python.** bdmvkit writes the files a
Blu-ray player navigates by:

* playlists with chapter marks (`.mpls`);
* clip information with the entry-point map players seek with (`.clpi`);
* `index.bdmv` and `MovieObject.bdmv` with HDMV navigation commands;
* PGS subtitle streams (`.sup`).

It also encodes the clips with ffmpeg and x264, using the Blu-ray settings.
There are no dependencies beyond the standard library, and ffmpeg is needed
only to encode.

日本語の説明は [README.ja.md](README.ja.md) にあります。

**Status: 0.1.** Titles with chapters, sound and subtitle tracks, played in
order. HDMV menus (Interactive Graphics: buttons, pop-up menus) come next.
They already work in [oncemore](https://github.com/kajisho5/oncemore), where
this code comes from, and are being moved here.

## Why

Open-source Blu-ray tools mux streams into a BDMV folder (tsMuxer, for one),
but they stop short of the navigation layer: menus, movie objects, playlists
and commands. bdmvkit writes that layer itself, and is tested by playing
every disc back with libbluray.

## Install

```sh
pip install git+https://github.com/kajisho5/bdmvkit
```

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

```sh
bdmvkit encode feature.mov feature.m2ts --chapters 0,300,600
bdmvkit build disc.json out
```

`disc.json` looks like this:

```json
{"titles": [{"clip": "feature.m2ts", "fps": "24000/1001", "chapters": [0, 300, 600],
             "audio": [["ac3", 2, "en"]], "subtitles": ["ja"]}],
 "play_all": true}
```

How the disc is laid out:

* Frame rates are 23.976 (1080p), 25 and 29.97. The last two are coded as
  progressive frames in a 1080i stream, as the format asks.
* Sound is AC-3, LPCM or DTS.
* Subtitles are PGS streams muxed into the clip. `pgs.write_sup` makes them
  from pictures, and `encode_clip(..., sups=[...])` muxes them in.
* First play and the Top Menu key start title 1.

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
  order.

The files' fixed bytes are checked as well.

## License

GNU Lesser General Public License, version 3 or later. See
[COPYING.LESSER](COPYING.LESSER) and [COPYING](COPYING). You may use
bdmvkit in programs under any license. Changes to bdmvkit itself stay under
the LGPL.
