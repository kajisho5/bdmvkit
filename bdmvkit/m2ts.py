"""Reading a BDAV transport stream (.m2ts) back: where its key frames are
and the span of its pictures, for the clip information and chapter marks."""

import dataclasses

from .errors import BdmvError
from .formats import PMT_PID, VIDEO_PID


@dataclasses.dataclass
class ClipScan:
    packets: int          # 192-byte source packets
    first_pts: int        # 90 kHz, first picture shown
    end_pts: int          # 90 kHz, end of the last picture
    pcr_pid: int
    entries: list         # [(pts, spn, size in bytes)] of the key frames, in order


def _pts(b, i):
    return (((b[i] >> 1) & 7) << 30 | b[i + 1] << 22 | (b[i + 2] >> 1) << 15 |
            b[i + 3] << 7 | b[i + 4] >> 1)


def scan_m2ts(path, video_pid=VIDEO_PID):
    """Where the key frames of a .m2ts are (for the entry-point map) and the
    span of its pictures. Every picture is one PES packet (ffmpeg); key
    frames carry the random-access flag."""
    entries = []
    pts_all = []
    pcr_pid = None
    spn = 0
    with open(path, "rb") as f:
        while True:
            buf = f.read(192 * 8192)
            if not buf:
                break
            if len(buf) % 192:
                raise BdmvError(f"{path} is not a BDAV stream (length is not 192 × n)")
            for off in range(0, len(buf), 192):
                p = off + 4
                b1 = buf[p + 1]
                if not b1 & 0x40:
                    continue
                if buf[p] != 0x47:
                    raise BdmvError(f"{path}: lost sync at packet {spn + off // 192}")
                pid = (b1 & 0x1F) << 8 | buf[p + 2]
                if pid != video_pid:
                    continue
                afc = buf[p + 3] >> 4 & 3
                q = p + 4
                rai = False
                if afc & 2:
                    alen = buf[q]
                    if alen:
                        rai = bool(buf[q + 1] & 0x40)
                        if buf[q + 1] & 0x10:
                            pcr_pid = pid
                    q += 1 + alen
                # (a PES header must start in this packet with its PTS: 14 bytes)
                if not afc & 1 or q + 14 > p + 188 or buf[q:q + 3] != b"\0\0\1" \
                        or not buf[q + 7] & 0x80:
                    continue
                pts = _pts(buf, q + 9)
                n = spn + off // 192
                if entries and entries[-1][2] is None:
                    entries[-1][2] = (n - entries[-1][1]) * 192
                pts_all.append(pts)
                if rai:
                    entries.append([pts, n, None])
            spn += len(buf) // 192
    if not pts_all or not entries:
        raise BdmvError(f"{path}: no pictures with key frames found")
    if entries[-1][2] is None:
        entries[-1][2] = (spn - entries[-1][1]) * 192
    ordered = sorted(pts_all)
    step = ordered[1] - ordered[0] if len(ordered) > 1 else 3003
    return ClipScan(spn, ordered[0], ordered[-1] + step, pcr_pid or video_pid,
                    [tuple(e) for e in entries])


def stream_pids(path, pmt_pid=PMT_PID):
    """{PID: stream type} of the elementary streams the clip's first program
    map table names."""
    with open(path, "rb") as f:
        while (pkt := f.read(192)):
            if len(pkt) < 192:
                break
            p = 4
            if (pkt[p + 1] & 0x1F) << 8 | pkt[p + 2] != pmt_pid or not pkt[p + 1] & 0x40:
                continue
            q = p + 4
            if pkt[p + 3] & 0x20:
                q += 1 + pkt[q]
            q += 1 + pkt[q]                                # pointer field
            end = q + 3 + ((pkt[q + 1] & 0x0F) << 8 | pkt[q + 2]) - 4
            e = q + 12 + ((pkt[q + 10] & 0x0F) << 8 | pkt[q + 11])
            pids = {}
            while e < min(end, 192):
                pids[(pkt[e + 1] & 0x1F) << 8 | pkt[e + 2]] = pkt[e]
                e += 5 + ((pkt[e + 3] & 0x0F) << 8 | pkt[e + 4])
            return pids
    raise BdmvError(f"{path}: no program map table (PID {pmt_pid:#06x})")


def set_stream_types(path, types, pmt_pid=PMT_PID, chunk=1 << 22):
    """Give the elementary streams their stream types `types` ({PID: type})
    in every program map table of the clip, in place, with the section CRC
    made again. The clip is read a piece at a time and only its PMT packets
    are written, so a long clip costs no more memory than a short one."""
    from .igs import crc32
    head = bytes([0x47, 0x40 | pmt_pid >> 8, pmt_pid & 0xFF])     # (a section starts in it)
    chunk -= chunk % 192
    with open(path, "r+b") as f:
        pos = 0
        while (data := f.read(chunk)):
            i = data.find(head)
            while i >= 0:
                start = i - 4                                   # (the 4-byte packet header)
                if start >= 0 and start % 192 == 0 and start + 192 <= len(data):
                    pkt = bytearray(data[start:start + 192])
                    if _retype(pkt, types, crc32):
                        f.seek(pos + start)
                        f.write(pkt)
                        f.seek(pos + len(data))
                i = data.find(head, i + 1)
            pos += len(data)


def _retype(pkt, types, crc32):
    """Set the stream types in one PMT packet; whether it changed."""
    p = 4
    q = p + 4
    if pkt[p + 3] & 0x20:
        q += 1 + pkt[q]
    q += 1 + pkt[q]                                     # pointer field
    if pkt[q] != 2:                                     # (not a PMT section)
        return False
    end = q + 3 + ((pkt[q + 1] & 0x0F) << 8 | pkt[q + 2]) - 4
    if end + 4 > len(pkt):
        raise BdmvError("a program map table runs over its packet")
    e = q + 12 + ((pkt[q + 10] & 0x0F) << 8 | pkt[q + 11])
    changed = False
    while e < end:
        pid = (pkt[e + 1] & 0x1F) << 8 | pkt[e + 2]
        if pid in types and pkt[e] != types[pid]:
            pkt[e] = types[pid]
            changed = True
        e += 5 + ((pkt[e + 3] & 0x0F) << 8 | pkt[e + 4])
    if changed:
        pkt[end:end + 4] = crc32(bytes(pkt[q:end])).to_bytes(4, "big")
    return changed
