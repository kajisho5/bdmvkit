"""HDMV navigation: the 12-byte navigation commands, MovieObject.bdmv and
index.bdmv."""

import struct

from .formats import VERSION


def _u8(v):
    return struct.pack(">B", v)


def _u16(v):
    return struct.pack(">H", v)


def _u32(v):
    return struct.pack(">I", v)


def _pad(data, n):
    return data + b"\0" * (-len(data) % n)


def index_bdmv(title_objects, first_play, top_menu, video_format, frame_rate, interactive=()):
    """title_objects: the movie object of every title (title 1 first);
    interactive: the titles (1-based) that are menus."""
    app = _u32(34) + bytes([0, video_format << 4 | frame_rate]) + bytes(32)

    def hdmv(obj, playback_type):
        # playback_type 0 = movie, 1 = interactive
        return _u16(playback_type << 14) + _u16(obj) + _u32(0)

    body = _u32(1 << 30) + hdmv(first_play, 1) + _u32(1 << 30) + hdmv(top_menu, 1)
    body += _u16(len(title_objects))
    for n, obj in enumerate(title_objects, 1):
        body += _u32(1 << 30) + hdmv(obj, int(n in interactive))   # HDMV, access permitted
    index_start = 40 + len(app)
    return b"INDX" + VERSION + _u32(index_start) + _u32(0) + bytes(24) + app + \
        _u32(len(body)) + body


def _cmd(b0, b1, dst=0, src=0, b3=0, b2=0):
    """A 12-byte navigation command: operand count / group / sub-group,
    immediate flags / branch option, compare option, set option; operands."""
    return bytes([b0, b1, b2, b3]) + _u32(dst) + _u32(src)


def play_pl(playlist):
    """Play PlayList <playlist> (an immediate number)."""
    return _cmd(0x22, 0x80, playlist)


def set_subtitles(number):
    """Set Stream: subtitle (PG) track `number` shown, or 0 = none shown."""
    # Set group, SetSystem sub-group, two immediate operands, option 1 (Set Stream);
    # the first operand: PG stream number valid (0x8000), shown (0x4000)
    return _cmd(0x51, 0xC0, 0xC000 | number if number else 0, 0, 0x01)


def jump_title(title):
    """Jump Title <title>: 1..N, 0 = top menu."""
    return _cmd(0x21, 0x81, title)


def jump_title_reg(reg):
    """Jump Title to the number held in general register `reg`."""
    return _cmd(0x21, 0x01, reg)


def jump_object(obj):
    """Jump Object <obj> (a movie object number)."""
    return _cmd(0x21, 0x80, obj)


def play_pl_mark(playlist, mark):
    """Play PlayList <playlist> from mark <mark> (0-based)."""
    return _cmd(0x42, 0xC2, playlist, mark)


def goto(pc):
    """Goto command <pc> of the same object."""
    return _cmd(0x20, 0x81, pc)



def move(reg, value):
    """Move <value> into general register <reg>."""
    return _cmd(0x50, 0x40, reg, value, 0x01)


def set_button(button=None, reg=None):
    """Set Button Page: select button `button` (an id), or the one held in
    general register `reg`; the page stays."""
    # Set group, SetSystem sub-group, option 3; the operand's top bit: button valid
    if reg is not None:
        return _cmd(0x51, 0x40, 0x80000000 | reg, 0, 0x03)
    return _cmd(0x51, 0xC0, 0x80000000 | button, 0, 0x03)


def add(reg, value):
    """Add <value> to general register <reg>."""
    return _cmd(0x50, 0x40, reg, value, 0x03)


def rnd(reg, top):
    """Set general register <reg> to a random number from 1 to <top>."""
    return _cmd(0x50, 0x40, reg, top, 0x08)


def if_at_least(reg, value):
    """Compare: the next command runs only if general register `reg` >= value."""
    return _cmd(0x48, 0x40, reg, value, b2=0x04)


def if_equal(reg, value):
    """Compare: the next command runs only if general register `reg` == value."""
    return _cmd(0x48, 0x40, reg, value, b2=0x02)


def if_not_equal(reg, value):
    """Compare: the next command runs only if general register `reg` != value."""
    return _cmd(0x48, 0x40, reg, value, b2=0x03)


def popup_off():
    """Pop-up Off: close the pop-up menu."""
    return _cmd(0x11, 0x00, b3=0x07)


def resume():
    """Resume the title the menu was called from."""
    return _cmd(0x01, 0x04)


def set_streams(audio=None, subtitle=None):
    """Set Stream: audio track `audio` (1-based) and/or subtitle track
    `subtitle` shown (0 = subtitles off)."""
    dst = 0
    if audio:
        dst |= 0x80000000 | audio << 16
    if subtitle is not None:
        dst |= (0xC000 | subtitle) if subtitle else 0
    return _cmd(0x51, 0xC0, dst, 0, 0x01)


def movie_objects(objects):
    """objects: lists of 12-byte navigation commands."""
    data = b""
    for cmds in objects:
        # resume_intention_flag set: a menu called during playback can resume it
        data += _u16(1 << 15) + _u16(len(cmds)) + b"".join(cmds)
    body = _u32(0) + _u16(len(objects)) + data
    return b"MOBJ" + VERSION + _u32(0) + bytes(28) + _u32(len(body)) + body
