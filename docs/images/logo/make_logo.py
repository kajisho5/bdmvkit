"""Regenerate the bdmvkit logo files (see docs/DESIGN.md, Brand).

The mark is drawn from geometry: a disc (the ring the oncemore family
shares) with a play button: titles and menus that play inside. The wordmark is "bdmvkit" set in Outfit
SemiBold (SIL Open Font License, Google Fonts) and converted to outlines,
so no font is needed to show it. Only this script needs fontTools and the
font file; bdmvkit itself does not:

    pip install fonttools
    python docs/images/logo/make_logo.py path/to/Outfit-SemiBold.ttf

Writes mark.svg, icon.svg, lockup-dark.svg, wordmark-light.svg and
wordmark-ink.svg next to this script.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "bdmvkit"
# the brand colours (the oncemore family's): highlight, ink, paper
HIGHLIGHT, INK, PAPER = "#ffd400", "#181b22", "#f2f2f2"


def svg(w, h, body, title, view=None):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view or f"0 0 {w:g} {h:g}"}" '
            f'width="{w:g}" height="{h:g}" role="img" aria-label="{title}"><title>{title}</title>'
            f'{body}</svg>\n')


def ring():
    """The disc every mark of the family is drawn on, on a 100 x 100 grid."""
    return f'<circle cx="50" cy="50" r="34" fill="none" stroke="{HIGHLIGHT}" stroke-width="12"/>'


def motif():
    """A play button: titles and menus that play."""
    return f'<path d="M42 35 L66 50 L42 65 Z" fill="{HIGHLIGHT}" stroke="{HIGHLIGHT}" stroke-width="4" stroke-linejoin="round"/>'


def mark():
    return ring() + motif()


def wordmark(font_path, size, x0, baseline, track=-0.01):
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    font = TTFont(font_path)
    gs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    s = size / font["head"].unitsPerEm
    x, parts = x0, []
    for ch in NAME:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x, baseline)))
        parts.append(pen.getCommands())
        x += hmtx[g][0] * s + track * size
    return " ".join(parts), x - track * size - x0


def main(font_path):
    def save(name, text):
        with open(os.path.join(HERE, name), "w") as f:
            f.write(text)
    m = mark()
    save("mark.svg", svg(100, 100, m, NAME))
    tile = f'<rect x="100" y="100" width="824" height="824" rx="185" fill="{INK}"/>'
    save("icon.svg", svg(64, 64, tile + f'<g transform="translate(212 212) scale(6)">{m}</g>',
                         NAME, view="100 100 824 824"))
    wm, width = wordmark(font_path, 64, 112, 66)
    w = round(112 + width + 8)
    save("lockup-dark.svg", svg(w, 100, f'<rect width="{w}" height="100" fill="{INK}"/>' + m +
                                f'<path d="{wm}" fill="{PAPER}"/>', NAME))
    for tone, fill in (("light", PAPER), ("ink", INK)):
        wm, width = wordmark(font_path, 96, 0, 96 * 0.78)
        save(f"wordmark-{tone}.svg",
             svg(round(width), 96, f'<path d="{wm}" fill="{fill}"/>', NAME))


if __name__ == "__main__":
    main(sys.argv[1])
