"""Read a BDMV folder back with libbluray (via ctypes).

libbluray is what VLC, mpv and Kodi play Blu-ray discs with: it parses
index.bdmv, MovieObject.bdmv, the playlists and the clip information, and
runs the HDMV navigation commands. If it lists our titles with the right
lengths and chapters, and following first play through its navigation
engine reaches the titles in the right order, the disc is laid out right.

Only used by tests; skipped when libbluray is not installed. The structs
are those of libbluray 1.x.
"""

import ctypes
import ctypes.util

BD_EVENT_ERROR = 1
BD_EVENT_TITLE = 5
BD_EVENT_PLAYLIST = 6
BD_EVENT_CHAPTER = 8
BD_EVENT_END_OF_TITLE = 10
BD_EVENT_AUDIO_STREAM = 11
BD_EVENT_PG_TEXTST_STREAM = 13
BD_EVENT_PG_TEXTST = 17
BD_EVENT_STILL = 25
BD_EVENT_STILL_TIME = 26

# remote keys (bd_vk_key_e)
KEYS = {"popup": 11, "up": 12, "down": 13, "left": 14, "right": 15, "enter": 16,
        **{str(d): d for d in range(10)}}           # (BD_VK_0 ... BD_VK_9: the number keys)
OVERLAY_IG, OVERLAY_DRAW, OVERLAY_CLEAR, OVERLAY_WIPE = 1, 3, 2, 4
BD_EVENT_IDLE = 28
BD_EVENT_UO_MASK_CHANGED = 33     # param: BLURAY_UO_* bits (0x1 menu call, 0x10 skip next ...)

_CANDIDATES = ("libbluray.so.2", "libbluray.so", "libbluray.2.dylib", "libbluray.dylib",
               "/opt/homebrew/lib/libbluray.dylib", "/usr/local/lib/libbluray.dylib")

u8, u16, u32, u64 = ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint32, ctypes.c_uint64


def structs(v15):
    """The title-info structs; libbluray 1.5 added fields to several of them."""

    class StreamInfo(ctypes.Structure):
        _fields_ = [("coding_type", u8), ("format", u8), ("rate", u8), ("char_code", u8),
                    ("lang", ctypes.c_char * 4), ("pid", u16), ("aspect", u8),
                    ("subpath_id", u8)] + \
            ([("dynamic_range_type", u8), ("color_space", u8), ("cr_flag", u8),
              ("hdr_plus_flag", u8)] if v15 else [])

    SP = ctypes.POINTER(StreamInfo)

    class ClipInfo(ctypes.Structure):
        _fields_ = [("pkt_count", u32), ("still_mode", u8), ("still_time", u16),
                    ("video_stream_count", u8), ("audio_stream_count", u8),
                    ("pg_stream_count", u8), ("ig_stream_count", u8),
                    ("sec_audio_stream_count", u8), ("sec_video_stream_count", u8)] + \
            ([("dv_stream_count", u8)] if v15 else []) + \
            [("video_streams", SP), ("audio_streams", SP), ("pg_streams", SP),
             ("ig_streams", SP), ("sec_audio_streams", SP), ("sec_video_streams", SP)] + \
            ([("dv_streams", SP)] if v15 else []) + \
            [("start_time", u64), ("in_time", u64), ("out_time", u64),
             ("clip_id", ctypes.c_char * 6)]

    class Chapter(ctypes.Structure):
        _fields_ = [("idx", u32), ("start", u64), ("duration", u64), ("offset", u64),
                    ("clip_ref", ctypes.c_uint)] + \
            ([("chapter_name", ctypes.c_char_p)] if v15 else [])

    class Mark(ctypes.Structure):
        _fields_ = [("idx", u32), ("type", ctypes.c_int), ("start", u64), ("duration", u64),
                    ("offset", u64), ("clip_ref", ctypes.c_uint)]

    class TitleInfo(ctypes.Structure):
        _fields_ = [("idx", u32), ("playlist", u32), ("duration", u64), ("clip_count", u32),
                    ("angle_count", u8), ("chapter_count", u32), ("mark_count", u32),
                    ("clips", ctypes.POINTER(ClipInfo)), ("chapters", ctypes.POINTER(Chapter)),
                    ("marks", ctypes.POINTER(Mark)), ("mvc_base_view_r_flag", u8)] + \
            ([("sdr_conversion_notification_flag", u8)] if v15 else [])

    return TitleInfo


class Title(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("interactive", u8), ("accessible", u8),
                ("hidden", u8), ("bdj", u8), ("id_ref", u32)]


class DiscInfo(ctypes.Structure):
    _fields_ = [("bluray_detected", u8), ("disc_name", ctypes.c_char_p),
                ("udf_volume_id", ctypes.c_char_p), ("disc_id", u8 * 20),
                ("no_menu_support", u8), ("first_play_supported", u8),
                ("top_menu_supported", u8), ("num_titles", u32),
                ("titles", ctypes.POINTER(ctypes.POINTER(Title))),
                ("first_play", ctypes.POINTER(Title)), ("top_menu", ctypes.POINTER(Title)),
                ("num_hdmv_titles", u32), ("num_bdj_titles", u32),
                ("num_unsupported_titles", u32)]


class Event(ctypes.Structure):
    _fields_ = [("event", u32), ("param", u32)]


class PaletteEntry(ctypes.Structure):
    _fields_ = [("Y", u8), ("Cr", u8), ("Cb", u8), ("T", u8)]


class RleElem(ctypes.Structure):
    _fields_ = [("len", u16), ("color", u16)]


class Overlay(ctypes.Structure):
    _fields_ = [("pts", ctypes.c_int64), ("plane", u8), ("cmd", u8),
                ("palette_update_flag", u8), ("x", u16), ("y", u16), ("w", u16), ("h", u16),
                ("palette", ctypes.POINTER(PaletteEntry)), ("img", ctypes.POINTER(RleElem))]


OVERLAY_PROC = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(Overlay))


def load_library():
    names = [n for n in (ctypes.util.find_library("bluray"),) if n] + list(_CANDIDATES)
    for n in names:
        try:
            lib = ctypes.CDLL(n)
        except OSError:
            continue
        P = ctypes.c_void_p
        version = [ctypes.c_int() for _ in range(3)]
        lib.bd_get_version(*(ctypes.byref(v) for v in version))
        TitleInfo = structs(tuple(v.value for v in version) >= (1, 5, 0))
        lib.bd_open.restype, lib.bd_open.argtypes = P, [ctypes.c_char_p, ctypes.c_char_p]
        lib.bd_close.argtypes = [P]
        lib.bd_get_disc_info.restype = ctypes.POINTER(DiscInfo)
        lib.bd_get_disc_info.argtypes = [P]
        lib.bd_get_titles.restype, lib.bd_get_titles.argtypes = u32, [P, u8, u32]
        lib.bd_get_playlist_info.restype = ctypes.POINTER(TitleInfo)
        lib.bd_get_playlist_info.argtypes = [P, u32, ctypes.c_uint]
        lib.bd_free_title_info.argtypes = [ctypes.POINTER(TitleInfo)]
        lib.bd_play.restype, lib.bd_play.argtypes = ctypes.c_int, [P]
        lib.bd_read_ext.restype = ctypes.c_int
        lib.bd_read_ext.argtypes = [P, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(Event)]
        lib.bd_user_input.restype = ctypes.c_int
        lib.bd_user_input.argtypes = [P, ctypes.c_int64, u32]
        lib.bd_register_overlay_proc.argtypes = [P, P, OVERLAY_PROC]
        lib.bd_menu_call.restype = ctypes.c_int
        lib.bd_menu_call.argtypes = [P, ctypes.c_int64]
        lib.bd_read_skip_still.restype, lib.bd_read_skip_still.argtypes = ctypes.c_int, [P]
        # (its notes about the end of the disc would fill the test output)
        lib.bd_set_debug_mask.argtypes = [u32]
        lib.bd_set_debug_mask(0)
        return lib
    return None


class Disc:
    """An opened BDMV folder (or image)."""

    def __init__(self, lib, path):
        self.lib = lib
        self.bd = lib.bd_open(path.encode(), None)
        if not self.bd:
            raise RuntimeError(f"libbluray cannot open {path}")

    def close(self):
        if self.bd:
            self.lib.bd_close(self.bd)
            self.bd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def info(self):
        d = self.lib.bd_get_disc_info(self.bd).contents
        return {"bluray": bool(d.bluray_detected), "titles": d.num_titles,
                "hdmv_titles": d.num_hdmv_titles, "first_play": bool(d.first_play_supported),
                "top_menu": bool(d.top_menu_supported)}

    def playlist(self, n):
        """Length (s), chapter starts (s) and streams of playlist n (xxxxx.mpls)."""
        self.lib.bd_get_titles(self.bd, 0, 0)
        p = self.lib.bd_get_playlist_info(self.bd, n, 0)
        if not p:
            return None
        t = p.contents
        clip = t.clips[0]
        out = {"duration": t.duration / 90000,
               "chapters": [t.chapters[i].start / 90000 for i in range(t.chapter_count)],
               "clip": clip.clip_id.decode(),
               "video": [(clip.video_streams[i].coding_type, clip.video_streams[i].format,
                          clip.video_streams[i].rate)
                         for i in range(clip.video_stream_count)],
               "audio": [(clip.audio_streams[i].coding_type, clip.audio_streams[i].format,
                          clip.audio_streams[i].lang.decode())
                         for i in range(clip.audio_stream_count)],
               "pg": [(clip.pg_streams[i].coding_type, clip.pg_streams[i].lang.decode())
                      for i in range(clip.pg_stream_count)]}
        self.lib.bd_free_title_info(p)
        return out

    def _overlay(self, _handle, ov):
        """IG overlay events: the button graphics the player draws, as
        ("draw", x, y, w, h, (Y, Cr, Cb, T) most used opaque colour)."""
        if not ov:
            return
        o = ov.contents
        if o.plane != OVERLAY_IG or o.cmd != OVERLAY_DRAW or not o.img:
            return
        counts, done, total, i = {}, 0, o.w * o.h, 0
        while done < total:
            e = o.img[i]
            i += 1
            if e.len == 0:
                continue
            c = o.palette[e.color]
            if c.T:
                key = (c.Y, c.Cr, c.Cb, c.T)
                counts[key] = counts.get(key, 0) + e.len
            done += e.len
        colour = max(counts, key=counts.get) if counts else None
        self.draws.append(("draw", o.x, o.y, o.w, o.h, colour))

    def play(self, max_bytes=200 * 2**20, keys=(), audio=False):
        """Run the disc from first play the way a player does, reading the
        streams and pressing `keys` ("up", "down", "enter" ...) one by one
        whenever the disc waits (a menu); "topmenu" is pressed while a title
        plays (once some of it was read); returns the navigation events in
        order as (name, value), with ("key", name) where a key was pressed
        and ("menu", button graphics drawn) after each key; with `audio`,
        also ("audio_stream", n) when the audio stream changes."""
        names = {BD_EVENT_TITLE: "title", BD_EVENT_PLAYLIST: "playlist",
                 BD_EVENT_CHAPTER: "chapter", BD_EVENT_END_OF_TITLE: "end",
                 **({BD_EVENT_AUDIO_STREAM: "audio_stream"} if audio else {}),
                 BD_EVENT_ERROR: "error", BD_EVENT_PG_TEXTST_STREAM: "subtitle_stream",
                 BD_EVENT_PG_TEXTST: "subtitles_shown", BD_EVENT_UO_MASK_CHANGED: "uo"}
        self.draws = []
        if keys:
            # (libbluray runs menus only for a player that draws them)
            self._proc = OVERLAY_PROC(self._overlay)
            self.lib.bd_register_overlay_proc(self.bd, None, self._proc)
        if not self.lib.bd_play(self.bd):
            raise RuntimeError("bd_play failed")
        keys = list(keys)
        buf = ctypes.create_string_buffer(6144 * 16)
        ev = Event()
        out, read, idle, waiting, since = [], 0, 0, 0, 0
        for _ in range(100000):     # (a bound, should the disc never end)
            if read >= max_bytes:
                break
            n = self.lib.bd_read_ext(self.bd, buf, len(buf), ctypes.byref(ev))
            if n < 0:
                out.append(("error", n))
                break
            read += n
            since += n
            if keys and keys[0] == "topmenu" and since > 300_000:
                out.append(("key", keys.pop(0)))
                self.lib.bd_menu_call(self.bd, -1)
                since = 0
                continue
            # "live:<key>": pressed while a title plays (the pop-up menu)
            if keys and keys[0].startswith("live:") and since > 200_000:
                key = keys.pop(0)
                if self.draws:
                    out.append(("menu", list(self.draws)))
                    self.draws = []
                out.append(("key", key))
                self.lib.bd_user_input(self.bd, -1, KEYS[key[5:]])
                since = 0
                continue
            if ev.event == BD_EVENT_STILL_TIME and ev.param:
                # a picture held for some seconds: let them pass at once
                out.append(("still", ev.param))
                self.lib.bd_read_skip_still(self.bd)
                continue
            item = (names.get(ev.event), ev.param)
            # (the end of the last title is reported on every read after it)
            if item[0] and not (item[0] == "end" and out and out[-1] == item):
                out.append(item)
            if ev.event == BD_EVENT_ERROR:
                break
            # a menu holding its picture: press the next key
            still = n == 0 and ev.event in (0, BD_EVENT_STILL, BD_EVENT_STILL_TIME,
                                            BD_EVENT_IDLE)
            waiting = waiting + 1 if still else 0
            if waiting > 30 and keys:
                if self.draws:
                    out.append(("menu", list(self.draws)))
                    self.draws = []
                if keys[0] != "topmenu" and not keys[0].startswith("live:"):
                    key = keys.pop(0)
                    out.append(("key", key))
                    self.lib.bd_user_input(self.bd, -1, KEYS[key])
                waiting, since = 0, 0
                continue
            # after the end of a title (or a menu with no more keys), a
            # while without data or new events means nothing follows
            stopped = n == 0 and out and (out[-1][0] == "end" or (not keys and waiting > 0)) \
                and ev.event in (0, BD_EVENT_END_OF_TITLE, BD_EVENT_IDLE, BD_EVENT_STILL_TIME)
            idle = idle + 1 if stopped else 0
            if idle > 40:
                break
        if self.draws:
            out.append(("menu", list(self.draws)))
        return out
