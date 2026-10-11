"""Encoding a video into a Blu-ray clip (.m2ts) with ffmpeg and x264.

The picture is fitted into the 1920 x 1080 frame (letter- or pillarboxed),
encoded as H.264 High at level 4.1 with x264's Blu-ray settings (at most a
second between key frames, key frames at the chapters), and muxed with its
sound and any PGS subtitle streams into a BDAV transport stream with the
PIDs the playlists name. 25 and 29.97 fps become progressive frames in an
interlaced (1080i) stream, as the format has no 1080p at those rates.
"""

import shutil
import subprocess

from .errors import BdmvError
from .formats import (AUDIO_PID, FORMATS, HEIGHT, PG_PID, PMT_PID, VBV_BUFFER, VIDEO_PID, WIDTH,
                      MAX_VIDEO_BPS)


def video_args(fps, max_bps=MAX_VIDEO_BPS, fast=False, keys=()):
    """x264 options for a Blu-ray video stream at `fps` ((num, den)); `keys`:
    times (s) to make key frames, e.g. the chapters."""
    if fps not in FORMATS:
        raise BdmvError(f"{fps[0]}/{fps[1]} fps has no Blu-ray format "
                        f"(use one of {', '.join(f'{a}/{b}' for a, b in FORMATS)})")
    gop = round(fps[0] / fps[1])            # at most one second between key frames
    x264 = (f"bluray-compat=1:slices=4:aud=1:nal-hrd=vbr:keyint={gop}:min-keyint=1:"
            "force-cfr=1")
    if FORMATS[fps][0] == 4:
        x264 += ":fake-interlaced=1:pic-struct=1"
    args = ["-c:v", "libx264", "-preset", "ultrafast" if fast else "medium",
            "-crf", "24" if fast else "19", "-profile:v", "high", "-level", "4.1",
            "-maxrate", str(max_bps), "-bufsize", str(VBV_BUFFER), "-x264-params", x264,
            "-r", f"{fps[0]}/{fps[1]}", "-pix_fmt", "yuv420p", "-aspect", "16:9",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-forced-idr", "1"]
    if keys:
        args += ["-force_key_frames", ",".join(f"{t:.6f}" for t in sorted(keys))]
    return args


def audio_args(codec="ac3", channels=2, k=0, bitrate=None):
    """Options for audio output stream k: "ac3", "lpcm" (16-bit stereo) or
    "copy" (as it is, e.g. AC-3 or DTS)."""
    if codec == "copy":
        return [f"-c:a:{k}", "copy"]
    if codec == "lpcm":
        return [f"-c:a:{k}", "pcm_bluray", f"-sample_fmt:a:{k}", "s16", f"-ar:a:{k}", "48000",
                f"-ac:a:{k}", "2"]
    if codec != "ac3":
        raise BdmvError(f"unknown audio codec {codec!r} (ac3, lpcm or copy)")
    bitrate = bitrate or (448000 if channels > 2 else 192000)
    return [f"-c:a:{k}", "ac3", f"-b:a:{k}", str(bitrate), f"-ar:a:{k}", "48000",
            f"-ac:a:{k}", str(channels)]


def fit_filter(fps):
    """The picture fitted into the HD frame, square pixels, at `fps`."""
    return (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps[0]}/{fps[1]}")


def encode_clip(source, out, fps=(24000, 1001), chapters=(), audio="ac3", channels=2,
                sups=(), max_bps=MAX_VIDEO_BPS, fast=False, ffmpeg=None):
    """Encode `source` (any video ffmpeg reads) into the Blu-ray clip `out`:
    its first audio stream, or silence when it has none. `chapters`: times
    (s) that become key frames, so chapter marks land on them. `sups`: PGS
    streams (.sup, e.g. from pgs.write_sup) muxed in as subtitle tracks."""
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        raise BdmvError("encoding needs ffmpeg (with libx264)")
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-i", source]
    if _has_audio(source, ffmpeg):
        sound = ["-map", "0:a:0"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        sound = ["-map", "1:a:0", "-shortest"]
    first_sup = cmd.count("-i")
    for sup in sups:
        cmd += ["-i", sup]
    cmd += ["-filter_complex", f"[0:v:0]{fit_filter(fps)}[v]", "-map", "[v]"] + sound
    for k in range(len(sups)):
        cmd += ["-map", f"{first_sup + k}:s:0"]
    cmd += video_args(fps, max_bps, fast, [t for t in chapters if t > 0])
    cmd += audio_args(audio, channels)
    if sups:
        cmd += ["-c:s", "copy"]
    cmd += ["-streamid", f"0:{VIDEO_PID}", "-streamid", f"1:{AUDIO_PID}"]
    for k in range(len(sups)):
        cmd += ["-streamid", f"{2 + k}:{PG_PID + k}"]
    cmd += ["-f", "mpegts", "-mpegts_m2ts_mode", "1", "-mpegts_pmt_start_pid", str(PMT_PID), out]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise BdmvError(f"ffmpeg could not encode {source}: {p.stderr.strip()[-800:]}")
    return out


def _has_audio(source, ffmpeg):
    probe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    p = subprocess.run([probe, "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=index", "-of", "csv=p=0", source], capture_output=True, text=True)
    return bool(p.stdout.strip())
