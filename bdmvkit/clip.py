"""Clip information (.clpi): a clip's streams, time span and entry-point map."""

from .formats import (AUDIO_PID, CODING_H264, CODING_IG, IG_PID, PG_PID, PMT_PID, TS_RATE,
                      VERSION, VIDEO_PID)
from .hdmv import _pad, _u8, _u16, _u32
from .playlist import _audio_attr, _pg_attr


def ep_map(entries):
    """EP_map() of the video stream: a coarse entry whenever the upper PTS or
    packet-number bits change, a fine entry per key frame."""
    coarse, fine = [], []
    last = None
    for i, (pts, spn, size) in enumerate(entries):
        key = (pts >> 19, spn & 0xFFFE0000)
        if key != last:
            coarse.append((i, pts >> 19 & 0x3FFF, spn))
            last = key
        # I_end_position_offset: how many bytes the key picture takes, in steps
        end = next((k for k, lim in enumerate((131072, 262144, 393216, 589824, 917504,
                                               1310720), 1) if size < lim), 7)
        fine.append(end << 28 | (pts >> 9 & 0x7FF) << 17 | spn & 0x1FFFF)
    table = b"".join(_u32(ref << 14 | cpts) + _u32(cspn) for ref, cpts, cspn in coarse)
    one = _u32(4 + len(table)) + table + b"".join(_u32(v) for v in fine)
    # stream_PID, 10 reserved bits + EP_stream_type 1 (video), the coarse and
    # fine counts (16 + 18 bits), then where the stream's map starts
    counts = 1 << 34 | len(coarse) << 18 | len(fine)
    head_len = 2 + 2 + 6 + 4        # (the address counts from the start of EP_map)
    head = _u8(0) + _u8(1) + _u16(VIDEO_PID) + counts.to_bytes(6, "big") + _u32(head_len)
    return head + one


def clpi(scan, video_format, frame_rate, audio, pg=(), ig=False):
    """Clip information of one .m2ts: its streams, time span and EP map.
    audio: [(coding, channels, lang3)]; pg: [lang3]; ig: menu buttons."""
    ts_type = bytes([0x80]) + b"HDMV" + bytes(9) + bytes(16)
    info = _u16(0) + _u8(1) + _u8(1) + _u32(0) + _u32(TS_RATE) + _u32(scan.packets) + \
        bytes(128) + _u16(len(ts_type)) + ts_type
    info = _u32(len(info)) + info
    start, end = scan.first_pts // 2, scan.end_pts // 2
    seq = _u8(0) + _u8(1) + _u32(0) + _u8(1) + _u8(0) + _u16(scan.pcr_pid) + _u32(0) + \
        _u32(start) + _u32(end)
    seq = _u32(len(seq)) + seq
    isrc = b"0" * 12
    streams = _u16(VIDEO_PID)
    coding = bytes([CODING_H264, video_format << 4 | frame_rate, 3 << 4, 0, 0]) + isrc + bytes(4)
    streams += _u8(len(coding)) + coding
    for k, tr in enumerate(audio):
        coding = _audio_attr(tr) + isrc + bytes(4)
        streams += _u16(AUDIO_PID + k) + _u8(len(coding)) + coding
    for k, lang in enumerate(pg):
        coding = _pg_attr(lang) + isrc + bytes(4)
        streams += _u16(PG_PID + k) + _u8(len(coding)) + coding
    if ig:
        coding = _pg_attr("und", CODING_IG) + isrc + bytes(4)
        streams += _u16(IG_PID) + _u8(len(coding)) + coding
    prog = _u8(0) + _u8(1) + _u32(0) + _u16(PMT_PID) + \
        _u8(1 + len(audio) + len(pg) + int(ig)) + _u8(0) + streams
    prog = _u32(len(prog)) + prog
    cpi = _u16(1) + ep_map(scan.entries)          # 12 reserved bits, CPI_type 1 (EP map)
    cpi = _u32(len(cpi)) + cpi
    parts = [info, seq, prog, cpi, _u32(0)]       # (the last one: no clip marks)
    pos, offsets, body = 40, [], b""
    for part in parts:
        offsets.append(pos)
        part = _pad(part, 4)
        body += part
        pos += len(part)
    return b"HDMV" + VERSION + b"".join(_u32(o) for o in offsets[1:]) + _u32(0) + \
        bytes(12) + body
