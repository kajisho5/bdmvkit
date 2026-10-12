"""Playlists (.mpls): play items with their streams, and chapter marks."""

from .formats import (AUDIO_PID, CODING_H264, CODING_IG, CODING_PG, IG_PID, PG_PID, VERSION,
                      VIDEO_PID, rate_code)
from .hdmv import _u8, _u16, _u32


def _video_attr(video_format, frame_rate):
    return bytes([CODING_H264, video_format << 4 | frame_rate, 0, 0, 0])


def _audio_attr(track):
    """(coding, channels, lang3[, rate]): the rate 48000 unless given."""
    coding, channels, lang, *rate = track
    fmt = 6 if channels > 2 else 3
    return bytes([coding, fmt << 4 | rate_code(coding, *rate)]) + lang.encode("ascii")


def _pg_attr(lang, coding=CODING_PG):
    return bytes([coding]) + lang.encode("ascii") + b"\0"


def mpls(items, marks, uo=0):
    """A playlist. items: [(clip name, in, out, video_format, frame_rate,
    audio, pg, ig, still[, uo])] played one after the other, times in 45 kHz
    on each clip's time line, audio [(coding, channels, lang3, rate)], pg [lang3]
    (subtitles), ig: the clip carries menu buttons, still: 2 holds the
    last picture (a still menu), (1, s) holds it for s seconds, uo: the
    item's UO mask; marks: chapter marks as (item index, time); uo: the
    whole playlist's UO mask (the remote keys it does not allow)."""
    app = _u32(14) + bytes([0, 1]) + _u16(0) + uo.to_bytes(8, "big") + _u16(0)
    body = b""
    for it in items:
        clip, in_time, out_time, video_format, frame_rate, audio, pg, ig, still = it[:9]
        item_uo = it[9] if len(it) > 9 else 0
        stn = _u16(0) + bytes([1, len(audio), len(pg), int(ig), 0, 0, 0, 0]) + bytes(4)
        entry = _u8(1) + _u16(VIDEO_PID) + bytes(6)
        stn += _u8(len(entry)) + entry + _u8(5) + _video_attr(video_format, frame_rate)
        for k, tr in enumerate(audio):
            entry = _u8(1) + _u16(AUDIO_PID + k) + bytes(6)
            stn += _u8(len(entry)) + entry + _u8(5) + _audio_attr(tr)
        for k, lang in enumerate(pg):
            entry = _u8(1) + _u16(PG_PID + k) + bytes(6)
            stn += _u8(len(entry)) + entry + _u8(5) + _pg_attr(lang)
        if ig:
            entry = _u8(1) + _u16(IG_PID) + bytes(6)
            stn += _u8(len(entry)) + entry + _u8(5) + _pg_attr("und", CODING_IG)
        still_mode, still_time = still if isinstance(still, tuple) else (still, 0)
        # connection_condition 1: the clips are not seamless; STC id 0
        item = clip.encode("ascii") + b"M2TS" + _u16(1) + _u8(0) + _u32(in_time) + \
            _u32(out_time) + item_uo.to_bytes(8, "big") + _u8(0) + _u8(still_mode) + _u16(still_time) + \
            _u16(len(stn)) + stn
        body += _u16(len(item)) + item
    playlist = _u16(0) + _u16(len(items)) + _u16(0) + body
    playlist = _u32(len(playlist)) + playlist
    mark = _u16(len(marks))
    for ref, t in marks:
        mark += _u8(0) + _u8(1) + _u16(ref) + _u32(t) + _u16(0xFFFF) + _u32(0)
    mark = _u32(len(mark)) + mark
    list_pos = 40 + len(app)
    mark_pos = list_pos + len(playlist)
    return b"MPLS" + VERSION + _u32(list_pos) + _u32(mark_pos) + _u32(0) + bytes(20) + app + \
        playlist + mark
