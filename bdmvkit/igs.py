"""Interactive Graphics (IG) streams: a menu's buttons.

A menu on a Blu-ray is a clip (its picture) carrying an IG stream: one
interactive composition with a page of buttons, each with a picture for
its normal, selected and activated states, the buttons it moves to with
the arrow keys, and the navigation commands it runs when activated.

    buttons = [Button("play", 200, 600, selected=rgba, activated=rgba, w=400, h=80,
                      commands=[hdmv.jump_title(1)])]
    data = ig_stream(buttons, frame_rate=1)      # write it as a .sup

The state pictures are RGBA (straight alpha) of the button's size; they
share one palette of up to 255 colours (quantize). Without a normal
picture a button shows nothing until it is selected (the highlight
is drawn over the menu's own picture). A pop-up composition (`popup`)
is shown by the remote's Pop-up key over a title instead of a menu clip.

ffmpeg muxes an IG stream given as a .sup like a subtitle stream; the
clip's PMT is then corrected with patch_ig_stream_type.
"""

import dataclasses
import struct

from . import pgs
from .errors import BdmvError
from .formats import CODING_IG, HEIGHT, IG_PID, PMT_PID, WIDTH

ICS, PDS, ODS, END = 0x18, 0x14, 0x15, 0x80
NO_OBJECT = 0xFFFF
DIRECTIONS = ("up", "down", "left", "right")


@dataclasses.dataclass
class Button:
    id: str
    x: int                      # top-left on the frame (1920 x 1080, or 1280 x 720)
    y: int
    w: int
    h: int
    selected: bytes             # RGBA, w x h
    activated: bytes = None     # (default: the selected picture)
    normal: bytes = None        # (default: nothing until selected)
    commands: list = dataclasses.field(default_factory=list)   # 12-byte commands
    nav: dict = dataclasses.field(default_factory=dict)        # direction -> button id
    auto: bool = False          # runs as soon as it is selected


def quantize(images):
    """RGBA pictures -> (palette [(r, g, b, a)] for indices 1.., index
    pictures) with at most 255 colours; fully transparent pixels are index
    0. Fewer bits per channel are kept until the colours fit; past that the
    rarest go to their nearest kept colour."""
    for bits in (8, 7, 6, 5, 4, 3):
        mask = (0xFF << (8 - bits)) & 0xFF
        table = bytes(v & mask for v in range(256))
        q = [im.translate(table) for im in images]
        counts = {}
        for qi in q:
            for i in range(0, len(qi), 4):
                c = qi[i:i + 4]
                if c[3]:
                    counts[c] = counts.get(c, 0) + 1
        if len(counts) <= 255:
            break
    kept = sorted(counts, key=counts.get, reverse=True)[:255]
    index = {c: k + 1 for k, c in enumerate(kept)}
    for c in counts:
        if c not in index:
            index[c] = min(index.items(), key=lambda kv: sum((a - b) ** 2 for a, b in
                                                           zip(kv[0], c)))[1]
    half = (~mask & 0xFF) >> 1
    palette = [tuple(v | half if v else v for v in c) for c in kept]
    out = [bytes(index.get(qi[i:i + 4], 0) if qi[i + 3] else 0 for i in range(0, len(qi), 4))
           for qi in q]
    return palette, out


def auto_nav(buttons):
    """The arrow keys between buttons that do not say where they go: the
    nearest button whose centre is that way (closer across counts more
    than along), else the button itself. Returns {id: {direction: id}}."""
    centre = {b.id: (b.x + b.w / 2, b.y + b.h / 2) for b in buttons}
    out = {}
    for b in buttons:
        cx, cy = centre[b.id]
        nav = {}
        for d in DIRECTIONS:
            if d in b.nav:
                nav[d] = b.nav[d]
                continue
            best, score = b.id, None
            for o in buttons:
                if o is b:
                    continue
                ox, oy = centre[o.id]
                along = {"up": cy - oy, "down": oy - cy, "left": cx - ox, "right": ox - cx}[d]
                across = abs(ox - cx) if d in ("up", "down") else abs(oy - cy)
                if along <= 0:
                    continue
                s = along + 2 * across
                if score is None or s < score:
                    best, score = o.id, s
            nav[d] = best
        out[b.id] = nav
    return out


def _segment(kind, data):
    return b"PG" + struct.pack(">IIBH", 0, 0, kind, len(data)) + data


def _objects(oid, w, h, pixels):
    """ODS segment(s) of one object (split when longer than a segment)."""
    coded = pgs.rle(pixels, w, h)
    data = (len(coded) + 4).to_bytes(3, "big") + struct.pack(">HH", w, h) + coded
    size = pgs.MAX_SEGMENT - 4
    chunks = [data[i:i + size] for i in range(0, len(data), size)]
    out = b""
    for k, chunk in enumerate(chunks):
        flags = (0x80 if k == 0 else 0) | (0x40 if k == len(chunks) - 1 else 0)
        out += _segment(ODS, struct.pack(">HBB", oid, 0, flags) + chunk)
    return out


def ig_stream(buttons, frame_rate, default=None, popup=False, button_offset=0,
              follow_selection=False, size=(WIDTH, HEIGHT)):
    """The buttons as an IG stream (.sup layout: "PG" segments).

    frame_rate: the menu clip's frame rate code (formats.FORMATS, or
    FORMATS_720 with size (1280, 720)); size: the video's frame, which the
    buttons are placed on;
    default: the id of the button selected when the menu starts (the
    first); follow_selection: keep the player's selection instead (a menu
    entered with a chosen button, set_button before playing it);
    button_offset: the number keys select button n with n + this."""
    if not buttons:
        raise BdmvError("a menu needs at least one button")
    ids = [b.id for b in buttons]
    if len(set(ids)) != len(ids):
        raise BdmvError("button ids must be unique")
    width, height = size
    for b in buttons:
        if b.x < 0 or b.y < 0 or b.x + b.w > width or b.y + b.h > height:
            raise BdmvError(f"button {b.id!r} is not inside the {width} x {height} frame")
        for name in ("selected", "activated", "normal"):
            pic = getattr(b, name)
            if pic is not None and len(pic) != b.w * b.h * 4:
                raise BdmvError(f"button {b.id!r}: its {name} picture is not {b.w} x {b.h} RGBA")
        for d, to in b.nav.items():
            if d not in DIRECTIONS or to not in ids:
                raise BdmvError(f"button {b.id!r}: nav {d} -> {to!r}")
    if default is not None and default not in ids:
        raise BdmvError(f"no button {default!r}")
    if button_offset + len(buttons) > 9999:
        raise BdmvError("button numbers go up to 9999")
    nav = auto_nav(buttons)
    index = {b.id: k for k, b in enumerate(buttons)}
    normal = any(b.normal is not None for b in buttons)
    pictures = []
    for b in buttons:
        empty = bytes(b.w * b.h * 4)
        pictures += [b.normal if b.normal is not None else empty, b.selected,
                     b.activated if b.activated is not None else b.selected]
    colours, indexed = quantize(pictures)
    palette = [(0, 16, 128, 128, 0)]
    for k, (r, g, bl, a) in enumerate(colours, 1):
        y, cb, cr = pgs.ycbcr((r, g, bl))
        palette.append((k, y, cr, cb, a))
    objects, body_buttons = b"", b""
    for k, b in enumerate(buttons):
        oids = {}
        for slot in (0, 1, 2):            # normal, selected, activated
            if slot == 0 and not normal:
                continue
            oid = 3 * k + slot
            objects += _objects(oid, b.w, b.h, indexed[3 * k + slot])
            oids[slot] = oid
        n_oid = oids.get(0, NO_OBJECT)
        moves = [index[nav[b.id][d]] for d in DIRECTIONS]
        cmds = list(b.commands)
        for c in cmds:
            if len(c) != 12:
                raise BdmvError(f"button {b.id!r}: a navigation command is 12 bytes")
        button = struct.pack(">HHBHH", k, button_offset + k + 1, 0x80 if b.auto else 0, b.x, b.y)
        button += struct.pack(">HHHH", *moves)
        button += struct.pack(">HHB", n_oid, n_oid, 0)
        button += struct.pack(">BHHB", 0xFF, oids[1], oids[1], 0)
        button += struct.pack(">BHH", 0xFF, oids[2], oids[2])
        button += struct.pack(">H", len(cmds)) + b"".join(cmds)
        # one button per overlap group: the buttons do not overlap
        body_buttons += struct.pack(">HB", k, 1) + button
    first = 0xFFFF if follow_selection else index.get(default, 0)
    page = struct.pack(">BB", 0, 0) + bytes(8)            # page 0, no user-operation mask
    page += bytes([0, 0]) + bytes([0, 0])                  # no in / out effects
    page += struct.pack(">BHHBB", 0, first, NO_OBJECT, 0, len(buttons)) + body_buttons
    # multiplexed; always on, or a pop-up (the Pop-up key shows it); no time-outs
    body = bytes([0x40 if popup else 0x00]) + bytes(10)
    body += (0).to_bytes(3, "big") + bytes([1]) + page     # no user time-out; one page
    ics = struct.pack(">HHB", width, height, frame_rate << 4)
    ics += struct.pack(">HB", 0, 0x80)                     # composition 0, epoch start
    ics += bytes([0xC0]) + len(body).to_bytes(3, "big") + body
    if len(ics) > pgs.MAX_SEGMENT:
        raise BdmvError("too many buttons or button commands for one composition")
    pds = bytes([0, 0]) + b"".join(bytes(e) for e in palette)
    return _segment(ICS, ics) + _segment(PDS, pds) + objects + _segment(END, b"")


def patch_ig_stream_type(path, pmt_pid=PMT_PID, pid=IG_PID):
    """ffmpeg muxes the IG stream as a PGS stream (stream type 0x90): mark it
    0x91 in every PMT of the clip (and fix the section CRC)."""
    with open(path, "r+b") as f:
        data = bytearray(f.read())
        for off in range(0, len(data), 192):
            p = off + 4
            if (data[p + 1] & 0x1F) << 8 | data[p + 2] != pmt_pid or not data[p + 1] & 0x40:
                continue
            q = p + 4
            if data[p + 3] & 0x20:
                q += 1 + data[q]
            q += 1 + data[q]                                # pointer field
            length = (data[q + 1] & 0x0F) << 8 | data[q + 2]
            end = q + 3 + length - 4
            info = (data[q + 10] & 0x0F) << 8 | data[q + 11]
            e = q + 12 + info
            while e < end:
                es_pid = (data[e + 1] & 0x1F) << 8 | data[e + 2]
                if es_pid == pid:
                    data[e] = CODING_IG
                e += 5 + ((data[e + 3] & 0x0F) << 8 | data[e + 4])
            data[end:end + 4] = crc32(bytes(data[q:end])).to_bytes(4, "big")
        f.seek(0)
        f.write(data)


def crc32(data):
    """MPEG-2 section CRC (polynomial 0x04C11DB7, no reflection)."""
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else \
                (crc << 1) & 0xFFFFFFFF
    return crc
