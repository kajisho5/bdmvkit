"""Reading a BDAV transport stream (.m2ts) back: where its key frames are
and the span of its pictures, for the clip information and chapter marks."""

import dataclasses

from .errors import BdmvError
from .formats import VIDEO_PID


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
