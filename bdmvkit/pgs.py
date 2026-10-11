"""Blu-ray subtitles: cues -> a PGS (Presentation Graphics) stream (.sup).

A text cue is a picture of white text with a black outline on a
transparent HD frame (RGBA, drawn by the caller); indexed() keeps 64
colours of it: 8 steps from the outline to the fill colour, each at 8
levels of opacity, so edges stay smooth, and palette() gives them in the
cue's own fill and outline colours. A picture cue keeps its own colours
(picture_palette). Palettes are BT.709 YCbCr, as Blu-ray HD pictures are.

A cue becomes a display set at its start (presentation composition, window,
palette and the run-length coded object) and an empty composition at its
end, which clears it. The stream begins with an empty composition at time 0
so that ffmpeg, which starts every input at 0, keeps the cue times.
"""

import re
import struct


PCS, WDS, PDS, ODS, END = 0x16, 0x17, 0x14, 0x15, 0x80
EPOCH_START, NORMAL = 0x80, 0x00
STEPS = 8                       # fill/outline mix steps and opacity levels
MAX_SEGMENT = 65535
MIN_GAP = 0.2                   # seconds between two cues the decoder needs (about 5 frames)

# per byte value: the step (0-7) of a lightness or an opacity
_STEP = bytes(min(STEPS - 1, v * STEPS // 256) for v in range(256))
_VISIBLE = bytes(1 if a >= 16 else 0 for a in range(256))


def _rgb(value):
    """'#RRGGBB' -> (r, g, b)."""
    s = value.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def ycbcr(rgb):
    """BT.709, studio range (what HD Blu-ray players expect)."""
    r, g, b = (c / 255 for c in rgb)
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    cb, cr = (b - y) / 1.8556, (r - y) / 1.5748
    return (round(16 + 219 * y), round(128 + 224 * cb), round(128 + 224 * cr))


def palette(fill, outline):
    """Entries (index, Y, Cr, Cb, alpha): 0 transparent, then 1 + 8 * mix +
    opacity, mix 0 = outline .. 7 = fill."""
    f, o = _rgb(fill), _rgb(outline)
    out = [(0, 16, 128, 128, 0)]
    for m in range(STEPS):
        t = m / (STEPS - 1)
        rgb = tuple(round(oc + (fc - oc) * t) for fc, oc in zip(f, o))
        y, cb, cr = ycbcr(rgb)
        for a in range(STEPS):
            alpha = round((a + 1) * 255 / STEPS)
            out.append((1 + STEPS * m + a, y, cr, cb, alpha))
    return out


def picture_palette(colours):
    """Entries for a picture's own colours [(r, g, b, a)]: index k for the
    k-th (0 transparent)."""
    return [(0, 16, 128, 128, 0)] + [(k, *_ycrcb(c[:3]), c[3])
                                     for k, c in enumerate(colours, 1)]


def _ycrcb(rgb):
    y, cb, cr = ycbcr(rgb)
    return y, cr, cb


def indexed(rgba, W, H):
    """RGBA (white text, black outline) -> (index bytes, w, h, x, y) cropped
    to what is visible, or None for an empty picture. Runs at C speed: the
    two steps are combined as big integers (no byte overflows into the next)."""
    alpha = rgba[3::4]
    vis = alpha.translate(_VISIBLE)
    first, last = vis.find(1), vis.rfind(1)
    if first < 0:
        return None
    y0, y1 = first // W, last // W
    x0, x1 = W, -1
    for yy in range(y0, y1 + 1):
        row = vis[yy * W:(yy + 1) * W]
        a, b = row.find(1), row.rfind(1)
        if a >= 0:
            x0, x1 = min(x0, a), max(x1, b)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    rows_l, rows_a, rows_v = [], [], []
    red = rgba[0::4]
    for yy in range(y0, y1 + 1):
        s = slice(yy * W + x0, yy * W + x1 + 1)
        v = vis[s]
        rows_v.append(v)
        # invisible pixels get step 0 in both, and no +1 below
        rows_l.append(_mask(red[s].translate(_STEP), v))
        rows_a.append(_mask(alpha[s].translate(_STEP), v))
    n = w * h
    lum = int.from_bytes(b"".join(rows_l), "big")
    opa = int.from_bytes(b"".join(rows_a), "big")
    one = int.from_bytes(b"".join(rows_v), "big")
    idx = (lum * STEPS + opa + one).to_bytes(n, "big")
    return idx, w, h, x0, y0


def _mask(steps, visible):
    """Steps where visible, 0 elsewhere (multiplying by the 0/1 mask)."""
    n = len(steps)
    if not n:
        return steps
    s = int.from_bytes(steps, "big")
    v = int.from_bytes(visible, "big")
    # visible bytes are 0 or 1; spread each to 0x00 / 0xFF and AND
    return (s & (v * 0xFF)).to_bytes(n, "big")


_RUN = re.compile(rb"(.)\1*", re.S)


def rle(idx, w, h):
    """PGS run-length coding, line by line (colour 0 = transparent)."""
    out = bytearray()
    for y in range(h):
        row = idx[y * w:(y + 1) * w]
        for m in _RUN.finditer(row):
            c, n = m.group()[0], m.end() - m.start()
            while n:
                k = min(n, 16383)
                if c == 0:
                    out += bytes([0, k]) if k < 64 else bytes([0, 0x40 | k >> 8, k & 0xFF])
                elif k < 3:
                    out += bytes([c]) * k
                elif k < 64:
                    out += bytes([0, 0x80 | k, c])
                else:
                    out += bytes([0, 0xC0 | k >> 8, k & 0xFF, c])
                n -= k
        out += b"\0\0"
    return bytes(out)


def _segment(kind, pts, data):
    return b"PG" + struct.pack(">IIBH", pts & 0xFFFFFFFF, 0, kind, len(data)) + data


def _pcs(size, number, state, objects):
    W, H = size
    data = struct.pack(">HHBHBBBB", W, H, 0x10, number & 0xFFFF, state, 0, 0, len(objects))
    for x, y in objects:
        data += struct.pack(">HBBHH", 0, 0, 0, x, y)
    return data


def display_set(pts, size, number, pic, entries):
    """Show `pic` (index bytes, w, h, x, y) from pts (90 kHz)."""
    idx, w, h, x, y = pic
    out = _segment(PCS, pts, _pcs(size, number, EPOCH_START, [(x, y)]))
    out += _segment(WDS, pts, struct.pack(">BBHHHH", 1, 0, x, y, w, h))
    out += _segment(PDS, pts, bytes([0, 0]) + b"".join(bytes(e) for e in entries))
    coded = rle(idx, w, h)
    data = (len(coded) + 4).to_bytes(3, "big") + struct.pack(">HH", w, h) + coded
    first = MAX_SEGMENT - 4
    chunks = [data[:first]] + [data[i:i + MAX_SEGMENT - 4]
                               for i in range(first, len(data), MAX_SEGMENT - 4)]
    for k, chunk in enumerate(chunks):
        flags = (0x80 if k == 0 else 0) | (0x40 if k == len(chunks) - 1 else 0)
        out += _segment(ODS, pts, struct.pack(">HBB", 0, 0, flags) + chunk)
    return out + _segment(END, pts, b"")


def clear_set(pts, size, number, window):
    out = _segment(PCS, pts, _pcs(size, number, NORMAL if window else EPOCH_START, []))
    if window:
        x, y, w, h = window
        out += _segment(WDS, pts, struct.pack(">BBHHHH", 1, 0, x, y, w, h))
    else:
        out += _segment(WDS, pts, b"\0")             # no windows
    return out + _segment(END, pts, b"")


def timeline(cues):
    """(start, end) per cue, each ending MIN_GAP before the next one starts so
    the player has time to decode it; cues left with no time are dropped."""
    out = []
    for i, c in enumerate(cues):
        end = c.end
        if i + 1 < len(cues):
            end = min(end, round(cues[i + 1].start - MIN_GAP, 6))
        out.append((c.start, end) if end > c.start else None)
    return out


def write_sup(path, pictures, size):
    """pictures: [(start s, end s, pic or None, palette entries)]."""
    data = clear_set(0, size, 0, None)
    n = 1
    for start, end, pic, entries in pictures:
        if pic is None:
            continue
        a, b = round(start * 90000), round(end * 90000)
        data += display_set(a, size, n, pic, entries)
        data += clear_set(b, size, n + 1, (pic[3], pic[4], pic[1], pic[2]))
        n += 2
    with open(path, "wb") as f:
        f.write(data)
    return path


def decode(data):
    """Read a .sup back: [(pts, [(x, y, w, h, index bytes)], palette)] per
    composition. For tests and checks."""
    out, pos, pal, objs, wins, comp, buf = [], 0, {}, [], {}, None, b""
    while pos < len(data):
        assert data[pos:pos + 2] == b"PG", "segment magic"
        pts, _, kind, size = struct.unpack(">IIBH", data[pos + 2:pos + 13])
        body = data[pos + 13:pos + 13 + size]
        pos += 13 + size
        if kind == PCS:
            n = body[10]
            comp = (pts, [struct.unpack(">HBBHH", body[11 + 8 * i:19 + 8 * i])[3:]
                          for i in range(n)])
            objs = []
        elif kind == PDS:
            pal = {body[i]: tuple(body[i + 1:i + 5]) for i in range(2, len(body), 5)}
        elif kind == ODS:
            flags = body[3]
            buf = (body[4:] if flags & 0x80 else buf + body[4:])
            if flags & 0x40:
                w, h = struct.unpack(">HH", buf[3:7])
                objs.append((w, h, unrle(buf[7:], w, h)))
        elif kind == END:
            pics = [(x, y, w, h, px) for (x, y), (w, h, px) in zip(comp[1], objs)]
            out.append((comp[0], pics, dict(pal)))
    return out


def unrle(data, w, h):
    out, i, row = bytearray(), 0, 0
    while i < len(data) and row < h:
        b = data[i]
        i += 1
        if b:
            out.append(b)
            continue
        f = data[i]
        i += 1
        if f == 0:
            row += 1
            continue
        n = f & 0x3F
        if f & 0x40:
            n = n << 8 | data[i]
            i += 1
        c = 0
        if f & 0x80:
            c = data[i]
            i += 1
        out += bytes([c]) * n
    assert len(out) == w * h, (len(out), w * h)
    return bytes(out)
