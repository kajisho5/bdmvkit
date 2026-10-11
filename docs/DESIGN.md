# Design system

bdmvkit is a library, so its design is its identity and its words: the logo
and colours it shares with the oncemore family, how its documents and
messages are written, and the images that show it. The family's full
interface design system is oncemore's
([docs/DESIGN.md](https://github.com/kajisho5/oncemore/blob/main/docs/DESIGN.md));
this one is the part a library needs.

## The family

oncemore and its libraries, [udfkit](https://github.com/kajisho5/udfkit),
[bdmvkit](https://github.com/kajisho5/bdmvkit),
[dvdcc](https://github.com/kajisho5/dvdcc) and
[vtskit](https://github.com/kajisho5/vtskit), look alike on purpose: the same
colours, the same typeface, and marks drawn on the same disc ring, each with
what that tool does inside it.

| | Mark |
|---|---|
| oncemore | the ring is a loop arrow: play it once more |
| udfkit | a folder: the files and folders it lays out on the disc |
| bdmvkit | a play button: titles and menus that play |
| dvdcc | a speech bubble with two caption lines |
| vtskit | a path that branches in two: the navigation it writes |

## Colours

| Token | Value | Use |
|---|---|---|
| Highlight | `#ffd400` | the mark; key words in headlines; the frame of a code card. The DVD highlight yellow. |
| Ink | `#181b22` | the ground of everything: tiles, lockups, previews |
| Paper | `#f2f2f2` | the wordmark and headlines on Ink |
| Muted | `#a9adb7` | the sentence under a headline |
| Faint | `#8a8f9e` | small print (the family line, comments in code) |
| Line | `#3a3f4a` | outlines of pills; never text |
| Code ground | `#0f1116` | inside a code card |

Contrast (WCAG 2): Highlight on Ink 12.0:1, Paper on Ink 15.4:1, Muted on
Ink 7.7:1, Faint on Ink 5.3:1 (and 5.9:1 on the code ground). Highlight on
white is 1.4:1, so **the mark is never put on a light ground**; there, use
`icon.svg`, which carries its own Ink tile, and the Ink wordmark.

## Type

* **Outfit** (SIL Open Font License): SemiBold for the wordmark (lower case,
  -0.01 em tracking, converted to outlines, so no font is needed to show
  it); Bold for headlines; Medium for sentences and pills.
* **Noto Sans CJK JP** for Japanese headlines and sentences.
* **DejaVu Sans Mono** (or any monospace) in code cards.
* The library itself never loads a font; these are for its images.

## Logo

* `docs/images/logo/mark.svg`: the mark, on a 100 x 100 grid: the ring
  (radius 34, stroke 12) and a play button: titles and menus that play.
* `icon.svg`: the mark on its Ink tile (rounded square), for avatars and
  light grounds.
* `lockup-dark.svg`: the mark and the wordmark on Ink, for the top of the
  README and anywhere the name is shown with the mark.
* `wordmark-light.svg`, `wordmark-ink.svg`: the name alone, Paper (on dark
  grounds) or Ink (on light ones).
* `make_logo.py` draws them all from geometry and the Outfit SemiBold font
  file (`pip install fonttools`; only this script needs it).
* **Rules:** clear space of at least the height of the wordmark's "o"
  around it; the mark at 16 px or more, the lockup at 96 px wide or more;
  only the colours above, no gradients, shadows or outlines; the mark is
  not rotated, recoloured or redrawn.

## Social preview

`docs/images/social-preview.png` (English) and `social-preview-ja.png`
(Japanese), 1280 x 640, made from `social-preview.html` and
`social-preview-ja.html`:

* left: the lockup, a headline of two lines at most with its key words in
  Highlight, one sentence in Muted, and three pills (the format, what is
  special, the license);
* right: a code card framed in Highlight that runs off the edge, with real
  commands or code from the README (never made-up output);
* bottom right: "a library of oncemore" in Faint.

To render them, put Outfit's TTF files (500, 600, 700) in
`docs/images/fonts/` (not committed) and screenshot the page at 1280 x 640
(any browser; the maintainers use Playwright's Chromium). GitHub takes the
image only through the repository's **Settings > General > Social
preview**; there is no API for it.

## Writing

* The README comes in English and Japanese (`README.ja.md`) with the same
  sections in the same order: what it does, why, install, use, how the
  output is laid out, tests, support, license. A change to one is made to
  the other.
* Plain words and short sentences. Every claim can be checked: a test, a
  format document or a command shows it.
* Examples are real: they run as written, and their output is what the
  program prints.
* Other projects are named only where bdmvkit works with them or is
  compared with them (libbluray, libdvdnav, ffmpeg, genisoimage ...).

## Messages

What bdmvkit prints follows one pattern, so scripts and people can read it:

* **Results** go to standard output, one line per thing made
  (`out: 2 title(s), 1 menu(s), chapters [3, 1]`).
* **Errors** go to standard error as `bdmvkit: what went wrong`, with a
  second, indented line saying what to do about it when there is one; the
  exit status is 1. Wrong arguments are argparse's (status 2).
* **Notes** that do not stop the work are `bdmvkit: note: ...` on standard
  error.
* Words are plain and say what happened to the user's files, not what the
  code did ("the picture is 1920 x 1080", not "assertion failed").

## Code

* The standard library only at run time; external programs (ffmpeg) only
  where the README says so.
* Each module starts with what it writes and why it is laid out that way.
* Tests read the output back with readers other than the writer: an
  independent parser in the tests, and the libraries players use.

## License

LGPL-3.0-or-later. The logo files are part of the repository and under the
same license; the oncemore family's name and marks identify these projects,
please do not use them for other ones.
